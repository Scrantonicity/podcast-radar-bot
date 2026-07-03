"""feed.py — list every episode of the active podcast as episode_meta dicts.

Generalizes run_one.build_episode_meta over the whole feed. Returns episodes
sorted OLDEST → NEWEST so a backfill fills Notion + the Telegram channel
chronologically (episode 1 first).
"""

import json
import os
import urllib.parse

import feedparser
import requests

import stt  # reuse resolve_feed_url() + the SSL-safe parse pattern
from show_loader import SHOW

# ---- Apple episode lookup (cached) -----------------------------------------
# iTunes returns the podcast + its episodes in one call; we match an RSS guid/
# title to an episode's trackViewUrl. Cache the whole response so a 60-episode
# backfill does ONE lookup, not 60. Best-effort: any failure -> no apple_url.
# A show using a direct RSS url (no feed_apple_id) skips this enrichment entirely.
APPLE_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feed_cache")
APPLE_CACHE_PATH = os.path.join(APPLE_CACHE_DIR, "apple_episodes.json")
APPLE_LOOKUP = (
    "https://itunes.apple.com/lookup?id=" + SHOW.feed_apple_id
    + "&entity=podcastEpisode&limit=200"
    if SHOW.feed_apple_id else None
)
_apple_cache = None  # process-level memo


def _apple_episodes():
    """Return the iTunes podcastEpisode results (list), cached to disk + memoized.
    Returns [] on any failure (network, parse) so feed parsing never breaks."""
    global _apple_cache
    if _apple_cache is not None:
        return _apple_cache
    # No Apple id (direct-RSS show) -> skip enrichment gracefully.
    if not SHOW.feed_apple_id:
        _apple_cache = []
        return _apple_cache
    # Disk cache first.
    try:
        if os.path.exists(APPLE_CACHE_PATH):
            with open(APPLE_CACHE_PATH, encoding="utf-8") as f:
                _apple_cache = json.load(f).get("results", [])
                return _apple_cache
    except (OSError, json.JSONDecodeError):
        pass
    # Live lookup.
    try:
        r = requests.get(APPLE_LOOKUP, timeout=30)
        r.raise_for_status()
        results = r.json().get("results", [])
        os.makedirs(APPLE_CACHE_DIR, exist_ok=True)
        with open(APPLE_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({"results": results}, f, ensure_ascii=False)
        _apple_cache = results
    except Exception:  # noqa: BLE001 - best effort, never block the feed
        _apple_cache = []
    return _apple_cache


def _apple_url(guid, title):
    """trackViewUrl for the episode matching guid (preferred) or title; else None."""
    eps = _apple_episodes()
    if guid:
        for ep in eps:
            if ep.get("episodeGuid") == guid:
                return ep.get("trackViewUrl")
    if title:
        for ep in eps:
            if ep.get("trackName") == title:
                return ep.get("trackViewUrl")
    return None


def _entry_meta(entry):
    # date YYYY-MM-DD from published_parsed
    date = None
    if getattr(entry, "published_parsed", None):
        t = entry.published_parsed
        date = f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"

    # audio url from the first audio enclosure
    audio_url = None
    for enc in getattr(entry, "enclosures", []):
        href = enc.get("href")
        etype = (enc.get("type") or "").lower()
        if href and ("audio" in etype or href.lower().endswith(".mp3")):
            audio_url = href
            break
    if not audio_url and getattr(entry, "enclosures", []):
        audio_url = entry.enclosures[0].get("href")

    number = None
    if getattr(entry, "itunes_episode", None):
        try:
            number = int(entry.itunes_episode)
        except (TypeError, ValueError):
            number = None

    title = entry.get("title")
    guid = entry.get("id") or entry.get("guid")

    # Platform links (omit any that can't be resolved).
    # Spotify: the Anchor RSS <item><link> IS the Spotify episode URL.
    spotify_url = entry.get("link") or None
    # YouTube: search URL (exact-link via Data API can come later). Needs a title.
    youtube_url = (
        "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(title)
        if title else None
    )
    # Apple: matched from the cached iTunes episode lookup.
    apple_url = _apple_url(guid, title)

    return {
        "number": number,
        "title": title,
        "date": date,
        "duration": getattr(entry, "itunes_duration", None),
        "audio_url": audio_url,
        "youtube_url": youtube_url,
        "spotify_url": spotify_url,
        "apple_url": apple_url,
        "guid": guid,
        "_published_parsed": getattr(entry, "published_parsed", None),
    }


def list_episodes(feed_url=None):
    """Return a list of episode_meta dicts, oldest → newest."""
    feed_url = feed_url or stt.resolve_feed_url()
    resp = requests.get(feed_url, timeout=60)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    entries = list(feed.entries)
    if not entries:
        raise RuntimeError("Feed has no entries")

    metas = [_entry_meta(e) for e in entries]

    # Oldest-first: by episode number when every entry has one, else by date.
    if all(m["number"] is not None for m in metas):
        metas.sort(key=lambda m: m["number"])
    elif all(m["_published_parsed"] for m in metas):
        metas.sort(key=lambda m: m["_published_parsed"])
    else:
        metas.reverse()  # feeds are newest-first; flip to oldest-first

    for m in metas:
        m.pop("_published_parsed", None)
    return metas


if __name__ == "__main__":
    eps = list_episodes()
    print(f"{len(eps)} episodes (oldest → newest):")
    for m in eps:
        print(f"  #{m['number']} | {m['date']} | {(m['title'] or '')[:50]} | guid={m['guid']}")
