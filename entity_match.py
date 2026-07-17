"""entity_match.py — deterministic candidate finder for entity de-duplication.

Pure matching layer (no LLM). Given an entity name/key, surface the existing DB
entities it might be the same as, so a resolver (live or backfill) can decide reuse
vs new. Recall matters more than precision here — the LLM makes the final call, so
we cast a wide net with three complementary signals:

  1. translit-normalized exact/near equality — catches native-script<->Latin twins
     ("אנבידיה"/"Nvidia") and subtitle-vs-title collisions that the punctuation-only
     `extract.normalize_key` misses. Driven by the show's romanization map
     (SHOW.translit_singles / translit_digraphs); a no-op for Latin-script shows.
  2. fuzzy string similarity (rapidfuzz, difflib fallback) over Name AND Key.
  3. embedding cosine similarity (cross-lingual, paraphrase-tolerant).

A "catalog" is a list of records: {"page_id", "key", "name", "type",
"aliases": [..], "vec": [..]?}. Build one from notion_bridge._load_entities_index
via `catalog_from_index`, or from any live query.
"""

import json
import math
import os
import re

try:
    from rapidfuzz import fuzz as _rf_fuzz
    _HAVE_RAPIDFUZZ = True
except ImportError:  # pragma: no cover - fallback path
    import difflib
    _HAVE_RAPIDFUZZ = False

import config
from show_loader import SHOW

EMBED_MODEL = config.EMBEDDING_MODEL

EMBED_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "entity_embeddings.json")

# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------

# Per-show romanization: native script -> Latin. Best-effort for RECALL, NOT a
# faithful transliteration — the goal is to pull a native-script name close enough to
# its Latin twin that the fuzzy scorer flags the pair. Empty maps (a Latin-script
# show) make translit_normalize collapse to base_normalize.
_DIGRAPHS = dict(SHOW.translit_digraphs)
_SINGLES = dict(SHOW.translit_singles)
_SCRIPT_RE = re.compile(SHOW.native_script_re) if SHOW.native_script_re else None

# Subtitle separators: a title's real identity is the part before the first
# colon / dash — "How History Punishes: Those Who Conform" -> "How History Punishes".
_SUBTITLE_RE = re.compile(r"\s*[:–—]\s+|\s+-\s+")


def _romanize(s):
    for dig, lat in _DIGRAPHS.items():
        s = s.replace(dig, lat)
    return "".join(_SINGLES.get(ch, ch) for ch in s)


def base_normalize(s):
    """Lowercase, strip punctuation/diacritics, collapse whitespace. Same spirit as
    extract.normalize_key but applied to display names."""
    if not s:
        return ""
    s = s.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def strip_subtitle(name):
    """Return the pre-subtitle head if a separator is present, else the name."""
    if not name:
        return name
    head = _SUBTITLE_RE.split(name, maxsplit=1)[0].strip()
    # Only treat as a subtitle if the head is substantial (avoid nuking short names).
    return head if len(head) >= 3 else name


def translit_normalize(s):
    """Script-agnostic normalized form: romanize the show's script, drop subtitle,
    base-normalize. "אנבידיה" -> "anbidyh"; "Nvidia" -> "nvidia"; the two are then
    within fuzzy reach. With no romanization map configured this is base_normalize
    of the subtitle-stripped name."""
    if not s:
        return ""
    s = strip_subtitle(s)
    if _SCRIPT_RE is not None and _SCRIPT_RE.search(s):
        s = _romanize(s)
    return base_normalize(s)


# --------------------------------------------------------------------------
# Fuzzy
# --------------------------------------------------------------------------
def _ratio(a, b):
    if not a or not b:
        return 0.0
    if _HAVE_RAPIDFUZZ:
        # token_sort handles word-order; WRatio is a robust blend. Take the max.
        return max(_rf_fuzz.token_sort_ratio(a, b), _rf_fuzz.WRatio(a, b)) / 100.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _forms(name, key):
    """The set of normalized strings we compare against, per entity."""
    forms = set()
    for raw in (name, key):
        if not raw:
            continue
        forms.add(base_normalize(raw))
        forms.add(translit_normalize(raw))
    return {f for f in forms if f}


def fuzzy_score(name, key, rec):
    """Best fuzzy ratio between the query (name/key + variants) and a catalog record
    (its name, key, and aliases + variants)."""
    q = _forms(name, key)
    cand = _forms(rec.get("name"), rec.get("key"))
    for alias in rec.get("aliases") or []:
        cand |= _forms(alias, None)
    best = 0.0
    for a in q:
        for b in cand:
            if a == b:
                return 1.0
            best = max(best, _ratio(a, b))
    return best


# --------------------------------------------------------------------------
# Embeddings
# --------------------------------------------------------------------------
def _cosine(a, b):
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def embed_texts(client, texts):
    """Embed a list of strings via google-genai. Returns list[list[float]] aligned to
    input order. Batches to keep requests bounded."""
    out = []
    BATCH = 100
    for i in range(0, len(texts), BATCH):
        chunk = texts[i:i + BATCH]
        resp = client.models.embed_content(model=EMBED_MODEL, contents=chunk)
        out.extend([list(e.values) for e in resp.embeddings])
    return out


