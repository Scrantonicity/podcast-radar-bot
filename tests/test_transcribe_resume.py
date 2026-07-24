"""Offline tests for the Speechmatics dedup-before-resubmit guard in transcribe.py.

No network, no API key spend: stt.download / submit / fetch are monkeypatched
and CACHE_DIR is redirected to a temp dir. Verifies that a pending job_id is
RESUMED (never re-submitted), that an expired job falls back to a fresh submit,
that the pending marker is written BEFORE fetch (the actual dedup invariant), and
that per-block timing is persisted for the timestamps feature.

Run:  ./venv/bin/python test_transcribe_resume.py
"""

import json
import os
import tempfile

import stt as bakeoff
import transcribe

# Minimal Speechmatics json-v2 payload so extract_blocks yields a timed block.
RAW = {"results": [
    {"type": "word", "alternatives": [{"content": "שלום", "speaker": "S1"}], "start_time": 1.0},
    {"type": "word", "alternatives": [{"content": "עולם", "speaker": "S1"}], "start_time": 1.5},
]}
LINES = ["[S1] שלום עולם"]
META = {"guid": "TEST-resume-guid", "audio_url": "https://example.com/a.mp3"}


class _Patch:
    """Swap module attrs for the duration of one test, restore after."""
    def __init__(self, **targets):
        self.targets = targets  # name -> (module, attr, value)
        self.saved = {}

    def __enter__(self):
        for name, (mod, attr, val) in self.targets.items():
            self.saved[name] = (mod, attr, getattr(mod, attr))
            setattr(mod, attr, val)
        return self

    def __exit__(self, *exc):
        for mod, attr, old in self.saved.values():
            setattr(mod, attr, old)


def test_resume_uses_pending_job_no_resubmit():
    """A pending marker => fetch that job, never download or submit."""
    with tempfile.TemporaryDirectory() as tmp:
        old_cache = transcribe.CACHE_DIR
        transcribe.CACHE_DIR = tmp
        os.environ["SPEECHMATICS_API_KEY"] = "test-key"
        calls = {"download": 0, "submit": 0, "fetch": []}

        def fake_download(url):
            calls["download"] += 1
            return "/tmp/should-not-be-used.mp3"

        def fake_submit(path, key):
            calls["submit"] += 1
            return "JOB-NEW"

        def fake_fetch(job_id, key, return_meta=False):
            calls["fetch"].append(job_id)
            return (LINES, RAW, job_id)

        # Seed a pending marker as if a prior run submitted but never fetched.
        with open(transcribe._pending_path(META["guid"]), "w") as f:
            json.dump({"job_id": "JOB-PENDING"}, f)

        try:
            with _Patch(d=(bakeoff, "download", fake_download),
                        s=(bakeoff, "submit_speechmatics", fake_submit),
                        f=(bakeoff, "fetch_speechmatics", fake_fetch)):
                text = transcribe.get_transcript(META)
        finally:
            transcribe.CACHE_DIR = old_cache

        assert text == "\n".join(LINES), text
        assert calls["download"] == 0, "must NOT re-download audio"
        assert calls["submit"] == 0, "must NOT re-submit a job (= duplicate bill)"
        assert calls["fetch"] == ["JOB-PENDING"], calls["fetch"]
        # Transcript + timing cached; timing carries the resumed job_id + blocks.
        assert os.path.exists(os.path.join(tmp, "TEST-resume-guid.txt"))
        timing = json.load(open(os.path.join(tmp, "TEST-resume-guid.timing.json")))
        assert timing["job_id"] == "JOB-PENDING"
        assert timing["blocks"] == [{"speaker": "S1", "start": 1.0, "text": "שלום עולם"}]
        # Pending marker cleared on success.
        assert not os.path.exists(transcribe._pending_path("TEST-resume-guid"))


