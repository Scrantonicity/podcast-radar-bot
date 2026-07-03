"""One-time backfill: fill Spotify/Apple links, entity context, and transcript
links on the existing Notion Episodes + Entities DBs.

Reads the cached extraction contracts in extractions/*.json (the same source the
live pipeline uses) and writes the three gaps the bridge didn't populate before:

  1. Episodes: Spotify + Apple Music url columns (from episode.spotify_url /
     episode.apple_url in each JSON).
  2. Episodes: Transcript url column -> the transcript child page (titled
     STRINGS.notion_transcript_title) already under each episode page (column is
     converted file->url first).
  3. Entities: Context column (most-recent episode's sentence) + a per-episode
     context bullet list ("{episode-word} N — <context>") in each entity page body.

Idempotent: re-running overwrites columns and rebuilds entity bodies (clears the
bullets it added, then re-appends). Reuses notion_bridge internals + helpers.

Run:  python backfill_notion.py
"""

import glob
import json
import os
import sys
import time

import notion_bridge as nb
from show_loader import STRINGS

EXTRACTIONS_DIR = os.path.join(os.path.dirname(__file__), "extractions")
TRANSCRIPT_TITLE = STRINGS.notion_transcript_title


def load_all():
    data = []
    for path in sorted(glob.glob(os.path.join(EXTRACTIONS_DIR, "*.json"))):
        with open(path, encoding="utf-8") as f:
            data.append(json.load(f))
    return data


