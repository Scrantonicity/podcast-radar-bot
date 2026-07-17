"""resolve_entities.py — the entity resolution pass (prevention).

Runs AFTER extract.extract, BEFORE notion_bridge.process_episode. For each freshly
extracted entity it:
  1. finds candidate matches among existing DB entities (entity_match: translit +
     fuzzy + embedding),
  2. asks Gemini (model knowledge only — no web) to, per entity: confirm it is a real
     substantive entity, correct STT mis-hears to the true name, emit a clean
     canonical_key (well-known form, no subtitle), and decide whether it is the SAME
     as one of the supplied candidates (→ reuse that key) or new,
  3. rewrites each entity's name/canonical_key accordingly, records the pre-correction
     spelling as an `alias`, and drops non-entities.

The resolver prompt is per-show: shows/<name>/resolve.txt. A show WITHOUT that file
skips this stage entirely (no-op), so it is opt-in per podcast.

Fail-open: any error (no API key, API failure, bad JSON) logs a warning and returns the
entities unchanged — resolution must never break the pipeline.
"""

import json
import os
import time

from google import genai
from google.genai import types
from google.genai import errors as genai_errors

import config
import entity_match
from extract import (normalize_key, RETRYABLE_CODES, MAX_API_RETRIES, MAX_BACKOFF,
                     MAX_TOKENS)
from show_loader import STRINGS, RESOLVE_PROMPT

RESOLVE_MODEL = config.RESOLVE_MODEL

# Max existing-entity candidates shown to the model per extracted entity.
MAX_CANDIDATES = 6

RESOLVE_SCHEMA = {
    "type": "object",
    "properties": {
        "resolutions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "name": {"type": "string"},
                    "canonical_key": {"type": "string"},
                    "matched_key": {"type": "string", "nullable": True},
                    "drop": {"type": "boolean"},
                    "alias": {"type": "string", "nullable": True},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["i", "name", "canonical_key", "matched_key", "drop",
                             "alias", "confidence"],
            },
        },
    },
    "required": ["resolutions"],
}


def _candidates_for(entities, index, client):
    """Return, per entity index, a list of candidate dicts. Uses fuzzy always and
    embeddings when available (best-effort; embedding failure -> fuzzy-only)."""
    catalog = entity_match.catalog_from_index(index)
    query_vecs = [None] * len(entities)
    if catalog and os.getenv("GOOGLE_API_KEY"):
        try:
            entity_match.refresh_embeddings(client, catalog)
            names = [e.get("name") or e.get("canonical_key") or "" for e in entities]
            query_vecs = entity_match.embed_texts(client, names)
        except Exception as e:  # noqa: BLE001 - embeddings are optional
            print(f"  [resolve] embeddings unavailable, fuzzy-only: {e}")
    cands = []
    for e, qv in zip(entities, query_vecs):
        cands.append(entity_match.find_candidates(
            e.get("name"), e.get("canonical_key"), catalog, query_vec=qv,
            k=MAX_CANDIDATES))
    return cands


def _call_resolver(client, items, model):
    payload = (f"{STRINGS.resolve_items_prefix}\n"
               + json.dumps(items, ensure_ascii=False, indent=1))
    cfg = types.GenerateContentConfig(
        system_instruction=RESOLVE_PROMPT,
        response_mime_type="application/json",
        response_schema=RESOLVE_SCHEMA,
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
            raise
    obj = json.loads(resp.text or "{}")
    return {int(r["i"]): r for r in obj.get("resolutions", []) if "i" in r}


def resolve(entities, index, client=None, model=None):
    """Resolve extracted entities against the existing DB. Mutates + returns
    (entities, notes) where notes is a list of human-readable low-confidence /
    correction messages for the private preview. Fail-open on any error.

    No-op when the active show has no resolve.txt prompt.
    """
    if not entities:
        return entities, []
    if not RESOLVE_PROMPT.strip():
        # Show hasn't opted into the resolution stage.
        return entities, []
    model = model or RESOLVE_MODEL
    if not os.getenv("GOOGLE_API_KEY"):
        print("  [resolve] GOOGLE_API_KEY not set — skipping resolution")
        return entities, []
    client = client or genai.Client()

    try:
        cands = _candidates_for(entities, index, client)
        items = []
        for i, (e, cand) in enumerate(zip(entities, cands)):
            items.append({
                "i": i,
                "name": e.get("name"),
                "canonical_key": e.get("canonical_key"),
                "type": e.get("type"),
                "one_liner": e.get("one_liner"),
                "context": e.get("context"),
                "candidates": [{"key": c["key"], "name": c["name"], "type": c["type"]}
                               for c in cand],
            })
        resolutions = _call_resolver(client, items, model)
    except Exception as e:  # noqa: BLE001 - resolution must never break the pipeline
        print(f"  [resolve] failed, keeping raw extraction: {e}")
        return entities, []

    existing_keys = set(index.keys())
    kept, notes = [], []
    for i, e in enumerate(entities):
        r = resolutions.get(i)
        if not r:
            kept.append(e)
            continue
        if r.get("drop"):
            notes.append(STRINGS.resolve_note_dropped.format(name=e.get("name")))
            continue
        orig_name = e.get("name")
        # Corrected name.
        new_name = (r.get("name") or "").strip() or orig_name
        # Key: prefer a matched existing key (folds into that page); else the model's
        # canonical_key; normalize either way so it can't fragment on punctuation.
        matched = (r.get("matched_key") or "").strip()
        if matched and normalize_key(matched) in existing_keys:
            e["canonical_key"] = normalize_key(matched)
            notes.append(STRINGS.resolve_note_merged.format(
                orig=orig_name, target=index[e["canonical_key"]].get("name"),
                confidence=r.get("confidence")))
        else:
            e["canonical_key"] = normalize_key(r.get("canonical_key")) or e.get("canonical_key")
        # Alias to preserve: the model's suggested alias, or the pre-correction name.
        alias = (r.get("alias") or "").strip()
        if not alias and new_name != orig_name:
            alias = orig_name
        if alias:
            e["alias"] = alias
        if new_name != orig_name:
            notes.append(STRINGS.resolve_note_renamed.format(
                orig=orig_name, new=new_name, confidence=r.get("confidence")))
        e["name"] = new_name
        if r.get("confidence") == "low":
            notes.append(STRINGS.resolve_note_low_conf.format(
                name=new_name, key=e["canonical_key"]))
        kept.append(e)

    # A resolver-driven merge can collapse two extracted entities onto one key; reuse
    # extract's within-episode merge so downstream sees a single row per key.
    from extract import _merge_within_episode
    kept = _merge_within_episode(kept)
    return kept, notes
