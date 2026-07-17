#!/usr/bin/env python3
"""watchdog.py — dead-man alert for the weekly pipeline trigger.

Fired via workflow_dispatch by an EXTERNAL scheduler (e.g. GCP Cloud Scheduler)
some hours after your show publishes. If the newest episode has NOT been processed
into Notion by then, the weekly trigger most likely failed to fire, so ping the
private alert chat and a human can dispatch it manually. Otherwise stay silent.

Why external: GitHub's own `schedule` cron silently drops runs under load, so a
watchdog on GitHub cron could miss the very failure it's meant to catch. Triggered
from outside, it reliably reports a missed weekly trigger. See RELIABILITY.md.

Read-only: it only looks at the feed, Notion, and approvals_posted.json — it never
transcribes, extracts, or posts to the channel.
"""

import json
import os

import config  # noqa: F401  (loads .env / env for the imports below)
import feed
import notify
import notion_bridge as nb
from show_loader import SHOW, STRINGS

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "approvals_posted.json")


def _load_posted():
    try:
        with open(STATE, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:  # noqa: BLE001
        return set()


def main():
    episodes = feed.list_episodes()  # oldest -> newest
    if not episodes:
        notify.send_alert(STRINGS.watchdog_empty_feed_template.format(show=SHOW.display_name))
        return

    newest = episodes[-1]
    guid = newest.get("guid")
    num = newest.get("number")

    # Already released to the channel? All good — nothing to alert.
    if guid in _load_posted():
        print(f"ep #{num} already posted to channel — OK")
        return

    # Processed into Notion (private approval draft was sent)? Then the trigger
    # DID fire; it is only awaiting the Approve tap — not a trigger failure.
    client = nb._client()
    if nb._find_episode_by_guid(client, guid) is not None:
        print(f"ep #{num} processed, awaiting Approve tap — OK (no alert)")
        return

    # Not processed by now => the weekly trigger did not fire.
    msg = STRINGS.watchdog_not_processed_template.format(show=SHOW.display_name, num=num)
    print(f"ALERT: ep #{num} (guid={guid}) not processed — weekly trigger likely missed")
    notify.send_alert(msg)


if __name__ == "__main__":
    main()