def _find_transcript_child(client, episode_page_id):
    """Return the page id of the episode's transcript child page, or None."""
    cursor = None
    while True:
        kwargs = {"block_id": episode_page_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = nb._retry(client.blocks.children.list, **kwargs)
        for b in resp.get("results", []):
            if b.get("type") == "child_page" and \
                    (b.get("child_page") or {}).get("title") == TRANSCRIPT_TITLE:
                return b["id"]
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return None


def _clear_children(client, page_id):
    """Delete all child blocks of a page (entity pages only hold our bullets)."""
    cursor = None
    ids = []
    while True:
        kwargs = {"block_id": page_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = nb._retry(client.blocks.children.list, **kwargs)
        ids += [b["id"] for b in resp.get("results", [])]
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    for bid in ids:
        nb._retry(client.blocks.delete, block_id=bid)
        time.sleep(nb.WRITE_DELAY)


def backfill_episodes(client, data):
    """Spotify/Apple url props + Transcript url link for every episode."""
    ok = links_only = missing_ep = 0
    for d in data:
        ep = d.get("episode", {})
        guid = ep.get("guid")
        num = ep.get("number")
        page = nb._find_episode_by_guid(client, guid)
        if not page:
            print(f"  [skip] no Notion episode for guid={guid} (#{num})")
            missing_ep += 1
            continue
        pid = page["id"]

        props = {}
        if ep.get("spotify_url"):
            props["Spotify"] = {"url": ep["spotify_url"]}
        if ep.get("apple_url"):
            props["Apple Music"] = {"url": ep["apple_url"]}
        if props:
            nb._retry(client.pages.update, page_id=pid, properties=props)
            time.sleep(nb.WRITE_DELAY)

        child = _find_transcript_child(client, pid)
        if child:
            nb._set_transcript_url(client, pid, child)
            print(f"  ep #{num}: links + transcript ok")
            ok += 1
        else:
            print(f"  ep #{num}: links ok, NO transcript child page")
            links_only += 1
    print(f"  episodes -> {ok} full, {links_only} no-transcript, {missing_ep} missing")


def backfill_entity_context(client, data):
    """Context column (latest episode) + per-episode bullet body for each entity."""
    # key -> {episode_number: context}
    ctx_map = {}
    for d in data:
        num = d.get("episode", {}).get("number")
        for e in d.get("entities", []):
            ctx = e.get("context")
            key = e.get("canonical_key")
            if ctx and key:
                ctx_map.setdefault(key, {})[num] = ctx

    index = nb._load_entities_index(client)
    total = len(ctx_map)
    written = missing = failed = 0
    for n_done, (key, by_num) in enumerate(ctx_map.items(), 1):
        cur = index.get(key)
        if not cur:
            missing += 1
            continue
        epid = cur["page_id"]
        try:
            valid = [n for n in by_num if n is not None]
            latest = max(valid) if valid else next(iter(by_num))
            nb._retry(client.pages.update, page_id=epid,
                      properties={"Context": {"rich_text": nb._rt(by_num[latest])}})
            time.sleep(nb.WRITE_DELAY)

            # Rebuild body: clear prior bullets, append sorted (None nums last).
            _clear_children(client, epid)
            order = sorted(by_num.keys(), key=lambda n: (n is None, n))
            bullets = [nb._context_bullet(n, by_num[n]) for n in order]
            for i in range(0, len(bullets), nb.CHILDREN_PER_REQUEST):
                nb._retry(client.blocks.children.append, block_id=epid,
                          children=bullets[i:i + nb.CHILDREN_PER_REQUEST])
                time.sleep(nb.WRITE_DELAY)
            written += 1
        except Exception as e:  # noqa: BLE001 - keep going past one bad page
            print(f"  [err] entity {key}: {e}", flush=True)
            failed += 1
        if n_done % 25 == 0:
            print(f"  ... {n_done}/{total} entities ({written} ok, {failed} err)",
                  flush=True)
    print(f"  entities -> {written} updated, {missing} not found, {failed} errors")


def backfill_entity_learn(client, data):
    """Set the 'Learn' Perplexity deep-link on every existing entity page, so the
    whole current DB gets the quick-learn link (not just entities re-mentioned in a
    future episode). name + one-liner come from the cached contracts (latest non-empty
    one-liner wins)."""
    if not nb._ensure_learn_property(client):
        print("  [learn] property unavailable — skipping")
        return
    # key -> record: latest episode wins for name/type/context; latest non-empty
    # one-liner wins. context = the claim raised in the most recent mention.
    info = {}
    for d in data:
        num = d.get("episode", {}).get("number") or 0
        for e in d.get("entities", []):
            key = e.get("canonical_key")
            if not key:
                continue
            rec = info.get(key) or {"name": None, "one_liner": None,
                                    "type": None, "context": None, "seen": -1}
            if num >= rec["seen"]:
                rec["name"] = e.get("name") or rec["name"]
                rec["type"] = e.get("type") or rec["type"]
                rec["context"] = e.get("context") or rec["context"]
                rec["seen"] = num
            if e.get("one_liner"):
                rec["one_liner"] = e["one_liner"]
            info[key] = rec

    index = nb._load_entities_index(client)
    total = len(info)
    written = missing = failed = 0
    for n_done, (key, rec) in enumerate(info.items(), 1):
        cur = index.get(key)
        if not cur:
            missing += 1
            continue
        if not rec["name"]:
            continue
        try:
            nb._retry(client.pages.update, page_id=cur["page_id"],
                      properties={"Learn": {"url": nb._learn_url(
                          rec["name"], rec["one_liner"], rec["type"], rec["context"])}})
            time.sleep(nb.WRITE_DELAY)
            written += 1
        except Exception as e:  # noqa: BLE001
            print(f"  [err] learn {key}: {e}", flush=True)
            failed += 1
        if n_done % 25 == 0:
            print(f"  ... {n_done}/{total} learn-links ({written} ok, {failed} err)",
                  flush=True)
    print(f"  learn -> {written} updated, {missing} not found, {failed} errors")


def main():
    client = nb._client()

    print("schema...")
    print("  Context property:", nb.ensure_context_property(client))
    print("  Transcript url:", nb.ensure_transcript_url(client))
    print("  Learn property:", nb._ensure_learn_property(client))

    data = load_all()
    print(f"loaded {len(data)} extraction files")

    entities_only = "--entities-only" in sys.argv
    if not entities_only:
        print("episodes (Spotify / Apple / Transcript link)...")
        backfill_episodes(client, data)
    else:
        print("episodes: skipped (--entities-only)")

    print("entity context (column + body)...")
    backfill_entity_context(client, data)

    print("entity learn-links (Perplexity)...")
    backfill_entity_learn(client, data)

    print("done")


if __name__ == "__main__":
    main()
