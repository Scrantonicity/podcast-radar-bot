"""Test harness for the Notion bridge against the REAL Notion DBs.

Runs two sample episodes (Palantir shared across both, mentioned by different
hosts) and reads back to verify dedup, relations, status, and bodies.
Leaves TEST-prefixed pages in Notion for inspection.

Run:  ./venv/bin/python test_bridge.py
"""

import sys
import tempfile
import time

import config
import notion_bridge as nb

# Unique-ish GUIDs so reruns are idempotent yet inspectable.
GUID_A = "TEST-ep-A-palantir-v2"
GUID_B = "TEST-ep-B-palantir-v2"

EPISODE_A = {
    "episode": {
        "number": 9001, "title": "TEST פרק A — פלאנטיר וחברים",
        "headline": "פלאנטיר, השקעות ערך וטוקיו",
        "date": "2026-04-17", "duration": "1:10:00",
        "audio_url": "https://example.com/a.mp3", "youtube_url": None, "guid": GUID_A,
    },
    "summary": "פרק בדיקה A. מדברים על פלאנטיר ועוד כמה ישויות.",
    "headline": "פלאנטיר, השקעות ערך וטוקיו",
    "entities": [
        {"name": "Palantir", "canonical_key": "palantir", "type": "company",
         "ticker": "PLTR", "notability": 4, "one_liner": "חברת ניתוח דאטה ביטחונית",
         "context": "הוזכרה בהקשר של חוזי ביטחון", "mentioned_by": ["יונתן"],
         "link": None, "timestamp": "34:18"},
        {"name": "Warren Buffett", "canonical_key": "warren-buffett", "type": "person",
         "notability": 2, "one_liner": "משקיע אגדי", "context": "דוגמה להשקעות ערך",
         "mentioned_by": ["גילי"], "timestamp": "12:00"},
        {"name": "טוקיו", "canonical_key": "tokyo", "type": "place",
         "notability": 2, "one_liner": "בירת יפן", "context": "הוזכרה כמרכז טכנולוגי",
         "mentioned_by": ["יונתן"], "timestamp": "45:30"},
        {"name": "The Intelligent Investor", "canonical_key": "intelligent-investor",
         "type": "book", "notability": 5, "one_liner": "ספר השקעות קלאסי",
         "context": "המלצת קריאה", "mentioned_by": ["גילי"], "timestamp": "13:05"},
    ],
}

EPISODE_B = {
    "episode": {
        "number": 9002, "title": "TEST פרק B — פלאנטיר שוב",
        "headline": "פלאנטיר חוזרת ושוק השבבים",
        "date": "2026-04-24", "duration": "1:20:00",
        "audio_url": "https://example.com/b.mp3", "youtube_url": None, "guid": GUID_B,
    },
    "summary": "פרק בדיקה B. פלאנטיר חוזרת, מוזכרת על ידי מארח אחר.",
    "headline": "פלאנטיר חוזרת ושוק השבבים",
    "entities": [
        {"name": "Palantir", "canonical_key": "palantir", "type": "company",
         "ticker": "PLTR", "notability": 4, "one_liner": "חברת ניתוח דאטה ביטחונית",
         "context": "הוזכרה שוב בהקשר AI", "mentioned_by": ["גילי"],
         "link": None, "timestamp": "08:00"},
        {"name": "NVIDIA", "canonical_key": "nvidia", "type": "stock",
         "ticker": "NVDA", "notability": 3, "one_liner": "יצרנית שבבי AI",
         "context": "מובילת שוק השבבים", "mentioned_by": ["יונתן"], "timestamp": "22:10"},
    ],
}


def _multi(props, name):
    return {o["name"] for o in (props.get(name, {}).get("multi_select") or [])}


def _rel(props, name):
    return {r["id"] for r in (props.get(name, {}).get("relation") or [])}


def _strip_iso(s):
    """Drop the U+2068/U+2069 bidi-isolate chars for plain substring assertions."""
    return s.replace("⁨", "").replace("⁩", "")


