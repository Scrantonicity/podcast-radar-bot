"""main.py — podcast pipeline orchestrator, per episode.

Per episode: transcript (Speechmatics, cached) -> extract (Gemini, cached) ->
Notion bridge (idempotent, broadcasts to the Telegram channel).

Modes:
  --backfill        process every episode oldest -> newest (channel history),
                    ~4s between episodes for Telegram rate limits. Resumable.
  (no flag)         weekly: process only episodes NOT already done in Notion.
  --episode N       process a single episode (1 = newest, matching bakeoff).
  --no-telegram     suppress Telegram (testing).
"""

import argparse
import collections
import html
import os
import sys
import time

import config
import extract
import feed
import notify
import notion_bridge as nb
import resolve_entities
import transcribe
from show_loader import SHOW, STRINGS

BACKFILL_DELAY = 4  # seconds between episodes (Telegram channel rate limit)

# Safety cap: max episodes processed in one non-explicit run (weekly/backfill/
# cached). A weekly run normally yields exactly 1 new episode; a feed glitch that
# surfaces many at once would otherwise queue that many PAID Speechmatics jobs.
# An explicit --episode N is never capped. Backfill can raise it via the env var.
MAX_EPISODES_PER_RUN = int(os.getenv("MAX_EPISODES_PER_RUN", "3"))


def _is_done_in_notion(client, guid):
    existing = nb._find_episode_by_guid(client, guid)
    if not existing:
        return False
    status = (existing["properties"].get("Status", {}).get("select") or {}).get("name")
    return status == "done"


def _wipe_data_source(client, ds_id, label):
    """Trash (delete) every page in a data source. Returns count trashed.

    query is eventually-consistent: a page just trashed can still surface in the
    next re-query for a short window, and re-trashing it 400s ("Can't edit block
    that is archived"). So we skip pages already trashed and stop once a full
    re-query yields nothing still-live — never re-trashing, never looping forever.
    """
    n = 0
    while True:
        resp = nb._retry(client.data_sources.query, data_source_id=ds_id, page_size=100)
        live = [p for p in resp.get("results", [])
                if not (p.get("archived") or p.get("in_trash"))]
        if not live:
            break
        for p in live:
            nb._retry(client.pages.update, page_id=p["id"], in_trash=True)
            n += 1
            time.sleep(nb.WRITE_DELAY)
    print(f"  [wipe] {label}: trashed {n} page(s)")
    return n


def wipe_all(client):
    """DESTRUCTIVE: archive every page in BOTH the Episodes and Entities DBs.
    Requires explicit typed confirmation. Use before a clean re-extraction so the
    bridge (which never removes) does not leave orphaned/stale rows behind."""
    print("\n!!! WIPE: this will ARCHIVE (delete) every page in BOTH Notion DBs:")
    print(f"    Episodes DS: {config.NOTION_EPISODES_DS_ID}")
    print(f"    Entities DS: {config.NOTION_ENTITIES_DS_ID}")
    ans = input("Type 'WIPE' to proceed, anything else to abort: ").strip()
    if ans != "WIPE":
        print("Aborted. Nothing archived.")
        return False
    _wipe_data_source(client, config.NOTION_EPISODES_DS_ID, "Episodes")
    _wipe_data_source(client, config.NOTION_ENTITIES_DS_ID, "Entities")
    print("  [wipe] done — both DBs empty.")
    return True


def _mark_failed(client, guid):
    try:
        existing = nb._find_episode_by_guid(client, guid)
        if existing:
            nb._retry(client.pages.update, page_id=existing["id"],
                      properties={"Status": {"select": {"name": "failed"}}})
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] could not mark failed: {e}")


def process_one(meta, client):
    """Run one episode through the pipeline. Returns 'done' | 'skipped' | 'failed'."""
    guid = meta.get("guid")
    label = f"#{meta.get('number')} {str(meta.get('title') or '')[:45]}"
    print(f"\n=== {label} (guid={guid}) ===")
    stage = "transcribe"
    try:
        print("  transcript...")
        text = transcribe.get_transcript(meta)
        print(f"    {len(text)} chars")
        print("  extract...")
        stage = "extract"
        contract = extract.extract(text, episode_meta=meta)
        # Resolution pass: STT-name correction + dedup-onto-existing before the write.
        # Load the current entity index once and hand it to the resolver (fail-open;
        # a no-op for shows without a resolve.txt prompt).
        stage = "resolve"
        resolve_index = nb._load_entities_index(client)
        contract["entities"], resolve_notes = resolve_entities.resolve(
            contract["entities"], resolve_index)
        for n in resolve_notes:
            print(f"    {n}")
        ents = contract["entities"]
        # Diagnostics (additive only): notability spread + diarization-gate state,
        # recomputed from the same signal the gate uses inside extract.
        spread = dict(sorted(collections.Counter(
            e.get("notability") for e in ents).items(), reverse=True))
        spk, share = extract._speaker_signal(text)
        gate = spk < extract.MIN_DISTINCT_SPEAKERS or share > extract.MAX_SPEAKER_CHAR_SHARE
        print(f"    ep #{meta.get('number')} | entities={len(ents)} | "
              f"notability={spread} | gate={'FIRED' if gate else 'not-fired'} "
              f"(distinct={spk}, char_share={share:.3f})")
        print("  notion + notify...")
        stage = "bridge"
        res = nb.process_episode(contract, transcript_path=transcribe.transcript_path(guid),
                                 client=client)
        print(f"    -> {res['status']}  Notability_written={res.get('has_notability')}  "
              f"{res.get('episode_url') or ''}")
        return res["status"]
    except Exception as e:  # noqa: BLE001
        print(f"  !!! FAILED [{stage}]: {e}")
        if guid:
            _mark_failed(client, guid)
        num = meta.get("number")
        alert = (
            STRINGS.alert_episode_failed_template.format(
                show=SHOW.display_name, num=html.escape(str(num)))
            + f"stage: <code>{stage}</code>\n"
            f"{html.escape(str(e)[:300])}"
        )
        notify.send_alert(alert)
        return "failed"


