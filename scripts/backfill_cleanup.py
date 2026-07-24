#!/usr/bin/env python3
"""backfill_cleanup.py — generate a human-reviewable cleanup plan for the whole
Entities archive. WRITES NOTHING to Notion; emits backfill_proposals.{json,txt}.

Three proposal kinds:
  merges[]       — duplicate clusters (translit + fuzzy + embedding candidates,
                   confirmed by an LLM), with a chosen survivor + canonical name/key.
  renames[]      — standalone pages whose Name is STT-garbled or wrong (LLM name
                   review), with the corrected name/key.
  new_entities[] — entities the old (weaker) extraction missed, recovered by re-running
                   extract with the current model over cached transcripts and diffing
                   against the DB.  (opt-in: --recover-missed, expensive.)

The clustering prompt is per-show: shows/<name>/backfill.txt. A show WITHOUT that
file cannot run the merge pass (we refuse rather than guess with a generic prompt) —
same opt-in contract as resolve.txt / resolve_entities.py.

Review/edit the JSON, then apply with apply_backfill.py --confirm.

  PYTHONPATH=. ./venv/bin/python scripts/backfill_cleanup.py                  # merges + renames
  PYTHONPATH=. ./venv/bin/python scripts/backfill_cleanup.py --no-name-review # merges only (cheapest)
  PYTHONPATH=. ./venv/bin/python scripts/backfill_cleanup.py --recover-missed # + missed-entity recovery
"""

import argparse
import glob
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

from google import genai
from google.genai import types
from google.genai import errors as genai_errors

import config
import entity_match
import extract
from extract import (normalize_key, HOST_BAN_KEYS, SPONSOR_BAN_KEYS,
                     RETRYABLE_CODES, MAX_API_RETRIES, MAX_BACKOFF, MAX_TOKENS)
from notion_bridge import _client, _plain
from show_loader import BACKFILL_PROMPT

MODEL = config.RESOLVE_MODEL
# Scripts live in scripts/; the caches and proposal files they read/write belong to
# the repo root (same place extract.py writes extractions/), so resolve from parent.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_JSON = os.path.join(ROOT, "backfill_proposals.json")
OUT_TXT = os.path.join(ROOT, "backfill_proposals.txt")
EXTRACTIONS_GLOB = os.path.join(ROOT, "extractions", "*.json")

# Candidate gates for clustering: recall-first but tight enough to keep clusters small
# (the LLM makes the final merge call).
FUZZY_FLOOR = 0.78
COSINE_FLOOR = 0.85

# The backfill LLM passes are classification, not deep reasoning — a small thinking
# budget is plenty and ~5x faster than the extraction default (4096). Batches are I/O
# bound on the Gemini API, so run them concurrently.
THINK_BUDGET = 512
LLM_WORKERS = 5
# google-genai sets NO request timeout by default — a stalled response hangs the
# worker (and the whole ThreadPool via ex.map) forever. Cap every call.
HTTP_TIMEOUT_MS = 120000
# Retry 504 (DEADLINE_EXCEEDED) in addition to the transient set — flash models return
# it often under load, and a fresh (smaller) attempt usually succeeds.
BACKFILL_RETRY_CODES = RETRYABLE_CODES | {504}
# Batch sizes kept small so each call stays well under the server deadline.
CLUSTER_BATCH = 5
RENAME_BATCH = 40


