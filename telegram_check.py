"""telegram_check.py — verify the bot can post to the configured channel.

Run this BEFORE the real pipeline. It calls getChat (prints the channel
title/type) and sends one test message, with a clear PASS/FAIL and Telegram's
own error description on failure.

    ./venv/bin/python telegram_check.py
"""

import sys

import config
import notify
from show_loader import SHOW


def main():
    print(f"chat_id: {config.TELEGRAM_CHAT_ID}")
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        sys.exit("FAIL: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in .env")

    print("== getChat ==")
    try:
        chat = notify.preflight_channel()
    except RuntimeError as e:
        sys.exit(f"FAIL: {e}")
    print(f"  title: {chat.get('title')}")
    print(f"  type:  {chat.get('type')}")
    if chat.get("username"):
        print(f"  username: @{chat['username']}")

    print("== sendMessage (test) ==")
    try:
        res = notify.send_telegram(
            f"✅ {SHOW.display_name} — bot connected to the channel", allow_public=True)
    except RuntimeError as e:
        sys.exit(f"FAIL: {e}")
    print(f"  sent, message_id: {res['result']['message_id']}")
    print("\nPASS ✅ — bot can post to the channel.")


if __name__ == "__main__":
    main()
