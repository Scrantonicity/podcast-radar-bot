#!/usr/bin/env python3
"""STT/feed engine: Soniox + Speechmatics speaker-diarized transcription.

Podcast/language-agnostic speech-to-text and feed resolution. All show-specific
details (language, feed source, STT vocab) come from the active show config via
show_loader; this module holds no per-podcast constants. Also runnable as a
one-off Soniox vs Speechmatics bake-off (see main()).
"""

import argparse
import json
import os
import sys
import tempfile
import time

import feedparser
import requests
from dotenv import load_dotenv

from show_loader import SHOW

APPLE_PODCAST_ID = SHOW.feed_apple_id
ITUNES_LOOKUP = (
    "https://itunes.apple.com/lookup?id=" + APPLE_PODCAST_ID
    if APPLE_PODCAST_ID else None
)

SPEECHMATICS_BASE = "https://asr.api.speechmatics.com/v2"
SONIOX_BASE = "https://api.soniox.com/v1"

POLL_INTERVAL = 10        # seconds between status checks
POLL_TIMEOUT = 60 * 40    # give large episodes time


# --------------------------------------------------------------------------
# Feed resolution + download
# --------------------------------------------------------------------------
def resolve_feed_url():
    # A show may supply a direct RSS url (skips the iTunes lookup entirely) or an
    # Apple/iTunes podcast id (resolved below). Exactly one must be set.
    if SHOW.feed_rss_url:
        print(f"Using direct RSS feed url: {SHOW.feed_rss_url}")
        return SHOW.feed_rss_url
    if not APPLE_PODCAST_ID:
        raise RuntimeError(
            "No feed source configured: set SHOW.feed_apple_id or SHOW.feed_rss_url"
        )
    print(f"Resolving RSS feed from iTunes (id={APPLE_PODCAST_ID})...")
    r = requests.get(ITUNES_LOOKUP, timeout=30)
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        raise RuntimeError("iTunes lookup returned no results")
    feed_url = results[0].get("feedUrl")
    if not feed_url:
        raise RuntimeError("No feedUrl in iTunes lookup result")
    print(f"  feedUrl: {feed_url}")
    return feed_url


def pick_episode(feed_url, n):
    print(f"Parsing feed, picking episode #{n} (1 = newest)...")
    # Fetch with requests (feedparser's own fetch can hit SSL cert issues on
    # some Python builds); hand the bytes to feedparser.
    resp = requests.get(feed_url, timeout=60)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    entries = list(feed.entries)
    if not entries:
        raise RuntimeError("Feed has no entries")

    # Sort newest-first defensively (most podcast feeds already are).
    def pub_key(e):
        return getattr(e, "published_parsed", None) or ()
    if all(getattr(e, "published_parsed", None) for e in entries):
        entries.sort(key=pub_key, reverse=True)

    if n < 1 or n > len(entries):
        raise RuntimeError(f"--episode {n} out of range (feed has {len(entries)})")
    entry = entries[n - 1]
    print(f"  Episode: {entry.get('title', '(no title)')}")

    audio_url = None
    for enc in getattr(entry, "enclosures", []):
        href = enc.get("href")
        etype = (enc.get("type") or "").lower()
        if href and ("audio" in etype or href.lower().endswith(".mp3")):
            audio_url = href
            break
    if not audio_url and getattr(entry, "enclosures", []):
        audio_url = entry.enclosures[0].get("href")
    if not audio_url:
        raise RuntimeError("No enclosure audio URL on chosen episode")
    print(f"  Audio: {audio_url}")
    return audio_url


def download(url):
    print("Downloading audio...")
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        size = 0
        for chunk in r.iter_content(chunk_size=1 << 16):
            if chunk:
                tmp.write(chunk)
                size += len(chunk)
    tmp.close()
    print(f"  Saved {size/1e6:.1f} MB -> {tmp.name}")
    return tmp.name


# --------------------------------------------------------------------------
# Speechmatics batch transcription
# --------------------------------------------------------------------------
class JobExpired(RuntimeError):
    """Speechmatics job is no longer fetchable (rejected/deleted/expired). Signals
    the caller to fall back to a fresh submit instead of resuming this job_id."""


