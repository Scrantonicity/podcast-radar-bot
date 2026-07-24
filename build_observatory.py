#!/usr/bin/env python3
"""build_observatory.py — render the archive as one self-contained HTML page.

Read-only over the episode cache; writes one file. Nothing here touches Notion,
Telegram, or the network, and it needs no API keys — so it is safe to run whenever,
and it runs in CI against fixtures.

    SHOW=demo python build_observatory.py --dry-run     # what would render, and why
    SHOW=demo python build_observatory.py               # -> dist/<show>_observatory.html

The theme and the words come from shows/<name>/observatory.py (optional — without
it you get a neutral dark page in plain English). The numbers always come from here.
See OBSERVATORY.md.

NOTE ON --extractions: the pipeline's extractions/ and transcripts/ caches live at
the repo root and are NOT per-show (extract.py, transcribe.py). If you run more than
one show from one checkout, both shows' episodes land in the same directory and a
plain build would silently mix them into one page. Point --extractions at the right
data when that applies to you.
"""

import argparse
import datetime
import glob
import json
import os
import sys

from observatory import assemble, stats as stats_mod
from observatory.defaults import resolve

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_EXTRACTIONS = os.path.join(HERE, "extractions")
DEFAULT_TRANSCRIPTS = os.path.join(HERE, "transcripts")


