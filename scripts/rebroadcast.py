"""rebroadcast.py — wipe the Telegram channel and re-post every episode in the
CURRENT minimalist format, oldest -> newest.

Why this exists: already-posted channel messages use the old layout. We have no
stored message_ids and main.py --backfill skips episodes already "done" in Notion,
so neither can re-issue the posts. This script is Telegram-only — it never reads or
writes Notion. It rebuilds each message from the cached extraction contract
(extractions/{guid}.json) using the exact same builder the live pipeline uses
(notify.build_telegram_message), and reproduces the 🔁 returning-marker by a clean
chronological pass over canonical_key (the same field _upsert_entity keys on).

Phases:
  0  ensure every feed episode has a cached contract (gap-fill missing ones), THEN
     hard-gate: if any is still missing, abort and delete NOTHING.
  1  delete every message in the channel (brute-force the message_id range, after a
     proactive admin/can_delete_messages rights check).
  2  re-post every episode oldest -> newest, silently (no push), 4s apart.

Safety: destructive + public. Requires --yes (or a typed REBROADCAST confirmation).
Use --dry-run first, and --chat-id <test> to rehearse against a throwaway channel.
"""

import argparse
import sys
import time

import requests

import config
import extract
import feed
import notify
import transcribe

BACKFILL_DELAY = 4       # seconds between posts (channel rate limit), local copy
DELETE_DELAY = 0.3       # base seconds between deleteMessage calls
PROBE_TEXT = "🧹"        # transient message used only to read the current max id

# deleteMessage descriptions that are benign (gap in the id range / unremovable
# service message) — skip and keep going. Anything else (esp. "not enough rights")
# must surface.
_DELETE_IGNORE = ("message to delete not found", "message can't be deleted")


def _tg(method, **payload):
    """POST a Telegram Bot API method, return (ok, body)."""
    r = requests.post(notify._api_url(method), json=payload, timeout=30)
    try:
        body = r.json()
    except ValueError:
        body = {}
    return r.status_code, body


# --------------------------------------------------------------------------
# Phase 0 — contracts
# --------------------------------------------------------------------------
def ensure_contracts(skip_extract):
    """Return [(meta, contract), ...] oldest->newest for every feed episode, after
    gap-filling any missing extraction. Hard-abort if a contract is still missing."""
    episodes = feed.list_episodes()  # oldest -> newest
    print(f"[phase0] feed has {len(episodes)} episode(s)")

    missing = [m for m in episodes if extract._load_checkpoint(m.get("guid")) is None]
    if missing and skip_extract:
        nums = ", ".join(str(m.get("number")) for m in missing)
        sys.exit(f"[phase0] ABORT: {len(missing)} episode(s) lack a cached contract "
                 f"and --skip-extract was set: [{nums}]")
    for m in missing:
        guid = m.get("guid")
        print(f"[phase0] extracting missing ep #{m.get('number')} (guid={guid})")
        text = transcribe.get_transcript(m)
        extract.extract(text, episode_meta=m)  # auto-caches

    pairs = []
    still_missing = []
    for m in episodes:
        contract = extract._load_checkpoint(m.get("guid"))
        if contract is None:
            still_missing.append(m)
        else:
            pairs.append((m, contract))
    if still_missing:
        nums = ", ".join(str(m.get("number")) for m in still_missing)
        sys.exit(f"[phase0] ABORT (nothing deleted): still missing contracts: [{nums}]")

    print(f"[phase0] OK — {len(pairs)} contract(s) ready; full repost is possible")
    return pairs


# --------------------------------------------------------------------------
# Phase 1 — delete
# --------------------------------------------------------------------------
def _assert_delete_rights():
    """Confirm the bot is an admin WITH can_delete_messages BEFORE touching the
    channel. Admins with this right can delete messages of any age."""
    code, me = _tg("getMe")
    if not me.get("ok"):
        sys.exit(f"[phase1] getMe failed ({code}): {me.get('description')}")
    bot_id = me["result"]["id"]

    code, cm = _tg("getChatMember", chat_id=config.TELEGRAM_CHAT_ID, user_id=bot_id)
    if not cm.get("ok"):
        sys.exit(f"[phase1] getChatMember failed ({code}): {cm.get('description')} — "
                 "is the bot a member/admin of the channel?")
    res = cm["result"]
    status = res.get("status")
    can_delete = res.get("can_delete_messages")
    if status not in ("administrator", "creator") or not can_delete:
        sys.exit(f"[phase1] ABORT: bot lacks delete rights (status={status}, "
                 f"can_delete_messages={can_delete}). Make it a channel admin with "
                 "the 'Delete Messages' permission, then re-run.")
    print(f"[phase1] rights OK (status={status}, can_delete_messages=True)")


