"""extract.py — the entity-extraction brain (podcast-agnostic engine).

Turns a diarized transcript into the FROZEN extraction-contract JSON that
notion_bridge.process_episode consumes. Owns "summary", "headline", and "entities"
(each entity carries a 1-5 "notability" rank); the "episode" block is RSS metadata
passed through from the caller (incl. platform URLs), with headline copied in.

All podcast/language specifics — the system prompt, hosts, sponsors, language
thresholds, user-turn scaffolding — come from the active show via show_loader.
The model id comes from config.EXTRACTION_MODEL (single source of truth).

Uses Google's official SDK (google-genai). Key from env (GOOGLE_API_KEY).
"""

import json
import os
import re
import time

from google import genai
from google.genai import types
from google.genai import errors as genai_errors

import config
from show_loader import SHOW, STRINGS, PROMPT, REGEN_PROMPT

# Transient Gemini errors to retry with backoff (high-demand 503, rate-limit
# 429, server 500). A backfill of 60+ episodes will hit these occasionally.
RETRYABLE_CODES = {429, 500, 503}
MAX_API_RETRIES = 15        # ride out extended Gemini high-demand windows
MAX_BACKOFF = 120           # cap per-retry sleep (seconds)

MODEL = config.EXTRACTION_MODEL
# Generous output budget: a full episode can yield 90+ entities (a large JSON
# document). gemini-2.5-flash supports up to 65536 output tokens; use a high
# ceiling so the JSON is never truncated mid-string.
MAX_TOKENS = 65000

# Diarization-quality gate (per-show thresholds). Speaker attribution is only as
# good as the transcript's diarization; when it's effectively absent, a "confidently
# wrong" all-one-host attribution is worse than none. If the transcript has fewer
# than MIN_DISTINCT_SPEAKERS distinct [S#] labels, OR a single speaker owns more than
# MAX_SPEAKER_CHAR_SHARE of the spoken CHARACTERS (a monologue / failed diarization),
# we blank every entity's mentioned_by.
MIN_DISTINCT_SPEAKERS = SHOW.diarization_min_speakers
MAX_SPEAKER_CHAR_SHARE = SHOW.diarization_max_char_share

# Forbidden "meta" context patterns — context that describes the ACT of discussing
# (who said/wrote/mentioned it) instead of a direct claim about the entity. Some
# languages need this because prompt rules alone leak it; the patterns live in the
# show's Strings. An EMPTY pattern list disables the whole detect->regenerate->demote
# feature (the default for new shows).
META_CONTEXT_PATTERNS = list(STRINGS.meta_context_patterns)
META_CONTEXT_RE = re.compile("|".join(META_CONTEXT_PATTERNS)) if META_CONTEXT_PATTERNS else None


def _is_meta_context(ctx):
    """True if a context uses forbidden meta phrasing (describes who said/wrote it
    rather than stating a direct claim about the entity). Always False when the
    active show defines no meta-context patterns."""
    return bool(ctx) and META_CONTEXT_RE is not None and bool(META_CONTEXT_RE.search(ctx))


ENTITY_TYPES = list(SHOW.entity_types)

# Deterministic type->action mapping (source of truth; NOT in the prompt). The model
# only contributes a boolean is_tool, which overrides action to "Tool". place/other
# and unknown types -> None (no action).
ACTION_BY_TYPE = {
    "book": "To Read", "article": "To Read", "concept": "To Research",
    "stock": "To Watch", "company": "To Research", "person": "To Look Up",
    "place": None, "other": None,
}
# A show with a custom taxonomy can map its own types to an Action (or override a
# default) via config.action_by_type — so adding an entity type never needs an
# engine edit. Overlaid on top of the defaults above.
if SHOW.action_by_type:
    ACTION_BY_TYPE = {**ACTION_BY_TYPE, **SHOW.action_by_type}
