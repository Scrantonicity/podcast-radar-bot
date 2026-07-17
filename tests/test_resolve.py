"""Offline unit tests for resolve_entities (Gemini call stubbed).

Covers the two headline bugs:
  - STT garble corrected ("פייבל פייב" -> "Fable 5")
  - a Hebrew variant folds onto an existing Latin DB entity (dedup), instead of
    minting a new page — the core duplicate regression.
Plus: non-entity dropped, alias carried, low-confidence surfaced.

    python test_resolve.py       # or: pytest test_resolve.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SHOW", "table4")


import os

import resolve_entities as re_


def _index():
    """Existing DB: NVIDIA already present under the canonical Latin key."""
    return {
        "nvidia": {"page_id": "pN", "name": "NVIDIA", "type": "stock", "aliases": []},
        "biden": {"page_id": "pB", "name": "Joe Biden", "type": "person", "aliases": []},
    }


def _entities():
    return [
        {"name": "פייבל פייב", "canonical_key": "פייבל פייב", "type": "book",
         "notability": 4, "mentioned_by": []},
        {"name": "אנבידיה", "canonical_key": "אנבידיה", "type": "stock",
         "notability": 3, "mentioned_by": []},
        {"name": "בלה בלה גנרי", "canonical_key": "bla", "type": "other",
         "notability": 1, "mentioned_by": []},
    ]


def _fake_resolutions(client, items, model):
    return {
        0: {"i": 0, "name": "Fable 5", "canonical_key": "fable 5", "matched_key": None,
            "drop": False, "alias": "פייבל פייב", "confidence": "high"},
        1: {"i": 1, "name": "Nvidia", "canonical_key": "nvidia", "matched_key": "nvidia",
            "drop": False, "alias": "אנבידיה", "confidence": "high"},
        2: {"i": 2, "name": "", "canonical_key": "", "matched_key": None,
            "drop": True, "alias": None, "confidence": "low"},
    }


def _resolve():
    os.environ["GOOGLE_API_KEY"] = "test-dummy"
    re_._call_resolver = _fake_resolutions          # stub the Gemini call
    # Dummy client so genai.Client() is never constructed; embeddings fail-open.
    return re_.resolve(_entities(), _index(), client=object())


def test_stt_name_corrected():
    ents, _ = _resolve()
    fable = next(e for e in ents if e["canonical_key"] == "fable 5")
    assert fable["name"] == "Fable 5"
    assert fable.get("alias") == "פייבל פייב"


def test_variant_folds_onto_existing_page():
    ents, _ = _resolve()
    # The Hebrew "אנבידיה" must resolve to the existing Latin key, NOT a new page.
    nv = next(e for e in ents if e["name"] == "Nvidia")
    assert nv["canonical_key"] == "nvidia"
    assert nv.get("alias") == "אנבידיה"
    # No leftover entity still carrying the un-reconciled Hebrew key.
    assert all(e["canonical_key"] != "אנבידיה" for e in ents)


def test_non_entity_dropped():
    ents, _ = _resolve()
    assert all("בלה" not in (e.get("name") or "") for e in ents)
    assert len(ents) == 2


def test_notes_surface_merge_and_rename():
    _, notes = _resolve()
    joined = "\n".join(notes)
    assert "🔗" in joined   # merge note
    assert "✏️" in joined   # rename note


def test_fail_open_without_api_key():
    os.environ.pop("GOOGLE_API_KEY", None)
    ents_in = _entities()
    ents_out, notes = re_.resolve(ents_in, _index())
    assert ents_out is ents_in and notes == []


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    ok = True
    for fn in fns:
        try:
            fn()
            print(f"  [PASS] {fn.__name__}")
        except AssertionError as e:
            ok = False
            print(f"  [FAIL] {fn.__name__}: {e}")
    print("RESULT:", "ALL PASS ✅" if ok else "SOME FAILED ❌")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if _run() else 1)
