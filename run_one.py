"""run_one.py — end-to-end proof on ONE real episode.

Reads the real bake-off transcript, fetches RSS metadata for the same episode,
runs extract(), prints the contract for eyeballing, then (after you confirm)
pushes it into Notion via the bridge. Creates a REAL (non-test) episode page.

Run:  ./venv/bin/python run_one.py            # newest episode
      ./venv/bin/python run_one.py --episode 2
"""

import argparse
import collections
import json
import sys

import feedparser
import requests

import stt  # reuse resolve_feed_url() + the feed-parse pattern
import extract
import notion_bridge

TRANSCRIPT_FILE = "out_speechmatics.txt"


def build_episode_meta(n):
    """Fetch RSS metadata for the Nth-newest episode (1 = newest)."""
    feed_url = stt.resolve_feed_url()
    resp = requests.get(feed_url, timeout=60)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    entries = list(feed.entries)
    if not entries:
        raise RuntimeError("Feed has no entries")
    if all(getattr(e, "published_parsed", None) for e in entries):
        entries.sort(key=lambda e: e.published_parsed, reverse=True)
    if n < 1 or n > len(entries):
        raise RuntimeError(f"--episode {n} out of range (feed has {len(entries)})")
    entry = entries[n - 1]

    # date YYYY-MM-DD from published_parsed
    date = None
    if getattr(entry, "published_parsed", None):
        t = entry.published_parsed
        date = f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"

    # audio url from enclosure
    audio_url = None
    for enc in getattr(entry, "enclosures", []):
        href = enc.get("href")
        etype = (enc.get("type") or "").lower()
        if href and ("audio" in etype or href.lower().endswith(".mp3")):
            audio_url = href
            break
    if not audio_url and getattr(entry, "enclosures", []):
        audio_url = entry.enclosures[0].get("href")

    # episode number: itunes_episode if present, else the position from newest
    number = None
    if getattr(entry, "itunes_episode", None):
        try:
            number = int(entry.itunes_episode)
        except (TypeError, ValueError):
            number = None

    return {
        "number": number,
        "title": entry.get("title"),
        "date": date,
        "duration": getattr(entry, "itunes_duration", None),
        "audio_url": audio_url,
        "youtube_url": None,
        "guid": entry.get("id") or entry.get("guid"),
    }


def main():
    ap = argparse.ArgumentParser(description="One-episode transcript -> extract -> Notion proof")
    ap.add_argument("--episode", type=int, default=1, help="Nth-newest episode (default 1)")
    args = ap.parse_args()

    # 1. transcript
    try:
        with open(TRANSCRIPT_FILE, encoding="utf-8") as f:
            transcript = f.read()
    except OSError as e:
        sys.exit(f"ERROR reading {TRANSCRIPT_FILE}: {e}")
    print(f"Transcript: {TRANSCRIPT_FILE} ({len(transcript)} chars)")

    # 2. metadata
    meta = build_episode_meta(args.episode)
    print("Episode metadata:")
    print(json.dumps(meta, ensure_ascii=False, indent=2))

    # 3. extract
    print("\nExtracting entities (Gemini)... this may take a bit.")
    contract = extract.extract(transcript, episode_meta=meta)

    # 4. pretty-print + quick summary
    print("\n===== CONTRACT =====")
    print(json.dumps(contract, ensure_ascii=False, indent=2))

    ents = contract["entities"]
    counts = collections.Counter(e["type"] for e in ents)
    print("\n===== QUICK SUMMARY =====")
    print(f"summary: {contract['summary']}")
    print(f"total entities: {len(ents)}")
    print("by type:", dict(counts))
    print("name -> canonical_key:")
    for e in ents:
        by = ",".join(e.get("mentioned_by") or [])
        print(f"  {e['name']}  ->  {e['canonical_key']}   [{e['type']}] ({by})")

    # 5. STOP for confirmation — this creates a REAL Notion page.
    print("\n" + "=" * 50)
    print("This will create a REAL (non-test) episode page in Notion.")
    ans = input("Type 'yes' to push to Notion, anything else to abort: ").strip().lower()
    if ans != "yes":
        print("Aborted. Nothing written to Notion.")
        return

    # 6. push
    print("\nWriting to Notion...")
    result = notion_bridge.process_episode(contract, transcript_path=TRANSCRIPT_FILE)
    print(f"Status: {result['status']}")
    print(f"Notion page: {result.get('episode_url')}")


if __name__ == "__main__":
    main()
