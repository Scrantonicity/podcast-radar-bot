#!/usr/bin/env python3
"""approval_poller.py — release approved previews to the channel.

Runs on a schedule (GitHub Actions, every few minutes). Pulls Telegram callback
updates; when the configured approver taps Approve on a private preview, copies that
exact message to the public channel via copyMessage (byte-clean, no buttons). Reject
just disables the buttons.

Idempotency: posted guids are recorded in approvals_posted.json (committed by the
workflow) so a re-run never double-posts. Updates are acked via getUpdates(offset=…)
so they aren't re-processed. Requires NO Telegram webhook be set (getUpdates only).
"""

import json
import os
import sys

import config
import notify
from show_loader import STRINGS

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "approvals_posted.json")


def _load_posted():
    try:
        with open(STATE, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:  # noqa: BLE001
        return set()


def _save_posted(posted):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(sorted(posted), f, ensure_ascii=False, indent=2)


def _disable_buttons(chat_id, message_id, label):
    notify._tg_api("editMessageReplyMarkup", {
        "chat_id": chat_id, "message_id": message_id,
        "reply_markup": {"inline_keyboard": [[{"text": label, "callback_data": "noop"}]]},
    })


def main():
    if not config.TELEGRAM_BOT_TOKEN:
        sys.exit("TELEGRAM_BOT_TOKEN not set")
    channel = config.TELEGRAM_CHAT_ID
    approver = str(config.TELEGRAM_APPROVER_ID or "").strip()

    updates = notify.get_updates()
    if not updates:
        print("no updates")
        return

    posted = _load_posted()
    max_uid = None
    for u in updates:
        max_uid = u["update_id"] if max_uid is None else max(max_uid, u["update_id"])
        cq = u.get("callback_query")
        if not cq:
            continue
        data = cq.get("data") or ""
        frm = str((cq.get("from") or {}).get("id"))
        msg = cq.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        mid = msg.get("message_id")
        action, _, guid = data.partition(":")

        if action == "noop":
            notify.answer_callback(cq["id"])
            continue
        # Fail-safe: only the configured approver can release anything.
        if not approver or frm != approver:
            notify.answer_callback(cq["id"], STRINGS.toast_unauthorized)
            print(f"ignored callback from {frm} (approver={approver or 'UNSET'})")
            continue

        if action == "approve":
            if guid in posted:
                notify.answer_callback(cq["id"], STRINGS.toast_already_sent)
                print(f"already posted guid={guid}")
            elif not channel:
                notify.answer_callback(cq["id"], STRINGS.toast_no_channel)
                print("TELEGRAM_CHAT_ID (channel) not set — cannot post")
            else:
                notify.copy_message(channel, chat_id, mid)
                posted.add(guid)
                _save_posted(posted)
                notify.answer_callback(cq["id"], STRINGS.toast_sent)
                _disable_buttons(chat_id, mid, STRINGS.disabled_sent)
                print(f"APPROVED+POSTED guid={guid}")
        elif action == "reject":
            notify.answer_callback(cq["id"], STRINGS.toast_rejected)
            _disable_buttons(chat_id, mid, STRINGS.disabled_rejected)
            print(f"rejected guid={guid}")

    # Ack processed updates so the next run doesn't see them again.
    if max_uid is not None:
        notify.get_updates(offset=max_uid + 1)


if __name__ == "__main__":
    main()