def test_telegram_format():
    """Pure-function checks on the redesigned Telegram message (no network).

    Types are LOWERCASE (matching the extraction contract). Sections are merged:
    concept / radar(stock+company) / person / reading(book+article)."""
    import notify
    # Two-speaker episode: attribution should be SHOWN. Notability spread with a
    # single clear winner (=5) so the 🔥 pick is deterministic (the book).
    episode = {"number": 60, "date": "2026-06-19",
               "headline": "פלאנטיר, סרטן והכסף הפרטי",
               "title": "פרק 60: כותרת לדוגמה על איראן",
               "youtube_url": "https://youtube.com/results?search_query=x",
               "spotify_url": "https://open.spotify.com/ep/x", "apple_url": None}
    entities = [
        {"name": "קיסר כל המחלות", "type": "book", "notability": 5,
         "one_liner": "ספר על הסרטן",
         "context": "קיסר כל המחלות הוא ספר על ההיסטוריה של מחקר הסרטן",
         "mentioned_by": ["יונתן"]},
        {"name": "ערפל המלחמה", "type": "concept", "notability": 4,
         "context": "ערפל המלחמה הוא מצב של אי-ודאות בתנאי קרב",
         "mentioned_by": ["גילי", "יונתן"]},
        {"name": "NVIDIA", "type": "stock", "ticker": "NVDA", "notability": 3,
         "sentiment": "positive", "context": "מובילת שוק שבבי ה-AI",
         "mentioned_by": ["גילי"]},
        {"name": "Palantir", "type": "company", "ticker": "PLTR", "link": "https://x.co",
         "notability": 3, "sentiment": "negative",
         "context": "הוזכרה בהקשר חוזי ביטחון אמריקאים ארוכים",
         "mentioned_by": ["יונתן", "גילי"], "is_returning": True, "earliest_episode": 42},
        {"name": "ברני סנדרס", "type": "person", "notability": 2,
         "context": "טען שהידע האנושי לא צריך להישלט בידי חברה פרטית אחת",
         "mentioned_by": ["גילי"]},
        {"name": "מחקר התודעה", "type": "article", "notability": 2,
         "link": "https://art.co", "context": "סקירת מחקר חדש",
         "mentioned_by": ["יונתן"]},
        {"name": "טוקיו", "type": "place", "notability": 4, "one_liner": "בירת יפן",
         "context": "הוזכרה כמרכז טכנולוגי", "mentioned_by": ["יונתן"]},
        {"name": "משהו", "type": "other", "notability": 4, "one_liner": "x", "context": "y",
         "mentioned_by": ["גילי"]},
    ]
    msg = notify.build_telegram_message(episode, entities)
    flat = _strip_iso(msg)
    lines = msg.splitlines()
    checks = []
    checks.append(("TG: no Notion URL in message", "notion" not in msg.lower()))

    # Header: single line, episode + headline + DD.MM.YY date, no separate title line.
    header = _strip_iso(lines[0])
    checks.append(("TG: header single line 🎙️ שולחן 4 | פרק 60 + headline + DD.MM.YY",
                   header.startswith("🎙️ שולחן 4 | פרק 60")
                   and "פלאנטיר, סרטן והכסף הפרטי" in header
                   and "19.06.26" in header and "2026" not in header))
    checks.append(("TG: headline not duplicated (only in header)",
                   flat.count("פלאנטיר, סרטן והכסף הפרטי") == 1))

    # 🔥 Deep Dive present, is the notability=5 book, NOT duplicated below.
    checks.append(("TG: 🔥 Deep Dive line present", "🔥 Deep Dive:" in msg))
    checks.append(("TG: 🔥 entity is the highest-notability one (book)",
                   "קיסר כל המחלות" in msg))
    checks.append(("TG: 🔥 entity not duplicated", flat.count("קיסר כל המחלות") == 1))
    dd_line = next(ln for ln in lines if ln.startswith("🔥 Deep Dive:"))
    checks.append(("TG: 🔥 line has no sentiment icon",
                   "📈" not in dd_line and "📉" not in dd_line))
    # FIX 1: context that starts with the entity name must not repeat it.
    dd_ctx = _strip_iso(dd_line.split("|", 1)[1]).strip() if "|" in dd_line else ""
    checks.append(("TG: 🔥 context does not repeat the name",
                   not dd_ctx.startswith("קיסר כל המחלות")
                   and _strip_iso(dd_line).count("קיסר כל המחלות") == 1))

    # Headings: exactly the four merged-section headings; concept = "מושגים לחקור".
    allowed = {"🧠 מושגים לחקור:", "🎯 רדאר חברות ומניות:",
               "🗣️ אנשים במרכז:", "📚 לקריאה:"}
    heading_lines = [ln for ln in lines
                     if ln.startswith(("🧠", "🎯", "🗣️", "📚", "💡", "🏢", "👤", "📰"))
                     and "<" not in ln]
    checks.append(("TG: only allowed merged headings (concept = 🧠 מושגים לחקור)",
                   bool(heading_lines) and all(ln in allowed for ln in heading_lines)))
    checks.append(("TG: concept heading verb 'מושגים לחקור' present",
                   "🧠 מושגים לחקור:" in msg))

    checks.append(("TG: place/other excluded",
                   "טוקיו" not in msg and "משהו" not in msg))

    # Attribution: two distinct speakers -> shown.
    checks.append(("TG: two speakers -> attribution shown", "(יונתן, גילי)" in msg))

    # Returning marker keeps the episode number (isolated).
    checks.append(("TG: returning marker '🔁 פרק 42'", "🔁 פרק 42" in flat))

    # Sentiment icons ONLY on stock/company (radar). NVIDIA +, Palantir -.
    nv_line = next(ln for ln in lines if "NVIDIA" in _strip_iso(ln))
    pal_line = next(ln for ln in lines if "Palantir" in _strip_iso(ln))
    concept_line = next(ln for ln in lines if "ערפל המלחמה" in ln)
    checks.append(("TG: 📈 on positive stock", "📈" in nv_line))
    checks.append(("TG: 📉 on negative company", "📉" in pal_line))
    checks.append(("TG: no sentiment icon on concept bullet",
                   "📈" not in concept_line and "📉" not in concept_line))
    checks.append(("TG: concept bullet context does not repeat the name",
                   _strip_iso(concept_line).count("ערפל המלחמה") == 1))

    # Links: ONLY in reading (article has link -> anchor); company link must NOT
    # become an anchor (radar uses plain bold even when a link exists).
    checks.append(("TG: reading article rendered as anchor",
                   '<a href="https://art.co">' in msg))
    checks.append(("TG: radar company link NOT anchored",
                   '<a href="https://x.co">' not in msg))
    # Ticker rendered (isolate-stripped) on the radar bullet.
    checks.append(("TG: ticker rendered", "(NVDA)" in flat))

    checks.append(("TG: platform footer 🔗 (YouTube+Spotify, no Apple)",
                   "🔗 להאזנה:" in msg and ">YouTube</a>" in msg
                   and ">Spotify</a>" in msg and ">Apple</a>" not in msg))
    checks.append(("TG: exactly one bit.ly DB link",
                   msg.count("https://bit.ly/tablefourdb") == 1))
    nonempty = [ln for ln in lines if ln.strip()]
    checks.append(("TG: DB link is the last line",
                   nonempty[-1].endswith("https://bit.ly/tablefourdb")))

    # Single-speaker episode: attribution should be DROPPED.
    solo_ep = {"number": 61, "date": "2026-06-26", "headline": "פרק יחיד"}
    solo_ents = [
        {"name": "TSMC", "type": "stock", "ticker": "TSM", "notability": 5,
         "context": "מובילה גלובלית בייצור שבבים מתקדמים", "mentioned_by": ["גילי"]},
        {"name": "Intel", "type": "stock", "ticker": "INTC", "notability": 3,
         "context": "מנסה להדביק את הפער", "mentioned_by": ["גילי"]},
    ]
    solo_msg = notify.build_telegram_message(solo_ep, solo_ents)
    checks.append(("TG: single speaker -> attribution dropped",
                   "(גילי)" not in solo_msg))

    print("== Telegram format checks ==")
    ok = True
    for n, p in checks:
        print(f"  [{'PASS' if p else 'FAIL'}] {n}")
        ok = ok and p
    return ok