def load_episodes(dirname):
    eps, bad = [], []
    for path in sorted(glob.glob(os.path.join(dirname, "*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            bad.append((os.path.basename(path), str(e)))
            continue
        if not isinstance(data, dict) or "entities" not in data:
            bad.append((os.path.basename(path), "not an extraction contract"))
            continue
        eps.append(data)
    # A checkpoint written mid-run has no number; sort those last, not as 0.
    eps.sort(key=lambda e: ((e.get("episode") or {}).get("number") is None,
                            (e.get("episode") or {}).get("number") or 0))
    return eps, bad


def load_transcripts(dirname, episodes):
    """Only the transcripts belonging to THESE episodes, matched by guid.

    Globbing the directory instead would pull in every show that shares the cache
    and inflate the word counts with another podcast's words.
    """
    if not os.path.isdir(dirname):
        return {}
    out = {}
    for ep in episodes:
        guid = (ep.get("episode") or {}).get("guid")
        if not guid:
            continue
        path = os.path.join(dirname, f"{guid}.txt")
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    out[guid] = f.read()
            except OSError:
                pass
    return out


def _report(stats, report, obs, show, out_path):
    """What a human (or the AI writing observatory.py) needs to know before authoring
    copy: which sections will actually render, and what data is missing."""
    sec = stats["sections"]
    print(f"\nshow: {show.display_name}  ({report['episodes']} episodes, "
          f"{stats['totals']['entities']} entities)")
    print(f"transcripts matched: {report['transcripts_found']}/{report['episodes']}"
          + ("  (no transcripts -> the language section drops its word blocks)"
             if not report["transcripts_found"] else ""))

    print("\nsections:")
    reasons = {
        "globe": f"{len(stats['places'])} placed (needs 3)",
        "library": f"{len(stats['books'])} books/articles (needs 6)",
        "records": f"{len(stats['superlatives']['top'])} types with a leader",
        "funfacts": f"{len(stats['funfacts'])} facts (needs 4)",
        "hostface": (f"{len(stats['host_face']['hosts'])} of "
                     f"{stats['host_face']['hosts_available']} hosts with attribution "
                     f"(needs 2)"),
        "leaders": f"{len(stats['leaderboard'])} ranked types",
        "cloud": f"{len(stats['concepts'])} concepts (needs 12)",
        "pulse": f"{len(stats['timeline'])} episodes (needs 4)",
        "wordlab": (f"words={'yes' if sec.get('wordlab_words') else 'no'}, "
                    f"tickers={len(stats['tickers'])} (needs 8)"),
        "graph": f"{len(stats['graph']['edges'])} edges (needs 12)",
        "shoutouts": f"{len(stats['shoutouts'])} written in copy",
    }
    enabled_off = []
    for k, why in reasons.items():
        on = sec.get(k)
        flag = "ON " if on else "off"
        print(f"  {flag} {k:10s} {why}")
        if not on and getattr(obs.copy, k).enabled and k != "shoutouts":
            enabled_off.append(k)
    if enabled_off:
        print(f"\n  note: {', '.join(enabled_off)} are switched on in copy but have too "
              f"little data to render.\n        Don't spend words on them.")

    if report["ungeocoded"]:
        print(f"\nUNGEOCODED ({len(report['ungeocoded'])}) — these places won't plot. "
              f"Add coords to\nObservatory.extra_place_coords as {{key: [lat, lon]}}:")
        for key, n in report["ungeocoded"][:40]:
            print(f'  "{key}": [ , ],    # {n} mention(s)')

    missing_copy = [f for f, why in report["skipped_facts"] if why == "no copy"]
    other_skips = [(f, w) for f, w in report["skipped_facts"] if w != "no copy"]
    if missing_copy:
        print(f"\nfacts with no copy (add to Copy.funfact_copy): {', '.join(missing_copy)}")
    if other_skips:
        print("\nfacts skipped:")
        for fid, why in other_skips:
            print(f"  {fid:20s} {why}")

    rendered = [f["id"] for f in stats["funfacts"]]
    print(f"\nfacts rendering ({len(rendered)}): {', '.join(rendered)}")
    if out_path:
        print(f"\nwould write: {out_path}")


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Build the podcast observatory (a self-contained statistics page).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="The active show comes from the SHOW env var, same as the pipeline.",
    )
    p.add_argument("--extractions", default=DEFAULT_EXTRACTIONS,
                   help="directory of episode json (default: ./extractions)")
    p.add_argument("--transcripts", default=DEFAULT_TRANSCRIPTS,
                   help="directory of transcripts, matched by guid (default: ./transcripts)")
    p.add_argument("--out", default=None,
                   help="output html (default: dist/<show>_observatory.html)")
    p.add_argument("--stats-json", default=None,
                   help="also write the computed STATS as json (for debugging)")
    p.add_argument("--dry-run", action="store_true",
                   help="report what would render and why; write nothing")
    p.add_argument("--no-vendor", action="store_true",
                   help="skip inlining d3/topojson/atlas — a fast, tiny, non-working page")
    args = p.parse_args(argv)

    # Imported here, not at module scope: show_loader reads .env and picks the show,
    # and --help shouldn't require either.
    from show_loader import SHOW, SHOW_NAME, OBSERVATORY

    if not os.path.isdir(args.extractions):
        p.error(f"no such directory: {args.extractions}\n"
                f"Run the pipeline first, or pass --extractions.")

    episodes, bad = load_episodes(args.extractions)
    for name, why in bad:
        print(f"  skipped {name}: {why}", file=sys.stderr)
    if not episodes:
        p.error(f"no episode json in {args.extractions}")

    transcripts = load_transcripts(args.transcripts, episodes)
    obs = resolve(SHOW, OBSERVATORY, n_episodes=len(episodes))
    stats, report = stats_mod.compute(episodes, transcripts, SHOW, obs)
    stats["meta"] = {
        "show": SHOW.display_name,
        "built": datetime.date.today().isoformat(),
        "episodes_dir": os.path.relpath(args.extractions, HERE),
    }

    out = args.out or os.path.join(HERE, "dist", f"{SHOW_NAME}_observatory.html")
    _report(stats, report, obs, SHOW, None if args.dry_run else out)
    if args.dry_run:
        if OBSERVATORY is None:
            print(f"\nshows/{SHOW_NAME}/observatory.py not found — this build would use "
                  f"the default\ntheme and English copy. See OBSERVATORY.md.")
        return 0

    if args.stats_json:
        with open(args.stats_json, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, separators=(",", ":"))
        print(f"wrote {args.stats_json}")

    html = assemble.build(stats, SHOW, obs, with_vendor=not args.no_vendor)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nwrote {out} ({len(html.encode('utf-8')) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
