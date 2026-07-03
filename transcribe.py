"""transcribe.py — Speechmatics transcription with a per-episode cache.

get_transcript(episode_meta) returns the diarized [S#] transcript text, reusing
stt's download + Speechmatics functions. Checkpoint cache transcripts/{guid}.txt
makes a backfill fully resumable — a re-run never re-bills Speechmatics for an
episode already transcribed (the #1 cost-saving rule).
"""

import json
import os
import re

from dotenv import load_dotenv

import stt

load_dotenv()

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "transcripts")


def _cache_path(guid):
    safe = re.sub(r"[^\w.-]", "_", str(guid))
    return os.path.join(CACHE_DIR, f"{safe}.txt")


def _timing_path(guid):
    safe = re.sub(r"[^\w.-]", "_", str(guid))
    return os.path.join(CACHE_DIR, f"{safe}.timing.json")


def _pending_path(guid):
    safe = re.sub(r"[^\w.-]", "_", str(guid))
    return os.path.join(CACHE_DIR, f"{safe}.pending.json")


def transcript_path(guid):
    """Path to the cached transcript for a guid (may not exist yet)."""
    return _cache_path(guid)


def timing_path(guid):
    """Path to the cached per-block timing for a guid (may not exist yet)."""
    return _timing_path(guid)


def get_timing(guid):
    """Per-block timing dict {job_id, blocks:[{speaker,start,text}]} or None.

    Backward-safe: episodes transcribed before timing was persisted have no
    timing.json — returns None so callers treat their timestamp as null instead
    of crashing.
    """
    path = _timing_path(guid)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _read_pending_job(guid):
    """job_id of an in-flight Speechmatics job for this guid, or None. Written
    BEFORE polling so a crash mid-poll resumes the SAME job instead of paying for
    a duplicate submit."""
    path = _pending_path(guid)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("job_id")
    except (OSError, ValueError):
        return None


def _finalize(guid, lines, raw, job_id):
    """Cache the transcript text + per-block timing, then clear the pending marker."""
    text = "\n".join(lines)
    blocks = stt.extract_blocks(raw)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_cache_path(guid), "w", encoding="utf-8") as f:
        f.write(text)
    # Persist per-block timing so future timestamp features have data on disk.
    # job_id lets a transcript be re-fetched within Speechmatics' retention window.
    with open(_timing_path(guid), "w", encoding="utf-8") as f:
        json.dump({"job_id": job_id, "blocks": blocks}, f, ensure_ascii=False)
    try:
        os.remove(_pending_path(guid))
    except OSError:
        pass
    return text


def get_transcript(episode_meta):
    """Diarized [S#] transcript text for one episode. Cached by guid.

    Resume-safe: the job_id is persisted in a pending marker the moment a job is
    submitted, so a failure between submit and fetch resumes that same job on the
    next run rather than re-uploading the audio (which would bill Speechmatics
    twice for the same episode)."""
    guid = episode_meta.get("guid")
    if not guid:
        raise RuntimeError("episode_meta has no guid")
    path = _cache_path(guid)

    # Checkpoint hit -> zero Speechmatics cost.
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    key = os.getenv("SPEECHMATICS_API_KEY")
    if not key:
        raise RuntimeError("SPEECHMATICS_API_KEY not set in .env")

    # Resume a job submitted by a prior run that didn't finish fetching.
    pending = _read_pending_job(guid)
    if pending:
        print(f"[resume] pending Speechmatics job {pending} for guid={guid} — fetching, not resubmitting")
        try:
            lines, raw, job_id = stt.fetch_speechmatics(pending, key, return_meta=True)
            return _finalize(guid, lines, raw, job_id)
        except stt.JobExpired as e:
            print(f"[resume] job no longer fetchable ({e}) — falling back to a fresh submit")
            try:
                os.remove(_pending_path(guid))
            except OSError:
                pass

    audio_url = episode_meta.get("audio_url")
    if not audio_url:
        raise RuntimeError(f"episode {guid} has no audio_url")

    audio_path = stt.download(audio_url)
    try:
        job_id = stt.submit_speechmatics(audio_path, key)
        # Persist the job_id BEFORE polling — this is the dedup guard.
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(_pending_path(guid), "w", encoding="utf-8") as f:
            json.dump({"job_id": job_id}, f)
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass

    lines, raw, job_id = stt.fetch_speechmatics(job_id, key, return_meta=True)
    return _finalize(guid, lines, raw, job_id)
