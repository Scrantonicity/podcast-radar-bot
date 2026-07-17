#!/usr/bin/env python3
"""auto_review.py — the weekly auto pipeline with a human approval gate.

For one episode (newest by default):
  1. transcribe once (cached),
  2. extract with the configured extraction model,
  3. WRITE Notion (episode + entities + Learn links) — channel post suppressed,
  4. build the exact channel digest and send it to the PRIVATE chat with inline
     Approve / Reject buttons.

Nothing reaches the public channel here. approval_poller.py reacts to the Approve
tap and copies the message to the channel. Notion is written now (before approval)
so the DB is always current; only the public broadcast waits for the tap.

  python auto_review.py                         # newest episode
  python auto_review.py --episode 2             # 2nd newest
  python auto_review.py --no-notion --chat-id 123   # test the private message only
"""

import argparse
import sys

import config
import extract
import feed
import notify
import notion_bridge as nb
import resolve_entities
import transcribe
from friday_preview import _stamp_returning
from show_loader import SHOW, STRINGS

MODEL = config.EXTRACTION_MODEL


def main():
    ap = argparse.ArgumentParser(description="Weekly auto-review: Notion + private approval msg")
    ap.add_argument("--episode", type=int, default=1, help="1 = newest (default 1)")
    ap.add_argument("--model", default=MODEL, help=f"extraction model (default {MODEL})")
    ap.add_argument("--no-notion", action="store_true", help="skip Notion write (testing)")
    ap.add_argument("--chat-id", help="override private chat id (testing)")
    ap.add_argument("--no-send", action="store_true", help="build only; do not send Telegram")
    ap.add_argument("--force", action="store_true",
                    help="reprocess even if the episode is already in Notion")
    args = ap.parse_args()

    episodes = feed.list_episodes()  # oldest -> newest
    idx = len(episodes) - args.episode
    if idx < 0 or idx >= len(episodes):
        sys.exit(f"--episode {args.episode} out of range (feed has {len(episodes)})")
    meta = episodes[idx]
    guid = meta.get("guid")
    print(f"Episode #{meta.get('number')} — {meta.get('title')!r} (guid={guid})")

    client = nb._client()
    # Reprocess safeguard — BEFORE transcription. Speechmatics costs money and the CI
    # runner has no transcript cache, so a run on an already-done episode would re-hit
    # the transcript API, re-upsert Notion, and re-send a private draft. Skip if this
    # episode is already in Notion (by guid) or its number isn't newer than the newest
    # episode already stored. --force overrides for a deliberate re-run.
    existing = nb._find_episode_by_guid(client, guid)
    ep_numbers = nb._load_episode_numbers(client)
    number = int(meta["number"]) if str(meta.get("number") or "").isdigit() else None
    newest_stored = max(ep_numbers.values()) if ep_numbers else None
    already = existing is not None or (
        number is not None and newest_stored is not None and number <= newest_stored)
    if already and not args.force:
        print(f"Episode #{meta.get('number')} already processed "
              f"(in Notion; newest stored=#{newest_stored}) — skipping. "
              f"Use --force to override.")
        return

    print("Transcribing (cached if already done)...")
    text = transcribe.get_transcript(meta)
    print(f"  {len(text)} chars")

    # Returning-markers from CURRENT Notion state, before this episode is written.
    index = nb._load_entities_index(client)
    current_page_id = existing["id"] if existing else None

    print(f"=== extract: {args.model} ===")
    contract = extract.extract(text, episode_meta=meta, model=args.model, use_cache=True)
    entities = contract.get("entities", [])

    # Resolution pass: correct STT-garbled names + fold variants onto existing DB
    # entities BEFORE anyone (Notion, the preview) sees them. Runs on the SAME index
    # already loaded for returning-markers. Fail-open (returns raw entities on error);
    # a no-op for shows without a resolve.txt prompt.
    print("=== resolve entities ===")
    entities, notes = resolve_entities.resolve(entities, index)
    contract["entities"] = entities
    for n in notes:
        print(f"  {n}")

    _stamp_returning(entities, index, ep_numbers, current_page_id)
    msg = notify.build_telegram_message(contract["episode"], entities)
    if notes:
        msg += f"\n\n{STRINGS.resolve_preview_header}\n" + "\n".join(notes[:15])
    print(f"  entities={len(entities)}  message={len(msg)} chars")

    # Notion FIRST (channel post suppressed); idempotent upsert.
    if not args.no_notion:
        config.ENABLE_TELEGRAM = False
        res = nb.process_episode(
            contract, transcript_path=transcribe.transcript_path(guid), client=client)
        print(f"  Notion -> {res['status']}  {res.get('episode_url') or ''}")
    else:
        print("  [no-notion] skipped Notion write")

    if args.no_send:
        print("  [no-send] built message; not sending")
        return

    result = notify.send_approval_request(msg, guid, chat_id=args.chat_id)
    print(f"  approval request sent to private chat (message_id={result.get('message_id')})")
    print("Awaiting your Approve tap — approval_poller.py will release it to the channel.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — never fail silently on the weekly auto run
        import html
        notify.send_alert(
            STRINGS.alert_auto_review_failed_template.format(show=SHOW.display_name)
            + f"{html.escape(str(e)[:400])}"
        )
        raise
