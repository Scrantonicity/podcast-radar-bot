#!/usr/bin/env python3
"""friday_preview.py — channel-safe multi-model preview to the PRIVATE chat.

Runs the real pipeline path for ONE episode, but instead of touching Notion or the
public channel it:
  1. transcribes once (single Speechmatics charge; cached for reuse),
  2. extracts the SAME transcript with each candidate Gemini model,
  3. builds the exact Telegram digest for each model and sends it to the private
     chat (TELEGRAM_ALERT_CHAT_ID), tagged with the model name,
  4. saves each model's contract (extractions_bakeoff/) and the exact message bytes
     (outbox/) so approve.py can later post the chosen one to the channel verbatim.

NOTHING is written to Notion and NOTHING is posted to the channel. Review the
tagged messages on your phone, pick a model, then run approve.py.

  python friday_preview.py --episode 1            # 1 = newest
  python friday_preview.py --episode 1 --models gemini-3-flash,gemini-3.5-flash
"""

import argparse
import collections
import json
import os
import re
import sys

import config
import extract
import feed
import notify
import notion_bridge as nb
import transcribe

# Flash generations the API currently serves for generateContent (1.5 and 2.0 are retired;
# "3" is the preview id). Each re-extracts the same transcript so the rendered digest reflects
# that model's headline / entity picks / notability. Unavailable ids degrade gracefully
# (per-model FAILED notice, not a crash). Manual bake-off tool only; prod uses 3.5 via auto_review.
DEFAULT_MODELS = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-3.5-flash"]

BAKEOFF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extractions_bakeoff")
OUTBOX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outbox")


def _safe(guid):
    return re.sub(r"[^\w.-]", "_", str(guid))


def _stamp_returning(entities, index, ep_numbers, current_page_id):
    """Mark each entity's is_returning / earliest_episode exactly as _upsert_entity
    would, from the live Notion state — without writing anything. The current
    episode's own page (if it already exists) is excluded so a re-run isn't counted
    as a prior mention."""
    for e in entities:
        key = e.get("canonical_key")
        cur = index.get(key)
        if not cur:
            e["is_returning"] = False
            e["earliest_episode"] = None
            continue
        prior_pages = cur["episodes"] - ({current_page_id} if current_page_id else set())
        e["is_returning"] = bool(prior_pages)
        prior_nums = [ep_numbers[p] for p in prior_pages if ep_numbers.get(p) is not None]
        e["earliest_episode"] = min(prior_nums) if prior_nums else None


def _send_private(text):
    """Send to the private alert chat via send_telegram (channel never touched)."""
    if not config.TELEGRAM_ALERT_CHAT_ID:
        sys.exit("TELEGRAM_ALERT_CHAT_ID not set — can't preview to the private chat.")
    config.TELEGRAM_CHAT_ID = config.TELEGRAM_ALERT_CHAT_ID  # redirect every send here
    # allow_public satisfies send_telegram's fail-closed guard; the line above has
    # already redirected TELEGRAM_CHAT_ID to the PRIVATE alert chat, so this never
    # reaches the public channel.
    notify.send_telegram(text, allow_public=True)


def main():
    ap = argparse.ArgumentParser(description="Multi-model preview to the private chat")
    ap.add_argument("--episode", type=int, default=1, help="1 = newest (default 1)")
    ap.add_argument("--models", help="comma-separated model ids (default: the 3 candidates)")
    ap.add_argument("--no-send", action="store_true",
                    help="build + save only; do not send to Telegram")
    args = ap.parse_args()

    models = [m.strip() for m in args.models.split(",")] if args.models else DEFAULT_MODELS

    episodes = feed.list_episodes()  # oldest -> newest
    idx = len(episodes) - args.episode
    if idx < 0 or idx >= len(episodes):
        sys.exit(f"--episode {args.episode} out of range (feed has {len(episodes)})")
    meta = episodes[idx]
    guid = meta.get("guid")
    print(f"Episode #{meta.get('number')} — {meta.get('title')!r} (guid={guid})")

    # Transcript ONCE — shared across every model (single Speechmatics charge).
    print("Transcribing (cached if already done)...")
    text = transcribe.get_transcript(meta)
    print(f"  {len(text)} chars")

    # Live Notion state for faithful 🔁 returning-markers — read only.
    client = nb._client()
    index = nb._load_entities_index(client)
    ep_numbers = nb._load_episode_numbers(client)
    existing = nb._find_episode_by_guid(client, guid)
    current_page_id = existing["id"] if existing else None

    os.makedirs(BAKEOFF_DIR, exist_ok=True)
    os.makedirs(OUTBOX_DIR, exist_ok=True)

    for m in models:
        print(f"\n=== model: {m} ===")
        try:
            contract = extract.extract(text, episode_meta=meta, model=m, use_cache=False)
        except Exception as e:  # noqa: BLE001
            print(f"  !!! extract failed for {m}: {e}")
            if not args.no_send:
                _send_private(f"🔬 <b>{m}</b> — extraction FAILED:\n{str(e)[:300]}")
            continue

        entities = contract.get("entities", [])
        _stamp_returning(entities, index, ep_numbers, current_page_id)

        spread = dict(sorted(collections.Counter(
            e.get("notability") for e in entities).items(), reverse=True))
        print(f"  entities={len(entities)}  notability={spread}")

        msg = notify.build_telegram_message(contract["episode"], entities)

        with open(os.path.join(BAKEOFF_DIR, f"{_safe(guid)}.{m}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(contract, f, ensure_ascii=False, indent=2)
        with open(os.path.join(OUTBOX_DIR, f"{_safe(guid)}.{m}.txt"), "w",
                  encoding="utf-8") as f:
            f.write(msg)

        if args.no_send:
            print("  [no-send] saved contract + message; not sending")
            continue

        # Tag header first (small), then the exact digest, so the 4096-char digest
        # is never truncated by the prefix.
        _send_private(f"🔬 <b>MODEL: {m}</b> | entities={len(entities)} | notability={spread}")
        _send_private(msg)
        print("  sent to private chat")

    print("\nDone. Review the tagged messages, then: "
          "python approve.py --episode {} --model <chosen>".format(args.episode))


if __name__ == "__main__":
    main()