def run_targets(targets, client, delay):
    """Process each target episode, sending a private alert per failure and ONE
    summary alert at the end if anything failed. Returns the counts dict."""
    counts = {"done": 0, "skipped": 0, "failed": 0}
    failed_nums = []
    for i, meta in enumerate(targets):
        status = process_one(meta, client)
        counts[status] = counts.get(status, 0) + 1
        if status == "failed":
            failed_nums.append(meta.get("number"))
        if delay and i < len(targets) - 1:
            time.sleep(delay)

    print(f"\n==== SUMMARY ==== processed={counts['done']} "
          f"skipped={counts['skipped']} failed={counts['failed']} "
          f"(of {len(targets)} targets)")

    if failed_nums:
        nums = ", ".join(str(n) for n in failed_nums)
        notify.send_alert(
            f"📋 <b>Run complete</b>: {counts['done']} ok, "
            f"{counts['failed']} failed: [{nums}]")
    return counts


def main():
    ap = argparse.ArgumentParser(description="podcast pipeline orchestrator")
    ap.add_argument("--backfill", action="store_true",
                    help="process every episode oldest->newest")
    ap.add_argument("--cached-only", action="store_true",
                    help="process only episodes whose transcript is already cached "
                         "(no Speechmatics calls) — e.g. re-extract after a Gemini outage")
    ap.add_argument("--episode", type=int,
                    help="process a single episode (1 = newest)")
    ap.add_argument("--no-telegram", action="store_true", help="suppress Telegram")
    ap.add_argument("--wipe", action="store_true",
                    help="DESTRUCTIVE: archive all pages in both Notion DBs "
                         "(requires typed confirmation), then exit")
    args = ap.parse_args()

    if args.no_telegram:
        config.ENABLE_TELEGRAM = False

    client = nb._client()

    if args.wipe:
        wipe_all(client)
        return
    episodes = feed.list_episodes()  # oldest -> newest

    if args.episode:
        # 1 = newest, matching bakeoff/run_one semantics.
        idx = len(episodes) - args.episode
        if idx < 0 or idx >= len(episodes):
            sys.exit(f"--episode {args.episode} out of range (feed has {len(episodes)})")
        targets = [episodes[idx]]
        delay = 0
    elif args.cached_only:
        import os
        targets = [m for m in episodes
                   if os.path.exists(transcribe.transcript_path(m.get("guid")))]
        delay = BACKFILL_DELAY
        print(f"Cached-only run: {len(targets)} episode(s) with a cached transcript")
    elif args.backfill:
        targets = episodes
        delay = BACKFILL_DELAY
    else:
        # Weekly: only episodes not already done in Notion.
        targets = [m for m in episodes if not _is_done_in_notion(client, m.get("guid"))]
        delay = 0
        print(f"Weekly run: {len(targets)} new episode(s) of {len(episodes)} total")

    # Per-run cap (everything except an explicit single --episode). Process the
    # first N (oldest-first ordering is preserved) and alert on what was dropped,
    # so an anomalous feed can never silently fan out into many paid STT jobs.
    if not args.episode and len(targets) > MAX_EPISODES_PER_RUN:
        dropped = [str(m.get("number")) for m in targets[MAX_EPISODES_PER_RUN:]]
        targets = targets[:MAX_EPISODES_PER_RUN]
        msg = (f"⚠️ <b>Run capped</b>: {len(targets)} processed, "
               f"{len(dropped)} deferred (MAX_EPISODES_PER_RUN={MAX_EPISODES_PER_RUN}): "
               f"[{', '.join(dropped)}]")
        print(f"  [cap] {msg}")
        notify.send_alert(msg)

    counts = run_targets(targets, client, delay)
    sys.exit(1 if counts["failed"] else 0)


if __name__ == "__main__":
    main()