VALID_SENTIMENTS = {"positive", "negative", "neutral"}
# The active show's regular hosts (short forms) + the guest label. mentioned_by is
# constrained to these. SINGLE SOURCE OF TRUTH: SHOW.hosts (shows/<name>/config.py).
HOSTS = SHOW.mentioned_by_enum
# HOST_BAN_KEYS / SPONSOR_BAN_KEYS are built from SHOW just below normalize_key
# (they need it to normalize the ban sets to canonical_key form).

# Per-episode extraction checkpoints (keyed by RSS guid). Makes the backfill
# fully resumable: a re-run reloads these and never re-calls Gemini.
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extractions")


def _checkpoint_path(guid):
    safe = re.sub(r"[^\w.-]", "_", str(guid))
    return os.path.join(CACHE_DIR, f"{safe}.json")


def _load_checkpoint(guid):
    path = _checkpoint_path(guid)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
    return None


def _save_checkpoint(guid, contract):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_checkpoint_path(guid), "w", encoding="utf-8") as f:
        json.dump(contract, f, ensure_ascii=False, indent=2)

# --------------------------------------------------------------------------
# Output schema for Gemini controlled generation. Gemini's response_schema uses
# the OpenAPI-subset dialect (NOT JSON-Schema): single "type" + "nullable": True
# for optional fields, no "additionalProperties". Python _validate is the
# secondary guard.
# --------------------------------------------------------------------------
CONTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "headline": {"type": "string"},
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "canonical_key": {"type": "string"},
                    "type": {"type": "string", "enum": ENTITY_TYPES},
                    # Plain integer: the OpenAPI-subset dialect is fragile on
                    # integer min/max/enum, so the 1-5 rubric is enforced in the
                    # prompt and clamped in _validate.
                    "notability": {"type": "integer"},
                    "ticker": {"type": "string", "nullable": True},
                    "one_liner": {"type": "string", "nullable": True},
                    "context": {"type": "string", "nullable": True},
                    "mentioned_by": {
                        "type": "array",
                        "items": {"type": "string", "enum": HOSTS},
                    },
                    "link": {"type": "string", "nullable": True},
                    "timestamp": {"type": "string", "nullable": True},
                    # action is OVERWRITTEN in _validate from the type mapping; the
                    # model's value is ignored. sentiment + is_tool + is_guest are
                    # real inputs.
                    "action": {"type": "string", "nullable": True},
                    "sentiment": {"type": "string"},
                    "is_tool": {"type": "boolean"},
                    # is_guest: true when this entity IS the episode's in-studio
                    # guest (a real person who appears/speaks as the interviewee),
                    # not merely someone discussed. Stored as a standalone flag.
                    "is_guest": {"type": "boolean"},
                    # suggested_category: only when type="other" AND the entity fits
                    # no existing type well — a short proposed type name (e.g.
                    # "ai_model"). The signal the taxonomy-review aggregates so a
                    # recurring new category can be promoted (see scripts/taxonomy_review.py).
                    # Null for everything that fits an existing type.
                    "suggested_category": {"type": "string", "nullable": True},
                },
                "required": [
                    "name", "canonical_key", "type", "notability", "ticker",
                    "one_liner", "context", "mentioned_by", "link", "timestamp",
                    "action", "sentiment", "is_tool", "is_guest",
                ],
            },
        },
    },
    "required": ["summary", "headline", "entities"],
}

# The extraction system prompt is the active show's editorial artifact, loaded from
# shows/<name>/prompt.txt via show_loader (imported at top as PROMPT). It is passed
# to Gemini as system_instruction in _call().


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def normalize_key(key):
    """Light deterministic normalization so model variance can't fragment dedup."""
    if not key:
        return key
    k = key.strip().lower()
    k = re.sub(r"[^\w\s-]", "", k, flags=re.UNICODE)  # strip punctuation
    k = re.sub(r"\s+", " ", k).strip()                 # collapse whitespace
    return k


# Deterministic host + sponsor post-filters (normalized to canonical_key form).
# Hosts kept leaking in as person-entities and sponsors as company-entities; both
# are dropped after extraction. resolved_host_ban_keys() folds in a normalized form
# of each host name so a plain rename in config can't silently stop the filter.
HOST_BAN_KEYS = {normalize_key(k) for k in SHOW.resolved_host_ban_keys()}
SPONSOR_BAN_KEYS = {normalize_key(k) for k in SHOW.sponsor_ban_keys}