# --------------------------------------------------------------------------
# Load the live archive
# --------------------------------------------------------------------------
def load_catalog(client):
    """Query the Entities DS -> catalog records for matching + a page dict for apply.
    Returns list of {page_id, key, name, type, aliases, episodes_n, mentions}."""
    out = []
    cursor = None
    while True:
        kwargs = {"data_source_id": config.NOTION_ENTITIES_DS_ID, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = client.data_sources.query(**kwargs)
        for pg in resp.get("results", []):
            p = pg["properties"]
            name = _plain(p.get("Name"))
            key = _plain(p.get("Key")) or normalize_key(name)
            aliases = [a.strip() for a in _plain(p.get("Aliases")).splitlines() if a.strip()]
            out.append({
                "page_id": pg["id"],
                "key": key,
                "name": name,
                "type": (p.get("Type", {}).get("select") or {}).get("name"),
                "aliases": aliases,
                "episodes_n": len(p.get("Episodes", {}).get("relation") or []),
                "mentions": p.get("Mentions", {}).get("number") or 0,
            })
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    # Drop hosts/sponsors that should never be entities (defensive).
    return [r for r in out
            if normalize_key(r["key"]) not in HOST_BAN_KEYS
            and normalize_key(r["key"]) not in SPONSOR_BAN_KEYS]


# --------------------------------------------------------------------------
# Clustering (deterministic candidate graph)
# --------------------------------------------------------------------------
def cluster_duplicates(catalog):
    """Connected components over candidate pairs (fuzzy OR embedding). Returns list of
    clusters, each a list of catalog records (size >= 2). Uses the vectorized
    all-pairs path (rapidfuzz cdist + numpy); falls back to the per-record loop only
    if that's unavailable."""
    n = len(catalog)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    try:
        for i, j in entity_match.cluster_pairs(catalog, FUZZY_FLOOR, COSINE_FLOOR):
            union(i, j)
    except Exception as e:  # noqa: BLE001 - fall back to the slow but portable path
        print(f"  [cluster] vectorized path unavailable ({e}); using slow loop")
        idx_by_page = {r["page_id"]: i for i, r in enumerate(catalog)}
        for i, rec in enumerate(catalog):
            others = [c for c in catalog if c["page_id"] != rec["page_id"]]
            for c in entity_match.find_candidates(
                    rec["name"], rec["key"], others, query_vec=rec.get("vec"),
                    k=8, fuzzy_floor=FUZZY_FLOOR, cosine_floor=COSINE_FLOOR):
                j = idx_by_page.get(c["page_id"])
                if j is not None:
                    union(i, j)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(catalog[i])
    return [g for g in groups.values() if len(g) >= 2]


# --------------------------------------------------------------------------
# LLM passes
# --------------------------------------------------------------------------
def _gemini_json(client, system, payload, schema, model):
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_schema=schema,
        temperature=0.1,
        max_output_tokens=MAX_TOKENS,
        thinking_config=types.ThinkingConfig(thinking_budget=THINK_BUDGET),
    )
    delay = 2.0
    for attempt in range(MAX_API_RETRIES):
        try:
            resp = client.models.generate_content(model=model, contents=payload, config=cfg)
            break
        except genai_errors.APIError as e:
            code = getattr(e, "code", None)
            # 504 DEADLINE_EXCEEDED is common on flash models under load; retry it too.
            if code in BACKFILL_RETRY_CODES and attempt < MAX_API_RETRIES - 1:
                time.sleep(delay)
                delay = min(delay * 2, MAX_BACKOFF)
                continue
            raise
    return json.loads(resp.text or "{}")


CLUSTER_SCHEMA = {
    "type": "object",
    "properties": {
        "clusters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "is_duplicate": {"type": "boolean"},
                    "survivor": {"type": "integer"},
                    "canonical_name": {"type": "string"},
                    "canonical_key": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "reason": {"type": "string"},
                },
                "required": ["id", "is_duplicate", "survivor", "canonical_name",
                             "canonical_key", "confidence", "reason"],
            },
        },
    },
    "required": ["clusters"],
}

RENAME_SCHEMA = {
    "type": "object",
    "properties": {
        "renames": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "canonical_name": {"type": "string"},
                    "canonical_key": {"type": "string"},
                    "reason": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["i", "canonical_name", "canonical_key", "reason", "confidence"],
            },
        },
    },
    "required": ["renames"],
}

# Unlike the clustering prompt (per-show, shows/<name>/backfill.txt — it needs the
# show's language/script pairs to judge duplicates), the rename pass is a pure
# "is this name garbled?" call that stays language-agnostic: the model sees the name
# in whatever script it was stored and answers about that name.
RENAME_SYSTEM = """\
You are auditing entity names in a podcast's entity database, looking ONLY for names \
that are WRONG or garbled by speech-to-text. You receive a list of entities (i, name, \
type). In "renames", return ONLY those whose name is wrong AND can be confidently \
corrected to the real name — e.g. a phonetic mangling of a foreign name, an obvious \
misspelling, or a descriptor used in place of an actual name. For each correction \
return canonical_name (the correct name), canonical_key (a clean dedup key: lowercase, \
no punctuation or subtitle, singular, prefer the widely-known form), reason, and \
confidence. Do NOT include names that are already correct, and do NOT guess — if you \
do not know the real name, omit the item. Return valid JSON per the schema.\
"""


def _run_batches(fn, n_items, batch):
    """Run fn(start) over batched ranges concurrently; return list of results (order
    irrelevant to callers, which key off returned indices)."""
    starts = list(range(0, n_items, batch))
    with ThreadPoolExecutor(max_workers=LLM_WORKERS) as ex:
        return list(ex.map(fn, starts))