def submit_speechmatics(audio_path, api_key):
    """Upload audio + start a Speechmatics job. Returns job_id immediately (does
    NOT wait for completion). Split out from fetch so a caller can persist the
    job_id BEFORE polling — a crash mid-poll then resumes the same job instead of
    re-uploading (= a duplicate paid job)."""
    headers = {"Authorization": f"Bearer {api_key}"}
    transcription_config = {
        "language": SHOW.stt_language,
        "diarization": "speaker",
    }
    # STT-vocab guardrail: let a show fix misheard proper names without code edits.
    if SHOW.stt_additional_vocab:
        transcription_config["additional_vocab"] = [
            {"content": w} for w in SHOW.stt_additional_vocab
        ]
    config = {
        "type": "transcription",
        "transcription_config": transcription_config,
    }
    print("[Speechmatics] Submitting job...")
    with open(audio_path, "rb") as f:
        r = requests.post(
            f"{SPEECHMATICS_BASE}/jobs",
            headers=headers,
            files={"data_file": f},
            data={"config": json.dumps(config)},
            timeout=300,
        )
    if not r.ok:
        raise RuntimeError(f"submit failed {r.status_code}: {r.text}")
    job_id = r.json()["id"]
    print(f"[Speechmatics] job id: {job_id}")
    return job_id


def fetch_speechmatics(job_id, api_key, return_meta=False):
    """Poll an existing Speechmatics job_id to completion and fetch its transcript.
    Raises JobExpired if the job ended rejected/deleted/expired (caller resubmits)."""
    headers = {"Authorization": f"Bearer {api_key}"}
    deadline = time.monotonic() + POLL_TIMEOUT
    while True:
        time.sleep(POLL_INTERVAL)
        r = requests.get(f"{SPEECHMATICS_BASE}/jobs/{job_id}", headers=headers, timeout=60)
        if not r.ok:
            # A 404 means the job no longer exists -> resubmit; other codes are transient.
            if r.status_code == 404:
                raise JobExpired(f"job {job_id} not found (404)")
            raise RuntimeError(f"poll failed {r.status_code}: {r.text}")
        status = r.json()["job"]["status"]
        print(f"[Speechmatics] status: {status}")
        if status == "done":
            break
        if status in ("rejected", "deleted", "expired"):
            raise JobExpired(f"job ended with status '{status}': {r.text}")
        if time.monotonic() > deadline:
            raise RuntimeError("poll timed out")

    print("[Speechmatics] Fetching transcript...")
    r = requests.get(
        f"{SPEECHMATICS_BASE}/jobs/{job_id}/transcript",
        headers=headers,
        params={"format": "json-v2"},
        timeout=120,
    )
    if not r.ok:
        raise RuntimeError(f"transcript fetch failed {r.status_code}: {r.text}")
    raw = r.json()
    lines = format_speechmatics(raw)
    # return_meta=True hands back the raw json-v2 payload + job_id so callers can
    # persist per-block timing (transcripts/{guid}.timing.json). Default stays
    # lines-only for backward-compat (bake-off, etc.).
    if return_meta:
        return lines, raw, job_id
    return lines


def transcribe_speechmatics(audio_path, api_key, return_meta=False):
    """Submit + fetch in one call (back-compat for the bake-off CLI). The pipeline
    uses submit_speechmatics + fetch_speechmatics separately for resume safety."""
    job_id = submit_speechmatics(audio_path, api_key)
    return fetch_speechmatics(job_id, api_key, return_meta=return_meta)


def format_speechmatics(data):
    """results[] -> [S#] lines, merging consecutive same-speaker words."""
    lines = []
    cur_spk = None
    cur = []
    for res in data.get("results", []):
        alts = res.get("alternatives") or []
        if not alts:
            continue
        content = alts[0].get("content", "")
        spk = alts[0].get("speaker", "UU")
        rtype = res.get("type")
        if spk != cur_spk:
            if cur:
                lines.append(f"[{cur_spk}] " + "".join(cur).strip())
            cur_spk = spk
            cur = []
        if rtype == "punctuation":
            cur.append(content)
        else:
            cur.append((" " if cur else "") + content)
    if cur:
        lines.append(f"[{cur_spk}] " + "".join(cur).strip())
    return lines


def extract_blocks(data):
    """results[] -> [{speaker, start, text}] per [S#] block.

    Same block-merging logic as format_speechmatics (consecutive same-speaker
    words become one block), but also captures the block's start time in seconds
    (start_time of the block's first word). Punctuation carries no useful timing.
    """
    blocks = []
    cur_spk = None
    cur = []
    cur_start = None
    for res in data.get("results", []):
        alts = res.get("alternatives") or []
        if not alts:
            continue
        content = alts[0].get("content", "")
        spk = alts[0].get("speaker", "UU")
        rtype = res.get("type")
        if spk != cur_spk:
            if cur:
                blocks.append(
                    {"speaker": cur_spk, "start": cur_start, "text": "".join(cur).strip()}
                )
            cur_spk = spk
            cur = []
            cur_start = None
        if rtype == "punctuation":
            cur.append(content)
        else:
            cur.append((" " if cur else "") + content)
            if cur_start is None:
                cur_start = res.get("start_time")
    if cur:
        blocks.append(
            {"speaker": cur_spk, "start": cur_start, "text": "".join(cur).strip()}
        )
    return blocks