def _strip_fences(text):
    """Remove ```json ... ``` fences if the model added them."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _validate(obj):
    """Validate the parsed object against the contract shape. Raises ValueError."""
    if not isinstance(obj, dict):
        raise ValueError("top-level is not an object")
    if not isinstance(obj.get("summary"), str):
        raise ValueError("summary missing or not a string")
    if not isinstance(obj.get("headline"), str):
        raise ValueError("headline missing or not a string")
    ents = obj.get("entities")
    if not isinstance(ents, list):
        raise ValueError("entities missing or not a list")
    required = {"name", "canonical_key", "type", "notability", "mentioned_by"}
    for i, e in enumerate(ents):
        if not isinstance(e, dict):
            raise ValueError(f"entity {i} is not an object")
        missing = required - e.keys()
        if missing:
            raise ValueError(f"entity {i} missing keys: {missing}")
        if e["type"] not in ENTITY_TYPES:
            raise ValueError(f"entity {i} has invalid type {e['type']!r}")
        if not isinstance(e.get("mentioned_by"), list):
            raise ValueError(f"entity {i} mentioned_by not a list")
        # Coerce + clamp notability to the 1-5 rubric; default 3 on junk.
        n = e.get("notability")
        e["notability"] = max(1, min(5, int(n))) if isinstance(n, (int, float)) else 3
        # sentiment: validate to the 3-value set; anything else -> neutral.
        sent = e.get("sentiment")
        e["sentiment"] = sent if sent in VALID_SENTIMENTS else "neutral"
        # action: deterministic from type; is_tool (model boolean) overrides to "Tool".
        # The model's own "action" value is ignored — code is the source of truth.
        e["action"] = "Tool" if bool(e.get("is_tool")) else ACTION_BY_TYPE.get(e["type"])
        # is_guest: standalone flag (unlike is_tool it does NOT fold into action).
        # Coerce to a real bool so the Notion checkbox always gets a definite value.
        e["is_guest"] = bool(e.get("is_guest"))
        # suggested_category: a normalized short slug, kept ONLY on "other" entities
        # (the misfit signal). Anything that landed in a real type can't also be
        # proposing a new one, so clear it there to keep the review signal clean.
        sc = e.get("suggested_category")
        sc = re.sub(r"[^\w]+", "_", (sc or "").strip().lower()).strip("_")
        e["suggested_category"] = sc if (sc and e["type"] == "other") else None
    return obj


def _merge_within_episode(entities):
    """Same canonical_key twice in one response -> merge (union mentioned_by,
    keep first one_liner/context/etc.)."""
    by_key = {}
    order = []
    for e in entities:
        key = e.get("canonical_key")
        if key in by_key:
            cur = by_key[key]
            merged = set(cur.get("mentioned_by") or []) | set(e.get("mentioned_by") or [])
            cur["mentioned_by"] = [m for m in HOSTS if m in merged]
            # notability: keep the strongest signal across duplicates.
            cur["notability"] = max(cur.get("notability") or 0, e.get("notability") or 0)
            # is_guest: OR across duplicates (same strongest-signal rule). A guest
            # folded onto a passing mention of the same person must stay flagged;
            # the promote-only Notion write can't recover a dropped True later.
            cur["is_guest"] = bool(cur.get("is_guest")) or bool(e.get("is_guest"))
            # fill empties from the duplicate
            for f in ("ticker", "one_liner", "context", "link", "timestamp"):
                if not cur.get(f) and e.get(f):
                    cur[f] = e[f]
        else:
            by_key[key] = dict(e)
            order.append(key)
    return [by_key[k] for k in order]


_SPEAKER_LINE = re.compile(r"^\s*(\[S\d+\])\s*(.*)$")


def _speaker_signal(text):
    """Diarization quality from the raw transcript: (distinct_labels, char_share).
    distinct_labels = number of distinct [S#] tags; char_share = fraction of the
    total labeled CHARACTERS owned by the single most-voluminous speaker. Used by
    the gate to decide whether speaker attribution is trustworthy at all."""
    by_char = {}
    for raw in text.splitlines():
        m = _SPEAKER_LINE.match(raw)
        if m:
            by_char[m.group(1)] = by_char.get(m.group(1), 0) + len(m.group(2))
    total = sum(by_char.values())
    char_share = (max(by_char.values()) / total) if total else 1.0
    return len(by_char), char_share


def clean_transcript(text):
    """Light input cleanup to cut input tokens without losing content:
    collapse consecutive same-speaker [S#] lines into one labeled block."""
    out = []
    cur_spk = None
    buf = []
    line_re = re.compile(r"^\s*(\[S\d+\])\s*(.*)$")
    for raw in text.splitlines():
        m = line_re.match(raw)
        if m:
            spk, txt = m.group(1), m.group(2).rstrip()
            if spk != cur_spk:
                if buf:
                    out.append(f"{cur_spk} " + " ".join(buf))
                cur_spk, buf = spk, []
            if txt:
                buf.append(txt)
        else:
            # non-labeled line: keep as-is, flush current speaker first
            if buf:
                out.append(f"{cur_spk} " + " ".join(buf))
                cur_spk, buf = None, []
            if raw.strip():
                out.append(raw.rstrip())
    if buf:
        out.append(f"{cur_spk} " + " ".join(buf))
    return "\n".join(out)


def _call(client, transcript_text, shownotes_text, force_json_suffix="", model=None):
    model = model or MODEL
    # Variable content goes LAST so Gemini's implicit prefix caching can reuse
    # the stable system instruction across episodes.
    user_parts = [f"{STRINGS.extract_transcript_prefix}\n\n{transcript_text}"]
    if shownotes_text:
        user_parts.append(STRINGS.extract_shownotes_note + shownotes_text)
    if force_json_suffix:
        user_parts.append("\n\n" + force_json_suffix)
    # Controlled generation: response_schema constrains output to the contract
    # (kills most parse-failure re-sends of the full transcript). mime_type
    # guarantees a fenceless JSON document. Low temperature for determinism.
    # Models can nondeterministically ignore the selectivity instruction and emit a
    # huge entity list that overruns MAX_TOKENS (truncated JSON). A truncated finish is
    # not retryable as an API error, so regenerate a few times — a fresh sample usually
    # comes back selective. Nudge temperature up ONLY on retries (first try stays 0.1 for
    # determinism); thinking JUDGMENT (selectivity + notability) needs ~4096 thinking
    # tokens, which fit under MAX_TOKENS once the entity list is selective.
    MAX_TRUNC_RETRIES = 2
    for trunc in range(MAX_TRUNC_RETRIES + 1):
        cfg = types.GenerateContentConfig(
            system_instruction=PROMPT,
            response_mime_type="application/json",
            response_schema=CONTRACT_SCHEMA,
            temperature=0.1 + 0.2 * trunc,
            max_output_tokens=MAX_TOKENS,
            thinking_config=types.ThinkingConfig(thinking_budget=4096),
        )
        # Backoff-retry transient API errors (503 high demand, 429 rate limit, 500).
        delay = 2.0
        for attempt in range(MAX_API_RETRIES):
            try:
                resp = client.models.generate_content(
                    model=model, contents="".join(user_parts), config=cfg)
                break
            except genai_errors.APIError as e:
                code = getattr(e, "code", None)
                if code in RETRYABLE_CODES and attempt < MAX_API_RETRIES - 1:
                    print(f"    [gemini {code}] retry {attempt + 1}/{MAX_API_RETRIES} "
                          f"in {delay:.0f}s")
                    time.sleep(delay)
                    delay = min(delay * 2, MAX_BACKOFF)
                    continue
                raise
        # Surface truncation explicitly — a MAX_TOKENS finish yields an
        # unterminated-string JSON error downstream that's otherwise hard to read.
        truncated = False
        try:
            fr = resp.candidates[0].finish_reason
            truncated = fr is not None and str(fr).rsplit(".", 1)[-1] == "MAX_TOKENS"
        except (AttributeError, IndexError, TypeError):
            pass
        if not truncated:
            return resp.text or ""
        if trunc < MAX_TRUNC_RETRIES:
            print(f"    [gemini MAX_TOKENS] output truncated; regenerating "
                  f"{trunc + 1}/{MAX_TRUNC_RETRIES} at temp {0.1 + 0.2 * (trunc + 1):.1f}")
            continue
        raise RuntimeError(
            f"Gemini hit MAX_TOKENS ({MAX_TOKENS}) on {MAX_TRUNC_RETRIES + 1} tries; "
            "model over-generated entities. Raise MAX_TOKENS or tighten selectivity."
        )


# --------------------------------------------------------------------------
# Meta-context regeneration (one batched call for the flagged subset)
# --------------------------------------------------------------------------
REGEN_SCHEMA = {
    "type": "object",
    "properties": {
        "contexts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "context": {"type": "string"},
                },
                "required": ["i", "context"],
            },
        },
    },
    "required": ["contexts"],
}