def test_expired_pending_falls_back_to_fresh_submit():
    """An expired/deleted pending job => resubmit once, then finalize."""
    with tempfile.TemporaryDirectory() as tmp:
        old_cache = transcribe.CACHE_DIR
        transcribe.CACHE_DIR = tmp
        os.environ["SPEECHMATICS_API_KEY"] = "test-key"
        calls = {"download": 0, "submit": 0, "fetch": []}

        def fake_download(url):
            calls["download"] += 1
            return "/tmp/x.mp3"

        def fake_submit(path, key):
            calls["submit"] += 1
            return "JOB-FRESH"

        def fake_fetch(job_id, key, return_meta=False):
            calls["fetch"].append(job_id)
            if job_id == "JOB-PENDING":
                raise bakeoff.JobExpired("expired")
            return (LINES, RAW, job_id)

        with open(transcribe._pending_path(META["guid"]), "w") as f:
            json.dump({"job_id": "JOB-PENDING"}, f)

        try:
            with _Patch(d=(bakeoff, "download", fake_download),
                        s=(bakeoff, "submit_speechmatics", fake_submit),
                        f=(bakeoff, "fetch_speechmatics", fake_fetch)):
                text = transcribe.get_transcript(META)
        finally:
            transcribe.CACHE_DIR = old_cache

        assert text == "\n".join(LINES)
        assert calls["download"] == 1
        assert calls["submit"] == 1
        assert calls["fetch"] == ["JOB-PENDING", "JOB-FRESH"], calls["fetch"]
        timing = json.load(open(os.path.join(tmp, "TEST-resume-guid.timing.json")))
        assert timing["job_id"] == "JOB-FRESH"


def test_pending_marker_written_before_fetch():
    """The dedup invariant: on a fresh run the job_id is persisted BEFORE polling,
    so a crash during fetch leaves a resumable marker."""
    with tempfile.TemporaryDirectory() as tmp:
        old_cache = transcribe.CACHE_DIR
        transcribe.CACHE_DIR = tmp
        os.environ["SPEECHMATICS_API_KEY"] = "test-key"
        observed = {}

        def fake_download(url):
            return "/tmp/x.mp3"

        def fake_submit(path, key):
            return "JOB-FRESH"

        def fake_fetch(job_id, key, return_meta=False):
            # At fetch time the marker must already exist with this job_id.
            p = transcribe._pending_path(META["guid"])
            observed["marker_exists"] = os.path.exists(p)
            observed["marker_job"] = json.load(open(p))["job_id"] if observed["marker_exists"] else None
            return (LINES, RAW, job_id)

        try:
            with _Patch(d=(bakeoff, "download", fake_download),
                        s=(bakeoff, "submit_speechmatics", fake_submit),
                        f=(bakeoff, "fetch_speechmatics", fake_fetch)):
                transcribe.get_transcript(META)
        finally:
            transcribe.CACHE_DIR = old_cache

        assert observed["marker_exists"] is True, "pending marker must exist before fetch"
        assert observed["marker_job"] == "JOB-FRESH", observed
        # And it is cleared once finalize succeeds.
        assert not os.path.exists(transcribe._pending_path("TEST-resume-guid"))


def test_cache_hit_skips_everything():
    """An existing transcript .txt => zero API calls, returns cached text."""
    with tempfile.TemporaryDirectory() as tmp:
        old_cache = transcribe.CACHE_DIR
        transcribe.CACHE_DIR = tmp
        with open(os.path.join(tmp, "TEST-resume-guid.txt"), "w", encoding="utf-8") as f:
            f.write("cached body")

        def boom(*a, **k):
            raise AssertionError("no API call allowed on a cache hit")

        try:
            with _Patch(d=(bakeoff, "download", boom),
                        s=(bakeoff, "submit_speechmatics", boom),
                        f=(bakeoff, "fetch_speechmatics", boom)):
                text = transcribe.get_transcript(META)
        finally:
            transcribe.CACHE_DIR = old_cache
        assert text == "cached body"


def main():
    tests = [
        test_resume_uses_pending_job_no_resubmit,
        test_expired_pending_falls_back_to_fresh_submit,
        test_pending_marker_written_before_fetch,
        test_cache_hit_skips_everything,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