def main():
    client = nb._client()

    tg_ok = test_telegram_format()

    print("== Step 0: ensure 'Recommended by' is multi_select ==")
    try:
        state = nb.ensure_recommended_by_multiselect(client)
        print(f"  Recommended by: {state}")
    except RuntimeError as e:
        print(f"  STOP: {e}")
        sys.exit(2)

    # Baseline Palantir mentions before this run (DB persists across reruns).
    base = nb._retry(
        client.data_sources.query,
        data_source_id=config.NOTION_ENTITIES_DS_ID,
        filter={"property": "Key", "rich_text": {"equals": "palantir"}},
    ).get("results", [])
    pal_base = (base[0]["properties"].get("Mentions", {}).get("number") or 0) if base else 0

    # Episode A: real bake-off transcript if present (exercises chunking),
    # else a small dummy. Episode B: small dummy.
    import os
    if os.path.exists("out_speechmatics.txt"):
        transcript_a = "out_speechmatics.txt"
        print("  using real out_speechmatics.txt for episode A")
    else:
        tfa = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
        tfa.write("[S1] שלום\n[S2] עולם\n")
        tfa.close()
        transcript_a = tfa.name
        print("  out_speechmatics.txt not found — using dummy for episode A")

    tfb = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    tfb.write("[S1] שלום\n[S2] עולם\n")
    tfb.close()

    print("== Step 1: process episode A ==")
    res_a = nb.process_episode(EPISODE_A, transcript_path=transcript_a, client=client)
    print(f"  A -> {res_a['status']}  page={res_a['episode_page_id']}")

    print("== Step 2: process episode B ==")
    res_b = nb.process_episode(EPISODE_B, transcript_path=tfb.name, client=client)
    print(f"  B -> {res_b['status']}  page={res_b['episode_page_id']}")

    print("== Step 3: verify ==")
    checks = []

    # Palantir single row, mentions=2, both episodes, both hosts.
    resp = nb._retry(
        client.data_sources.query,
        data_source_id=config.NOTION_ENTITIES_DS_ID,
        filter={"property": "Key", "rich_text": {"equals": "palantir"}},
    )
    pal = resp.get("results", [])
    checks.append(("Palantir is a single row", len(pal) == 1))
    if pal:
        p = pal[0]["properties"]
        mentions = p.get("Mentions", {}).get("number")
        checks.append(("Palantir Mentions +2 this run",
                       mentions == pal_base + 2))
        eps = _rel(p, "Episodes")
        checks.append(("Palantir linked to both episodes",
                       {res_a["episode_page_id"], res_b["episode_page_id"]} <= eps))
        rec = _multi(p, "Recommended by")
        checks.append(("Palantir recommended by both hosts", {"יונתן", "גילי"} <= rec))

    # Episode pages done + body populated.
    for label, res in (("A", res_a), ("B", res_b)):
        page = nb._retry(client.pages.retrieve, page_id=res["episode_page_id"])
        status = (page["properties"].get("Status", {}).get("select") or {}).get("name")
        checks.append((f"Episode {label} Status == done", status == "done"))
        kids = nb._retry(client.blocks.children.list, block_id=res["episode_page_id"])
        blocks = kids.get("results", [])
        checks.append((f"Episode {label} body has blocks", len(blocks) > 0))
        # The episode's "Entities" is populated by Notion's async dual-relation
        # sync from each entity's "Episodes" write — it can lag a second or two.
        # Re-read up to 3 times before declaring the relation empty.
        ents = _rel(page["properties"], "Entities")
        for _ in range(3):
            if len(ents) > 0:
                break
            time.sleep(2)
            page = nb._retry(client.pages.retrieve, page_id=res["episode_page_id"])
            ents = _rel(page["properties"], "Entities")
        checks.append((f"Episode {label} Entities relation populated (synced)", len(ents) > 0))

        # Body structure: summary heading, entities heading, >=1 entity bullet.
        def _btext(b):
            payload = b.get(b.get("type"), {})
            return "".join(p.get("plain_text", "") for p in payload.get("rich_text", []))
        texts = [_btext(b) for b in blocks]
        h2s = [t for b, t in zip(blocks, texts) if b.get("type") == "heading_2"]
        bullets = [t for b, t in zip(blocks, texts) if b.get("type") == "bulleted_list_item"]
        ent_names = [e["name"] for e in (EPISODE_A if label == "A" else EPISODE_B)["entities"]]
        checks.append((f"Episode {label} body has '📝 סיכום' heading",
                       any("📝 סיכום" in t for t in h2s)))
        checks.append((f"Episode {label} body has '🔑 ישויות' heading",
                       any("🔑 ישויות" in t for t in h2s)))
        checks.append((f"Episode {label} body has >=1 grouped entity bullet",
                       any(any(b.startswith(n) for n in ent_names) for b in bullets)))

        # Transcript child page exists under the episode, with content blocks.
        child_pages = [b for b in blocks if b.get("type") == "child_page"]
        checks.append((f"Episode {label} has a transcript child page", len(child_pages) >= 1))
        if child_pages:
            tkids = nb._retry(client.blocks.children.list, block_id=child_pages[0]["id"])
            checks.append((f"Episode {label} transcript page has content",
                           len(tkids.get("results", [])) > 0))

    print("\n==== PASS/FAIL ====")
    ok = tg_ok
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed

    print("\nTelegram: a message was attempted per episode (see above for errors).")
    print("Test pages are titled with 'TEST' prefix — inspect, then you can delete them.")
    print("\nRESULT:", "ALL PASS ✅" if ok else "SOME FAILED ❌")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
