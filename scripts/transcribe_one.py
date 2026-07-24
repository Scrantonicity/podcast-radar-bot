"""transcribe_one.py — transcribe ONE episode to a text file, nothing else.

The onboarding needs a sample transcript *before* the entity taxonomy exists (you
derive the taxonomy from the sample — see ONBOARDING.md Step 3/4). The full pipeline
(`main.py --episode N`) also extracts and writes Notion, which needs a finished
prompt + Notion wiring you don't have yet. This helper stops right after
transcription: feed → Speechmatics → a `.txt` you can read.

Only needs a show with a feed + `stt_language` set (identity, no taxonomy) and
`SPEECHMATICS_API_KEY` in `.env`. Transcripts are cached by GUID, so re-running is free.

Run:  SHOW=<name> python scripts/transcribe_one.py            # newest episode
      SHOW=<name> python scripts/transcribe_one.py --episode 3 --out sample.txt
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import feed
import transcribe


def main():
    ap = argparse.ArgumentParser(description="Transcribe one episode to a text file.")
    ap.add_argument("--episode", type=int, default=1,
                    help="episode number, 1 = newest (default 1)")
    ap.add_argument("--out", default="sample_transcript.txt",
                    help="output file (default sample_transcript.txt)")
    args = ap.parse_args()

    if not os.getenv("SPEECHMATICS_API_KEY"):
        sys.exit("SPEECHMATICS_API_KEY not set in .env — needed to transcribe.")

    episodes = feed.list_episodes()          # oldest-first
    if not episodes:
        sys.exit("Feed returned no episodes — check the show's feed_apple_id / feed_rss_url.")
    idx = len(episodes) - args.episode        # same indexing as main.py (1 = newest)
    if idx < 0 or idx >= len(episodes):
        sys.exit(f"--episode {args.episode} out of range (feed has {len(episodes)}).")

    meta = episodes[idx]
    print(f"Episode #{args.episode} (newest=1): {meta.get('title')}  [{meta.get('date')}]",
          file=sys.stderr)
    print("Transcribing via Speechmatics (cached by GUID; a re-run is free)…", file=sys.stderr)

    text = transcribe.get_transcript(meta)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)

    speakers = sorted(set(t for t in text.split() if t.startswith("[S") and t.endswith("]")))
    print(f"Wrote {len(text)} chars to {args.out}  (speaker tags seen: {', '.join(speakers) or 'none'})",
          file=sys.stderr)
    print("Next: read it, then derive the taxonomy — ONBOARDING.md Step 4.", file=sys.stderr)


if __name__ == "__main__":
    main()