def _regenerate_contexts(client, flagged, transcript_text, model=None):
    """One batched Gemini call to rewrite meta contexts into direct claims.
    `flagged` = list of (index, entity). Returns {index: new_context}. Best-effort:
    {} on failure (caller then applies the notability=1 fallback)."""
    model = model or MODEL
    items = [{"i": i, "name": e.get("name"), "type": e.get("type"),
              "context": e.get("context") or ""} for i, e in flagged]
    payload = (f"{STRINGS.extract_transcript_prefix}\n\n" + transcript_text
               + f"\n\n{STRINGS.regen_items_prefix}\n" + json.dumps(items, ensure_ascii=False))
    cfg = types.GenerateContentConfig(
        system_instruction=REGEN_PROMPT,
        response_mime_type="application/json",
        response_schema=REGEN_SCHEMA,
        temperature=0.1,
        max_output_tokens=MAX_TOKENS,
        thinking_config=types.ThinkingConfig(thinking_budget=4096),
    )
    delay = 2.0
    for attempt in range(MAX_API_RETRIES):
        try:
            resp = client.models.generate_content(model=model, contents=payload, config=cfg)
            break
        except genai_errors.APIError as e:
            code = getattr(e, "code", None)
            if code in RETRYABLE_CODES and attempt < MAX_API_RETRIES - 1:
                time.sleep(delay)
                delay = min(delay * 2, MAX_BACKOFF)
                continue
            print(f"  [regen] failed: {e}")
            return {}
    try:
        obj = json.loads(_strip_fences(resp.text or ""))
        return {int(c["i"]): (c.get("context") or "").strip()
                for c in obj.get("contexts", []) if "i" in c}
    except (json.JSONDecodeError, ValueError, TypeError, KeyError) as e:
        print(f"  [regen] parse failed: {e}")
        return {}


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
def extract(transcript_text, episode_meta=None, shownotes_text=None, use_cache=True,
            model=None):
    """Transcript -> extraction contract dict. Single API call, defensive parse,
    one retry on parse/validation failure, then raise.

    Checkpoint/skip: if extractions/{guid}.json already exists, load and return
    it WITHOUT any Gemini call (makes a backfill fully resumable at zero cost).

    model overrides EXTRACTION_MODEL for this call (model bake-off). use_cache=False
    skips both the checkpoint read and write — so a bake-off never reads a stale
    contract nor clobbers the canonical extractions/{guid}.json with a trial model's
    output.
    """
    meta = episode_meta or {}
    guid = meta.get("guid")
    model = model or MODEL

    # 1. Checkpoint hit -> zero API cost.
    if use_cache and guid:
        cached = _load_checkpoint(guid)
        if cached is not None:
            print(f"  [cache] hit for guid={guid} — skipping Gemini call")
            return cached

    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("GOOGLE_API_KEY not set in .env")
    client = genai.Client()

    # Diarization quality from the RAW transcript (before clean_transcript collapses
    # blocks) — drives the attribution gate applied after extraction.
    distinct_spk, char_share = _speaker_signal(transcript_text)

    transcript_text = clean_transcript(transcript_text)
    raw = _call(client, transcript_text, shownotes_text, model=model)
    try:
        obj = _validate(json.loads(_strip_fences(raw)))
    except (json.JSONDecodeError, ValueError):
        raw = _call(client, transcript_text, shownotes_text,
                    force_json_suffix="Return ONLY valid JSON, nothing else.", model=model)
        try:
            obj = _validate(json.loads(_strip_fences(raw)))
        except (json.JSONDecodeError, ValueError) as e:
            raise RuntimeError(f"extract failed to produce valid JSON after retry: {e}") from e

    # Deterministic key normalization, then drop host leaks, then within-episode
    # merge. Filtering AFTER normalize (the ban set is normalized form) and BEFORE
    # merge (so a host row never survives a key collision) — see HOST_BAN_KEYS.
    for e in obj["entities"]:
        e["canonical_key"] = normalize_key(e.get("canonical_key"))
    obj["entities"] = [e for e in obj["entities"]
                       if e.get("canonical_key") not in HOST_BAN_KEYS
                       and e.get("canonical_key") not in SPONSOR_BAN_KEYS]
    obj["entities"] = _merge_within_episode(obj["entities"])

    # Meta-context fix (deterministic, code-enforced — prompt rules failed 3×):
    # detect forbidden meta phrasing, regenerate the flagged subset in ONE batched
    # call, then fall back to notability=1 for anything still meta or empty (drops
    # it out of the digest's 13-cap while keeping it in the archive).
    flagged = [(i, e) for i, e in enumerate(obj["entities"]) if _is_meta_context(e.get("context"))]
    if flagged:
        print(f"  [meta] {len(flagged)} flagged context(s) — regenerating")
        fixes = _regenerate_contexts(client, flagged, transcript_text, model=model)
        for i, e in flagged:
            new_ctx = fixes.get(i)
            if new_ctx is not None:
                e["context"] = new_ctx  # cleaned or "" (empty = no substance)
            if not e.get("context") or _is_meta_context(e.get("context")):
                e["notability"] = 1  # unfixable -> demote out of the digest

    # Attribution gate: if diarization is effectively absent, blank all mentioned_by
    # — honest-empty beats confidently-wrong. (The message drops attribution anyway
    # when <2 distinct speakers, so empties flow through cleanly.)
    if distinct_spk < MIN_DISTINCT_SPEAKERS or char_share > MAX_SPEAKER_CHAR_SHARE:
        print(f"  [gate] low diarization (distinct={distinct_spk}, "
              f"char_share={char_share:.3f}) — blanking attribution")
        for e in obj["entities"]:
            e["mentioned_by"] = []

    # Assemble the full contract. episode is pass-through metadata from the caller,
    # PLUS headline (model output) and the platform URLs the caller resolved — so
    # the cached contract carries everything notify needs on a --cached-only re-run.
    episode = {
        "number": meta.get("number"),
        "title": meta.get("title"),
        "headline": obj.get("headline"),
        "date": meta.get("date"),
        "duration": meta.get("duration"),
        "audio_url": meta.get("audio_url"),
        "youtube_url": meta.get("youtube_url"),
        "spotify_url": meta.get("spotify_url"),
        "apple_url": meta.get("apple_url"),
        "guid": meta.get("guid"),
    }
    contract = {"episode": episode, "summary": obj["summary"],
                "headline": obj.get("headline"), "entities": obj["entities"]}

    # Checkpoint so a re-run / backfill skips this episode at zero API cost.
    # Gated on use_cache so a bake-off (use_cache=False) never overwrites the
    # canonical contract with a trial model's output.
    if guid and use_cache:
        _save_checkpoint(guid, contract)
    return contract