def delete_all_messages():
    _assert_delete_rights()

    # Probe: bypass send_telegram (which discards message_id) — POST sendMessage
    # directly and read the current max id, silently.
    code, body = _tg("sendMessage", chat_id=config.TELEGRAM_CHAT_ID,
                     text=PROBE_TEXT, disable_notification=True)
    if not body.get("ok"):
        sys.exit(f"[phase1] probe sendMessage failed ({code}): {body.get('description')}")
    max_id = body["result"]["message_id"]
    print(f"[phase1] max message_id = {max_id}; deleting {max_id} -> 1")

    deleted = 0
    for mid in range(max_id, 0, -1):
        while True:  # retry loop only re-enters on 429
            code, body = _tg("deleteMessage", chat_id=config.TELEGRAM_CHAT_ID,
                             message_id=mid)
            if body.get("ok"):
                deleted += 1
                break
            desc = (body.get("description") or "").lower()
            if code == 429:
                retry_after = (body.get("parameters") or {}).get("retry_after", 3)
                time.sleep(retry_after + 1)
                continue
            if any(s in desc for s in _DELETE_IGNORE):
                break  # benign gap / unremovable — skip
            sys.exit(f"[phase1] ABORT deleting id={mid} ({code}): "
                     f"{body.get('description')}")
        if mid % 50 == 0:
            print(f"[phase1]   ...at id={mid} ({deleted} deleted so far)")
        time.sleep(DELETE_DELAY)
    print(f"[phase1] done — {deleted} message(s) deleted")


# --------------------------------------------------------------------------
# Phase 2 — rebroadcast
# --------------------------------------------------------------------------
def _prep_entities(entities, episode_number, seen):
    """Drop banned sponsors, then stamp is_returning/earliest_episode chronologically.
    Mirrors the live filter (extract) + _upsert_entity returning logic."""
    kept = []
    for e in entities:
        key = extract.normalize_key(e.get("canonical_key"))
        if key in extract.SPONSOR_BAN_KEYS or key in extract.HOST_BAN_KEYS:
            continue
        if key in seen:
            e["is_returning"] = True
            e["earliest_episode"] = seen[key]
        else:
            e["is_returning"] = False
            e["earliest_episode"] = None
            seen[key] = episode_number
        kept.append(e)
    return kept


def rebroadcast(pairs, dry_run):
    seen = {}
    n = len(pairs)
    for i, (meta, contract) in enumerate(pairs):
        ep = contract["episode"]
        entities = _prep_entities(contract.get("entities", []), ep.get("number"), seen)
        msg = notify.build_telegram_message(ep, entities)
        if dry_run:
            print(f"\n----- ep #{ep.get('number')} ({i + 1}/{n}) "
                  f"[{len(entities)} entities] -----\n{msg}")
            continue
        notify.send_telegram(msg, disable_notification=True, allow_public=True)
        print(f"[phase2] posted ep #{ep.get('number')} ({i + 1}/{n})")
        if i < n - 1:
            time.sleep(BACKFILL_DELAY)


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Wipe + rebroadcast the Telegram channel")
    ap.add_argument("--dry-run", action="store_true",
                    help="build & print every message; no delete, no send")
    ap.add_argument("--yes", action="store_true",
                    help="skip the typed confirmation (required for a live run)")
    ap.add_argument("--chat-id",
                    help="override TELEGRAM_CHAT_ID (point at a throwaway test channel)")
    ap.add_argument("--skip-delete", action="store_true",
                    help="do not delete; only (re)post")
    ap.add_argument("--skip-extract", action="store_true",
                    help="do not gap-fill; abort if any contract is missing")
    args = ap.parse_args()

    if args.chat_id:
        config.TELEGRAM_CHAT_ID = args.chat_id
        print(f"[init] TELEGRAM_CHAT_ID overridden -> {args.chat_id}")

    # Phase 0 always runs (cheap if everything is cached) and gates the rest.
    pairs = ensure_contracts(args.skip_extract)

    if args.dry_run:
        rebroadcast(pairs, dry_run=True)
        print(f"\n[dry-run] {len(pairs)} message(s) built; nothing sent or deleted.")
        return

    if not args.yes:
        target = config.TELEGRAM_CHAT_ID
        print(f"\n!!! LIVE: this DELETES every message in {target} and re-posts "
              f"{len(pairs)} episode(s).")
        if input("Type 'REBROADCAST' to proceed: ").strip() != "REBROADCAST":
            sys.exit("Aborted. Nothing deleted.")

    if not args.skip_delete:
        delete_all_messages()
    else:
        print("[phase1] skipped (--skip-delete)")

    rebroadcast(pairs, dry_run=False)
    print("\n[done] channel rebroadcast complete.")


if __name__ == "__main__":
    main()