def resolve_clusters(client, clusters, model):
    """LLM-confirm each cluster (batches run concurrently). Returns merge proposals."""
    BATCH = CLUSTER_BATCH

    def do(start):
        chunk = clusters[start:start + BATCH]
        items = []
        for cid, cl in enumerate(chunk):
            members = [{"index": mi, "name": m["name"], "type": m["type"],
                        "key": m["key"], "episodes": m["episodes_n"]}
                       for mi, m in enumerate(cl)]
            items.append({"id": cid, "members": members})
        payload = "clusters:\n" + json.dumps(items, ensure_ascii=False, indent=1)
        out = []
        try:
            obj = _gemini_json(client, BACKFILL_PROMPT, payload, CLUSTER_SCHEMA, model)
        except Exception as e:  # noqa: BLE001
            print(f"  [cluster] batch {start} failed: {e}", flush=True)
            return out
        print(f"  [cluster] batch {start} done", flush=True)
        for r in obj.get("clusters", []):
            cid = r.get("id")
            if cid is None or cid >= len(chunk) or not r.get("is_duplicate"):
                continue
            cl = chunk[cid]
            sv = r.get("survivor")
            if not isinstance(sv, int) or sv < 0 or sv >= len(cl):
                sv = max(range(len(cl)), key=lambda k: (cl[k]["episodes_n"], cl[k]["mentions"]))
            survivor = cl[sv]
            losers = [m for k, m in enumerate(cl) if k != sv]
            aliases = sorted({m["name"] for m in cl if m["name"] != r.get("canonical_name")})
            out.append({
                "survivor_id": survivor["page_id"],
                "survivor_name": survivor["name"],
                "loser_ids": [m["page_id"] for m in losers],
                "loser_names": [m["name"] for m in losers],
                "canonical_name": (r.get("canonical_name") or survivor["name"]).strip(),
                "canonical_key": normalize_key(r.get("canonical_key")) or survivor["key"],
                "aliases": aliases,
                "confidence": r.get("confidence"),
                "reason": r.get("reason"),
            })
        return out

    return [p for batch_out in _run_batches(do, len(clusters), BATCH) for p in batch_out]


def review_names(client, catalog, model):
    """Batched STT/garble name review over standalone pages (batches run concurrently)."""
    BATCH = RENAME_BATCH

    def do(start):
        chunk = catalog[start:start + BATCH]
        items = [{"i": start + k, "name": r["name"], "type": r["type"]}
                 for k, r in enumerate(chunk)]
        payload = "entities:\n" + json.dumps(items, ensure_ascii=False)
        out = []
        try:
            obj = _gemini_json(client, RENAME_SYSTEM, payload, RENAME_SCHEMA, model)
        except Exception as e:  # noqa: BLE001
            print(f"  [rename] batch {start} failed: {e}", flush=True)
            return out
        print(f"  [rename] batch {start} done", flush=True)
        for r in obj.get("renames", []):
            i = r.get("i")
            if i is None or i >= len(catalog):
                continue
            rec = catalog[i]
            new_name = (r.get("canonical_name") or "").strip()
            if not new_name or new_name == rec["name"]:
                continue
            out.append({
                "page_id": rec["page_id"],
                "old_name": rec["name"],
                "canonical_name": new_name,
                "canonical_key": normalize_key(r.get("canonical_key")) or rec["key"],
                "confidence": r.get("confidence"),
                "reason": r.get("reason"),
            })
        return out

    return [p for batch_out in _run_batches(do, len(catalog), BATCH) for p in batch_out]


