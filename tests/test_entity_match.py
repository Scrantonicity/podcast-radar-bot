"""Offline unit tests for entity_match (no network).

    python test_entity_match.py      # or: pytest test_entity_match.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SHOW", "demo")


import entity_match as em


def test_strip_subtitle():
    full = "כך מענישה ההיסטוריה: את ההולכים בתלם"
    assert em.strip_subtitle(full) == "כך מענישה ההיסטוריה"
    # Dash separator too.
    assert em.strip_subtitle("Sapiens - A Brief History") == "Sapiens"
    # Short head is NOT treated as a subtitle head (keep whole).
    assert em.strip_subtitle("AI: הבוט") == "AI: הבוט"


def test_translit_normalize_collapses_subtitle():
    full = "כך מענישה ההיסטוריה: את ההולכים בתלם"
    head = "כך מענישה ההיסטוריה"
    # Subtitle variant normalizes to the same string as the clean title.
    assert em.translit_normalize(full) == em.translit_normalize(head)


def test_base_normalize():
    assert em.base_normalize("  The Intelligent, Investor!  ") == "the intelligent investor"


def test_romanize_latin_passthrough():
    assert em.translit_normalize("Nvidia") == "nvidia"
    # Hebrew romanizes to a latin token (recall aid, not exact).
    rom = em._romanize("אנבידיה")
    assert rom and all(ord(c) < 128 for c in rom)


def test_find_candidates_subtitle_and_exact():
    catalog = [
        {"page_id": "p1", "key": "kach maanisha", "name": "כך מענישה ההיסטוריה",
         "type": "book", "aliases": []},
        {"page_id": "p2", "key": "warren-buffett", "name": "Warren Buffett",
         "type": "person", "aliases": []},
    ]
    # Subtitle variant of an existing book title -> matches p1 (translit-equal form).
    cands = em.find_candidates(
        "כך מענישה ההיסטוריה: את ההולכים בתלם", "kach", catalog)
    assert cands and cands[0]["page_id"] == "p1"
    assert cands[0]["fuzzy"] >= 0.99
    # Unrelated query -> no candidate.
    assert em.find_candidates("Tel Aviv", "tel-aviv", catalog) == []


def test_alias_hit():
    catalog = [{"page_id": "p1", "key": "fable-5", "name": "Fable 5", "type": "book",
                "aliases": ["פייבל פייב"]}]
    # A repeat of the STT-garbled spelling matches via the stored alias.
    cands = em.find_candidates("פייבל פייב", "פייבל פייב", catalog)
    assert cands and cands[0]["page_id"] == "p1"


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