def load_embed_cache(path=EMBED_CACHE):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_embed_cache(cache, path=EMBED_CACHE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def refresh_embeddings(client, catalog, path=EMBED_CACHE):
    """Ensure every catalog record has a cached embedding of its Name. Incremental:
    only (re)embeds records whose name changed or are new. Mutates each record with a
    'vec' key and returns the updated cache dict {page_id: {name, key, vec}}."""
    cache = load_embed_cache(path)
    stale = [r for r in catalog
             if not r.get("page_id")
             or cache.get(r["page_id"], {}).get("name") != (r.get("name") or "")]
    if stale:
        vecs = embed_texts(client, [r.get("name") or r.get("key") or "" for r in stale])
        for r, v in zip(stale, vecs):
            if r.get("page_id"):
                cache[r["page_id"]] = {"name": r.get("name") or "",
                                       "key": r.get("key"), "vec": v}
        save_embed_cache(cache, path)
    for r in catalog:
        pid = r.get("page_id")
        if pid and pid in cache:
            r["vec"] = cache[pid]["vec"]
    return cache


# --------------------------------------------------------------------------
# Candidate finder
# --------------------------------------------------------------------------
def catalog_from_index(index):
    """Convert notion_bridge._load_entities_index output ({key: {...}}) into a catalog
    list. Requires the index entries to carry 'name' (and optionally 'aliases')."""
    out = []
    for key, v in index.items():
        out.append({
            "page_id": v.get("page_id"),
            "key": key,
            "name": v.get("name") or "",
            "type": v.get("type"),
            "aliases": v.get("aliases") or [],
            "vec": v.get("vec"),
        })
    return out


def cluster_pairs(catalog, fuzzy_floor=0.78, cosine_floor=0.85):
    """Vectorized all-pairs candidate detection for a full catalog (backfill scale).

    O(n^2) but pushed into C/BLAS: rapidfuzz.process.cdist for the fuzzy matrix,
    numpy matmul for the embedding cosine matrix. Returns a list of (i, j) index
    pairs (i<j) that pass EITHER floor. Pure-python per-pair scoring is far too slow
    at ~2000+ entities (16B float ops), so this path requires rapidfuzz + numpy;
    without them it raises (caller falls back to the slow find_candidates loop)."""
    if not _HAVE_RAPIDFUZZ:
        raise RuntimeError("cluster_pairs requires rapidfuzz")
    import numpy as np
    from rapidfuzz import process as _rf_process

    n = len(catalog)
    forms = [translit_normalize(r.get("name")) or base_normalize(r.get("name") or "")
             for r in catalog]
    pairs = set()

    # Fuzzy matrix (0-100). token_sort is order-robust; scores_cutoff prunes cheaply.
    fmat = _rf_process.cdist(forms, forms, scorer=_rf_fuzz.token_sort_ratio,
                             score_cutoff=fuzzy_floor * 100, workers=-1)
    fi, fj = np.where(np.triu(fmat, k=1) >= fuzzy_floor * 100)
    pairs.update(zip(fi.tolist(), fj.tolist()))

    # Embedding cosine matrix, if every record has a vec.
    vecs = [r.get("vec") for r in catalog]
    if all(v is not None for v in vecs):
        m = np.asarray(vecs, dtype=np.float32)
        norms = np.linalg.norm(m, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        m = m / norms
        # Chunk the matmul to bound peak memory on large catalogs.
        CH = 512
        for s in range(0, n, CH):
            sim = m[s:s + CH] @ m.T
            ci, cj = np.where(sim >= cosine_floor)
            for a, b in zip((ci + s).tolist(), cj.tolist()):
                if a < b:
                    pairs.add((a, b))
    return list(pairs)


def find_candidates(name, key, catalog, query_vec=None, k=6,
                    fuzzy_floor=0.72, cosine_floor=0.80):
    """Return up to k candidate matches for an entity, ranked by a blended score.

    fuzzy_floor / cosine_floor gate which records qualify on each signal; a record
    passing EITHER is a candidate (recall-first). query_vec (the entity name's
    embedding) enables the cosine signal; omit it to run fuzzy-only."""
    scored = []
    for rec in catalog:
        fs = fuzzy_score(name, key, rec)
        cs = _cosine(query_vec, rec.get("vec")) if query_vec and rec.get("vec") else 0.0
        if fs >= fuzzy_floor or cs >= cosine_floor:
            scored.append((max(fs, cs), fs, cs, rec))
    scored.sort(key=lambda t: t[0], reverse=True)
    out = []
    for blended, fs, cs, rec in scored[:k]:
        out.append({"key": rec["key"], "name": rec.get("name"), "type": rec.get("type"),
                    "page_id": rec.get("page_id"),
                    "score": round(blended, 3), "fuzzy": round(fs, 3),
                    "cosine": round(cs, 3)})
    return out
