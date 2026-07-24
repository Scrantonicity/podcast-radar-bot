"""taxonomy_review.py — surface new entity categories the show has outgrown.

The entity taxonomy is set per show, but a show that runs for a while drifts: new
kinds of things keep coming up that fit none of the existing types, so the model
parks them in `other` and names the gap in `suggested_category` (see the extraction
prompt). This script aggregates those signals across every cached episode and, once a
proposed category recurs past a threshold, reports it so you can PROMOTE it to a real
type — the taxonomy adapts over time instead of being frozen from episode one.

Nothing here changes the taxonomy on its own (same human-in-the-loop rule as posting):
it reports candidates and tells you exactly what to add. With --telegram it sends the
report to your private alert chat.

Run:  SHOW=<name> python scripts/taxonomy_review.py
      SHOW=<name> python scripts/taxonomy_review.py --min-entities 4 --min-episodes 3 --telegram
"""

import argparse
import glob
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import extract  # for CACHE_DIR (extractions/)


def _load(extractions_dir):
    cands = defaultdict(lambda: {"count": 0, "episodes": set(), "examples": []})
    other_total = 0
    n_files = 0
    for path in sorted(glob.glob(os.path.join(extractions_dir, "*.json"))):
        try:
            contract = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        n_files += 1
        ep = os.path.basename(path)[:-5]
        for e in contract.get("entities", []):
            if e.get("type") != "other":
                continue
            other_total += 1
            sc = e.get("suggested_category")
            if not sc:
                continue
            c = cands[sc]
            c["count"] += 1
            c["episodes"].add(ep)
            if e.get("name") and len(c["examples"]) < 6:
                c["examples"].append(e["name"])
    return cands, other_total, n_files


def _report(cands, other_total, n_files, min_entities, min_episodes):
    lines = [f"🗂️ Taxonomy review — {n_files} episode(s) scanned, {other_total} entity(ies) in `other`.", ""]
    ranked = sorted(cands.items(),
                    key=lambda kv: (len(kv[1]["episodes"]), kv[1]["count"]), reverse=True)
    promotable = [(k, v) for k, v in ranked
                  if v["count"] >= min_entities and len(v["episodes"]) >= min_episodes]

    if promotable:
        lines.append(f"✅ Candidates to PROMOTE (≥{min_entities} entities across ≥{min_episodes} episodes):")
        for k, v in promotable:
            lines.append(f"  • `{k}` — {v['count']} entities in {len(v['episodes'])} episodes "
                         f"(e.g. {', '.join(v['examples'][:5])})")
        lines.append("")
        lines.append("To promote one, add it in TWO places (they must agree) and re-run:")
        lines.append("  1. shows/<name>/config.py — add the slug to `entity_types` (+ a")
        lines.append("     tg_sections/notion_type_labels entry, and action_by_type if it needs an Action).")
        lines.append("  2. shows/<name>/prompt.txt — add the new type to the allowed-types list with a")
        lines.append("     one-line definition, so the model classifies it directly instead of via `other`.")
        lines.append("  Notion needs nothing — the Type select auto-creates the option on the next write.")
    else:
        lines.append(f"No category has crossed the threshold yet "
                     f"(≥{min_entities} entities across ≥{min_episodes} episodes). Nothing to promote.")

    below = [(k, v) for k, v in ranked if (k, v) not in promotable]
    if below:
        lines.append("")
        lines.append("Watching (below threshold):")
        for k, v in below[:8]:
            lines.append(f"  · `{k}` — {v['count']} in {len(v['episodes'])} ep")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Review `other` entities for new-category candidates.")
    ap.add_argument("--min-entities", type=int, default=3,
                    help="min entities carrying a suggested_category to propose it (default 3)")
    ap.add_argument("--min-episodes", type=int, default=2,
                    help="min distinct episodes it must span (default 2)")
    ap.add_argument("--extractions", default=extract.CACHE_DIR,
                    help="extractions cache dir (default: extractions/)")
    ap.add_argument("--telegram", action="store_true",
                    help="also send the report to the private alert chat")
    args = ap.parse_args()

    if not os.path.isdir(args.extractions):
        sys.exit(f"No extractions dir at {args.extractions} — run the pipeline on some episodes first.")

    cands, other_total, n_files = _load(args.extractions)
    if n_files == 0:
        sys.exit(f"No cached extractions found in {args.extractions}.")

    report = _report(cands, other_total, n_files, args.min_entities, args.min_episodes)
    print(report)

    if args.telegram:
        try:
            import notify
            notify.send_alert(report)
            print("\n[sent to private alert chat]", file=sys.stderr)
        except Exception as e:  # noqa: BLE001 - reporting must not crash
            print(f"\n[telegram send failed: {e}]", file=sys.stderr)


if __name__ == "__main__":
    main()