# --------------------------------------------------------------------------
# Soniox async transcription
# --------------------------------------------------------------------------
def transcribe_soniox(audio_path, api_key):
    headers = {"Authorization": f"Bearer {api_key}"}
    print("[Soniox] Uploading file...")
    with open(audio_path, "rb") as f:
        r = requests.post(
            f"{SONIOX_BASE}/files",
            headers=headers,
            files={"file": f},
            timeout=300,
        )
    if not r.ok:
        raise RuntimeError(f"upload failed {r.status_code}: {r.text}")
    file_id = r.json()["id"]
    print(f"[Soniox] file id: {file_id}")

    try:
        print("[Soniox] Creating transcription...")
        r = requests.post(
            f"{SONIOX_BASE}/transcriptions",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "model": "stt-async-v5",
                "language_hints": [SHOW.stt_language],
                "enable_speaker_diarization": True,
                "file_id": file_id,
            },
            timeout=60,
        )
        if not r.ok:
            raise RuntimeError(f"create failed {r.status_code}: {r.text}")
        tid = r.json()["id"]
        print(f"[Soniox] transcription id: {tid}")

        deadline = time.monotonic() + POLL_TIMEOUT
        while True:
            time.sleep(POLL_INTERVAL)
            r = requests.get(f"{SONIOX_BASE}/transcriptions/{tid}", headers=headers, timeout=60)
            if not r.ok:
                raise RuntimeError(f"poll failed {r.status_code}: {r.text}")
            body = r.json()
            status = body.get("status")
            print(f"[Soniox] status: {status}")
            if status == "completed":
                break
            if status == "error":
                raise RuntimeError(f"transcription error: {body.get('error_message')}")
            if time.monotonic() > deadline:
                raise RuntimeError("poll timed out")

        print("[Soniox] Fetching transcript...")
        r = requests.get(
            f"{SONIOX_BASE}/transcriptions/{tid}/transcript",
            headers=headers,
            timeout=120,
        )
        if not r.ok:
            raise RuntimeError(f"transcript fetch failed {r.status_code}: {r.text}")
        return format_soniox(r.json())
    finally:
        # Best-effort cleanup of the uploaded file.
        try:
            requests.delete(f"{SONIOX_BASE}/files/{file_id}", headers=headers, timeout=30)
        except Exception:
            pass


def format_soniox(data):
    """tokens[] -> [S#] lines, merging consecutive same-speaker tokens."""
    lines = []
    cur_spk = None
    cur = []
    for tok in data.get("tokens", []):
        text = tok.get("text", "")
        spk = tok.get("speaker")
        label = f"S{spk}" if spk is not None else "SU"
        if label != cur_spk:
            if cur:
                lines.append(f"[{cur_spk}] " + "".join(cur).strip())
            cur_spk = label
            cur = []
        cur.append(text)
    if cur:
        lines.append(f"[{cur_spk}] " + "".join(cur).strip())
    return lines


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def write_and_preview(path, lines, label):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n===== {label}: first 10 lines of {path} =====")
    for line in lines[:10]:
        print(line)
    print("=" * 50)


def main():
    ap = argparse.ArgumentParser(description="Soniox vs Speechmatics STT bake-off")
    ap.add_argument("--url", help="Direct audio URL (skips feed resolution)")
    ap.add_argument("--episode", type=int, default=1, help="Nth-newest episode (default 1)")
    args = ap.parse_args()

    load_dotenv()
    sm_key = os.getenv("SPEECHMATICS_API_KEY")
    sx_key = os.getenv("SONIOX_API_KEY")
    if not sm_key or not sx_key:
        sys.exit("ERROR: set SPEECHMATICS_API_KEY and SONIOX_API_KEY in .env")

    if args.url:
        audio_url = args.url
    else:
        audio_url = pick_episode(resolve_feed_url(), args.episode)
    audio_path = download(audio_url)

    results = {}
    for name, fn, key, out in [
        ("Speechmatics", transcribe_speechmatics, sm_key, "out_speechmatics.txt"),
        ("Soniox", transcribe_soniox, sx_key, "out_soniox.txt"),
    ]:
        try:
            lines = fn(audio_path, key)
            write_and_preview(out, lines, name)
            results[name] = True
        except Exception as e:
            print(f"\n!!! {name} FAILED: {e}\n")
            results[name] = False

    print("\nDone. Engine results:", results)
    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