# --------------------------------------------------------------------------
# Missed-entity recovery
# --------------------------------------------------------------------------
def recover_missed(client, catalog, model):
    """Re-extract cached transcripts with the current model and propose entities that
    have no strong match in the DB. Expensive (one Gemini call per uncached transcript)."""
    import transcribe  # local: heavy import only when this opt-in path runs
    entity_match.refresh_embeddings(client, catalog)
    proposals = {}
    for path in sorted(glob.glob(EXTRACTIONS_GLOB)):
        with open(path, encoding="utf-8") as f:
            contract = json.load(f)
        guid = (contract.get("episode") or {}).get("guid")
        tpath = transcribe.transcript_path(guid) if guid else None
        if not tpath or not os.path.exists(tpath):
            continue
        with open(tpath, encoding="utf-8") as f:
            text = f.read()
        meta = contract.get("episode") or {}
        try:
            fresh = extract.extract(text, episode_meta=meta, model=model, use_cache=False)
        except Exception as e:  # noqa: BLE001
            print(f"  [recover] {guid} extract failed: {e}")
            continue
        for e in fresh.get("entities", []):
            nk = normalize_key(e.get("canonical_key"))
            if nk in {r["key"] for r in catalog} or nk in proposals:
                continue
            cand = entity_match.find_candidates(
                e.get("name"), nk, catalog, k=3,
                fuzzy_floor=FUZZY_FLOOR, cosine_floor=COSINE_FLOOR)
            if cand:
                continue  # likely already present under a variant — skip, not new
            proposals[nk] = {
                "name": e.get("name"), "canonical_key": nk, "type": e.get("type"),
                "one_liner": e.get("one_liner"), "context": e.get("context"),
                "notability": e.get("notability"), "episode": meta.get("number"),
            }
    return list(proposals.values())


# --------------------------------------------------------------------------
# Render + main
# --------------------------------------------------------------------------
def write_txt(plan):
    lines = ["# Backfill cleanup proposals (review, then apply_backfill.py --confirm)\n"]
    lines.append(f"## MERGES ({len(plan['merges'])})")
    for m in plan["merges"]:
        losers = "  +  ".join(f'"{n}"' for n in m["loser_names"])
        lines.append(f'KEEP "{m["canonical_name"]}" (key={m["canonical_key"]}) '
                     f'[{m["confidence"]}]  <=  {losers}')
        if m["reason"]:
            lines.append(f'    reason: {m["reason"]}')
    lines.append(f"\n## RENAMES ({len(plan['renames'])})")
    for r in plan["renames"]:
        lines.append(f'"{r["old_name"]}" -> "{r["canonical_name"]}" '
                     f'(key={r["canonical_key"]}) [{r["confidence"]}] — {r["reason"]}')
    lines.append(f"\n## NEW ENTITIES ({len(plan['new_entities'])})")
    for e in plan["new_entities"]:
        lines.append(f'+ "{e["name"]}" [{e["type"]}] (ep {e.get("episode")}) '
                     f'— {e.get("one_liner") or ""}')
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Generate entity-cleanup proposals (no writes).")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--no-name-review", action="store_true", help="skip standalone rename pass")
    ap.add_argument("--recover-missed", action="store_true",
                    help="re-extract transcripts to find missed entities (expensive)")
    args = ap.parse_args()

    # The merge pass is meaningless without the show's clustering prompt — refuse up
    # front rather than spend LLM calls on a prompt-less system_instruction.
    if not BACKFILL_PROMPT.strip():
        raise SystemExit(
            f"SHOW={os.getenv('SHOW', 'demo')!r} has no shows/<show>/backfill.txt — the "
            "archive-cleanup clustering prompt. This stage is opt-in per podcast: add "
            "that file (see shows/demo/backfill.txt) to enable it."
        )

    client = _client()
    gclient = genai.Client(http_options=types.HttpOptions(timeout=HTTP_TIMEOUT_MS))
    print("Loading Entities archive...")
    catalog = load_catalog(client)
    print(f"  {len(catalog)} entities")

    print("Embedding + clustering duplicate candidates...")
    try:
        entity_match.refresh_embeddings(gclient, catalog)
    except Exception as e:  # noqa: BLE001 - fuzzy-only fallback
        print(f"  [embeddings] unavailable, fuzzy-only clustering: {e}")
    clusters = cluster_duplicates(catalog)
    print(f"  {len(clusters)} candidate clusters")

    merges = resolve_clusters(gclient, clusters, args.model)
    print(f"  {len(merges)} confirmed merges")

    renames = []
    if not args.no_name_review:
        print("Reviewing standalone names for STT garble...")
        renames = review_names(gclient, catalog, args.model)
        print(f"  {len(renames)} rename proposals")

    new_entities = []
    if args.recover_missed:
        print("Recovering missed entities (re-extracting transcripts)...")
        new_entities = recover_missed(gclient, catalog, args.model)
        print(f"  {len(new_entities)} candidate new entities")

    plan = {"merges": merges, "renames": renames, "new_entities": new_entities}
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    write_txt(plan)
    print(f"\nWrote {OUT_JSON} and {OUT_TXT}. Review, then: "
          "PYTHONPATH=. ./venv/bin/python scripts/apply_backfill.py --confirm")


if __name__ == "__main__":
    main()
