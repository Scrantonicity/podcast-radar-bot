#!/usr/bin/env python3
"""apply_backfill.py — apply a reviewed backfill_proposals.json to live Notion.

Reuses merge_entities' load_pages + merged_props + trash pattern. Dry-run by default;
pass --confirm to write. Idempotent-ish and reversible (losers -> Notion trash, 30d).

  PYTHONPATH=. ./venv/bin/python scripts/apply_backfill.py                  # dry run: print the plan
  PYTHONPATH=. ./venv/bin/python scripts/apply_backfill.py --confirm        # execute against live Notion
  PYTHONPATH=. ./venv/bin/python scripts/apply_backfill.py --confirm --only merges
"""

import argparse
import json
import os
import time

import config
import notion_bridge as nb
from merge_entities import load_pages, merged_props
from notion_bridge import _client, _rt, _retry, trash_page, WRITE_DELAY
from extract import normalize_key

# Scripts live in scripts/; the proposals file is written to the repo root by
# backfill_cleanup.py, so resolve from the parent dir (not __file__'s dir).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROPOSALS = os.path.join(ROOT, "backfill_proposals.json")


def _alias_props(existing_aliases, new_aliases, canonical_name):
    """Merged, deduped alias rich_text prop (drop the canonical name itself)."""
    merged = list(existing_aliases)
    for a in new_aliases:
        if a and a != canonical_name and a not in merged:
            merged.append(a)
    return {"Aliases": {"rich_text": _rt("\n".join(merged))}} if merged else {}


def apply_merges(client, merges, by_id, has_aliases, confirm):
    for m in merges:
        surv = by_id.get(m["survivor_id"])
        losers = [by_id[i] for i in m["loser_ids"] if i in by_id]
        if not surv or not losers:
            print(f"  [skip merge] missing pages for {m['canonical_name']}")
            continue
        # Dedup-only: fold episodes/mentions/fills, but KEEP the survivor's existing
        # display Name and Key (no rename — preserves the show's native-script-first
        # naming). Loser + canonical variants are recorded as aliases so they resolve
        # here in future runs.
        props = merged_props(surv, losers)
        if has_aliases:
            variants = (m.get("aliases") or []) + [m.get("canonical_name")]
            props.update(_alias_props([], variants, surv["name"]))
        print(f'  KEEP "{surv["name"]}"  <= ' +
              "  +  ".join(f'"{lo["name"]}"' for lo in losers))
        if confirm:
            _retry(client.pages.update, page_id=surv["id"], properties=props)
            time.sleep(WRITE_DELAY)
            for lo in losers:
                # GUARDRAIL: trash via the bridge helper (it sends in_trash=True) —
                # recoverable from Notion trash for 30 days. Never hand-roll the
                # legacy archive flag; this API version rejects it.
                trash_page(client, lo["id"])
                time.sleep(WRITE_DELAY)


def apply_renames(client, renames, by_id, has_aliases, confirm):
    for r in renames:
        pg = by_id.get(r["page_id"])
        if not pg:
            print(f"  [skip rename] missing page {r['page_id']}")
            continue
        props = {"Name": {"title": _rt(r["canonical_name"])},
                 "Key": {"rich_text": _rt(r["canonical_key"])}}
        if has_aliases and r["old_name"] and r["old_name"] != r["canonical_name"]:
            props.update(_alias_props([], [r["old_name"]], r["canonical_name"]))
        print(f'  RENAME "{r["old_name"]}" -> "{r["canonical_name"]}"')
        if confirm:
            _retry(client.pages.update, page_id=pg["id"], properties=props)
            time.sleep(WRITE_DELAY)


def apply_new_entities(client, new_entities, confirm):
    """Create archive-only entity pages (no episode link — these are additions the old
    extraction missed, not a new episode run). Skips any key already in the DB."""
    if not new_entities:
        return
    index = nb._load_entities_index(client)
    has_notability = nb._has_property(client, config.NOTION_ENTITIES_DS_ID, "Notability")
    has_context = nb._has_property(client, config.NOTION_ENTITIES_DS_ID, "Context")
    from extract import ACTION_BY_TYPE
    for e in new_entities:
        key = normalize_key(e.get("canonical_key"))
        if key in index:
            print(f'  [skip new] "{e.get("name")}" — key {key} already exists')
            continue
        etype = e.get("type")
        props = {
            "Name": {"title": _rt(e.get("name"))},
            "Key": {"rich_text": _rt(key)},
            "Mentions": {"number": 1},
        }
        if etype:
            props["Type"] = {"select": {"name": etype}}
        if has_notability and e.get("notability"):
            props["Notability"] = {"number": e["notability"]}
        if e.get("one_liner"):
            props["One-liner"] = {"rich_text": _rt(e["one_liner"])}
        if has_context and e.get("context"):
            props["Context"] = {"rich_text": _rt(e["context"])}
        action = ACTION_BY_TYPE.get(etype)
        if action:
            props["Action"] = {"select": {"name": action}}
        print(f'  NEW "{e.get("name")}" [{etype}]')
        if confirm:
            _retry(client.pages.create,
                   parent={"type": "data_source_id",
                           "data_source_id": config.NOTION_ENTITIES_DS_ID},
                   properties=props)
            time.sleep(WRITE_DELAY)
            index[key] = {"page_id": None}  # guard against dup within this run


def main():
    ap = argparse.ArgumentParser(description="Apply reviewed backfill proposals to Notion.")
    ap.add_argument("--confirm", action="store_true", help="write to Notion (else dry run)")
    ap.add_argument("--only", choices=["merges", "renames", "new_entities"],
                    help="apply only one section")
    args = ap.parse_args()

    with open(PROPOSALS, encoding="utf-8") as f:
        plan = json.load(f)

    client = _client()
    # Only add the column when actually writing — a dry run must touch nothing, not
    # even the schema.
    if args.confirm:
        try:
            nb.ensure_aliases_property(client)
        except Exception as e:  # noqa: BLE001 - aliases are optional; merges still apply
            print(f"  [aliases] could not ensure property, skipping aliases: {e}")
    has_aliases = nb._has_property(client, config.NOTION_ENTITIES_DS_ID, "Aliases")
    pages = load_pages(client)
    by_id = {p["id"]: p for p in pages}
    mode = "APPLY" if args.confirm else "DRY RUN"
    print(f"Loaded {len(pages)} pages. Mode: {mode}. Aliases prop: {has_aliases}\n")

    if args.only in (None, "merges"):
        print(f"MERGES ({len(plan.get('merges', []))}):")
        apply_merges(client, plan.get("merges", []), by_id, has_aliases, args.confirm)
    if args.only in (None, "renames"):
        print(f"\nRENAMES ({len(plan.get('renames', []))}):")
        apply_renames(client, plan.get("renames", []), by_id, has_aliases, args.confirm)
    if args.only in (None, "new_entities"):
        print(f"\nNEW ENTITIES ({len(plan.get('new_entities', []))}):")
        apply_new_entities(client, plan.get("new_entities", []), args.confirm)

    if not args.confirm:
        print("\nDry run only. Re-run with --confirm to write to Notion.")
    else:
        print("\nDone.")


if __name__ == "__main__":
    main()
