#!/usr/bin/env python3
"""approve.py — after reviewing the private preview, commit ONE model's result.

Run only once you've picked a model from friday_preview.py's tagged messages:
  1. writes the chosen model's contract to Notion (episode + entities + transcript
     + Learn links) with the channel post SUPPRESSED, then
  2. posts the exact message bytes you reviewed (outbox/{guid}.{model}.txt) to the
     public channel — so the channel message is byte-identical to the preview.

  python approve.py --episode 1 --model <model>
  python approve.py --episode 1 --model <model> --notion-only   # skip channel
  python approve.py --episode 1 --model <model> --channel-only  # skip Notion
"""

import argparse
import json
import os
import sys

import config
import feed
import notify
import notion_bridge as nb
import transcribe
from friday_preview import BAKEOFF_DIR, OUTBOX_DIR, _safe


def main():
    ap = argparse.ArgumentParser(description="Commit a chosen model's preview to Notion + channel")
    ap.add_argument("--episode", type=int, default=1, help="1 = newest (default 1)")
    ap.add_argument("--model", required=True, help="model id chosen from the preview")
    ap.add_argument("--notion-only", action="store_true", help="write Notion, do not post to channel")
    ap.add_argument("--channel-only", action="store_true", help="post to channel, do not write Notion")
    ap.add_argument("--confirm-channel", action="store_true",
                    help="required to actually post to the PUBLIC channel (or set CONFIRM_CHANNEL=1)")
    args = ap.parse_args()

    episodes = feed.list_episodes()
    idx = len(episodes) - args.episode
    if idx < 0 or idx >= len(episodes):
        sys.exit(f"--episode {args.episode} out of range (feed has {len(episodes)})")
    guid = episodes[idx].get("guid")

    contract_path = os.path.join(BAKEOFF_DIR, f"{_safe(guid)}.{args.model}.json")
    outbox_path = os.path.join(OUTBOX_DIR, f"{_safe(guid)}.{args.model}.txt")
    if not os.path.exists(contract_path):
        sys.exit(f"No saved contract: {contract_path}\nRun friday_preview.py first.")
    if not os.path.exists(outbox_path):
        sys.exit(f"No saved message: {outbox_path}\nRun friday_preview.py first.")

    with open(contract_path, encoding="utf-8") as f:
        contract = json.load(f)
    with open(outbox_path, encoding="utf-8") as f:
        message = f.read()

    print(f"Approving episode #{episodes[idx].get('number')} with model {args.model}")

    # 1. Notion — channel post suppressed (we send the reviewed bytes ourselves below).
    if not args.channel_only:
        config.ENABLE_TELEGRAM = False
        client = nb._client()
        res = nb.process_episode(
            contract, transcript_path=transcribe.transcript_path(guid), client=client)
        print(f"  Notion -> {res['status']}  {res.get('episode_url') or ''}")

    # 2. Channel — post the EXACT bytes reviewed in the private preview.
    if not args.notion_only:
        if not config.TELEGRAM_CHAT_ID:
            sys.exit("TELEGRAM_CHAT_ID (the channel) not set — cannot post.")
        # Fail-safe: this posts to the PUBLIC channel with no approval gate. Require an
        # explicit opt-in so a workflow can't do it silently (see the ep61 one-off bug).
        confirm = args.confirm_channel or os.getenv("CONFIRM_CHANNEL", "").strip() in ("1", "true", "yes")
        if not confirm:
            print(f"  [dry-run] would post to PUBLIC channel {config.TELEGRAM_CHAT_ID}:")
            print("  " + "\n  ".join(message.splitlines()))
            sys.exit("Refusing to post: pass --confirm-channel or set CONFIRM_CHANNEL=1 to broadcast.")
        notify.send_telegram(message, allow_public=True)
        print(f"  posted to channel ({config.TELEGRAM_CHAT_ID})")

    print("Done.")


if __name__ == "__main__":
    main()
