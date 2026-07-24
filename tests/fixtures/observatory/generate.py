#!/usr/bin/env python3
"""Generate the synthetic observatory fixture corpus.

One-off authoring tool. Emits tests/fixtures/observatory/{extractions,transcripts}.
Everything here is invented: the show, hosts, entities, and one-liners are not real.
Deterministic — no randomness, so regenerating produces byte-identical output.
"""

import json
import os

OUT = os.path.dirname(os.path.abspath(__file__))
EXTRACT_DIR = os.path.join(OUT, "extractions")
TRANS_DIR = os.path.join(OUT, "transcripts")

DANA, NOAM, YUVAL, GUEST = "דנה", "נועם", "יובל", "אורח"

ACTION_BY_TYPE = {
    "person": "Follow", "company": "Watch", "stock": "Watch", "place": "Explore",
    "concept": "Learn", "book": "Read", "article": "Read", "other": None,
}


def ent(name, key, typ, notability, by, one_liner, *, ticker=None, link=None,
        context=None, ts=None, sentiment="neutral", is_tool=False):
    """Build one entity in the extract.py contract shape."""
    return {
        "name": name,
        "canonical_key": key,
        "type": typ,
        "notability": notability,
        "ticker": ticker,
        "one_liner": one_liner,
        "context": context or f"{name} עלה בשיחה על {one_liner[:20]}",
        "mentioned_by": list(by),
        "link": link,
        "timestamp": ts,
        "action": "Tool" if is_tool else ACTION_BY_TYPE.get(typ),
        "sentiment": sentiment,
        "is_tool": is_tool,
    }


# --- places: 6 geocoded (keys must hit PLACE_COORDS) + 2 deliberately not ------
P = [
    ("ישראל", "israel", 5), ("סין", "china", 5), ("ארצות הברית", "united states", 4),
    ("יפן", "japan", 3), ("הודו", "india", 3), ("גרמניה", "germany", 2),
    # These two must NOT resolve — they prove the UNGEOCODED report fires.
    ("עמק הסיליקון התחתון", "lower silicon valley", 2),
    ("איי התבלין", "spice islands", 1),
]
PEOPLE = [
    ("שרה חן", "sarah chen", 5), ("מרקו דל־רוסו", "marco del rosso", 4),
    ("פרופ׳ איימי לוין", "amy levin", 4), ("ג׳ורדן אוקafor", "jordan okafor", 3),
    ("הלנה ווס", "helena voss", 3), ("טום בריידי־הול", "tom brady-hall", 2),
    ("ריטה מוראלס", "rita morales", 2), ("קנג׳י אישיקווה", "kenji ishikawa", 1),
]
COMPANIES = [
    ("נורת׳ווינד", "northwind", "NWND", 5), ("אורביט לאבס", "orbit labs", "ORBT", 4),
    ("פייבר־קור", "fiber core", "FBRC", 4), ("הליוס", "helios energy", "HLOS", 3),
    ("סטארלייט", "starlight systems", "STLT", 3), ("קוואנטה", "quanta works", "QNTA", 2),
]
STOCKS = [
    ("מדד ה־T7", "t7 index", "T7X", 5), ("קרן הרכבות", "rail fund", "RAILF", 3),
    ("סל המוליכים", "semi basket", "SEMIB", 4), ("אג״ח ירוק", "green bond", "GRNB", 2),
]
CONCEPTS = [
    ("ריבונות חישובית", "compute sovereignty", 5),
    ("כלכלת תשומת הלב", "attention economy", 5),
    ("חוב טכני", "technical debt", 4),
    ("אפקט הרשת ההפוך", "reverse network effect", 4),
    ("תמחור דינמי", "dynamic pricing", 4),
    ("שרשרת אספקה קצרה", "short supply chain", 3),
    ("ממשל אלגוריתמי", "algorithmic governance", 3),
    ("הון סבלני", "patient capital", 3),
    ("עקומת האימוץ", "adoption curve", 3),
    ("סיכון זנב", "tail risk", 2),
    ("מלכודת הבינוניות", "mediocrity trap", 2),
    ("כשל התיאום", "coordination failure", 2),
    ("דחיסת שוליים", "margin compression", 4),
    ("אפקט ההילה", "halo effect", 1),
]
BOOKS = [
    ("המפעל השקט", "the quiet factory", "book", 5),
    ("שוליים", "margins", "book", 4),
    ("איך נבנו הגשרים", "how bridges were built", "book", 4),
    ("זיכרון של מכונה", "machine memory", "book", 3),
    ("הדרך הארוכה הביתה", "the long way home", "book", 3),
    ("ספר החול השני", "the second book of sand", "book", 2),
    ("על קצב וריבית", "on tempo and interest", "article", 4),
    ("מי מחזיק את הכבלים", "who holds the cables", "article", 3),
]

TRANSCRIPT_1 = """דנה: אז כאילו, בואו נתחיל. השבוע דיברנו הרבה על ריבונות חישובית.
נועם: כאילו זה הנושא שחוזר כל הזמן. חחחח, כן.
דנה: שרה חן כתבה על זה מאמר מצוין. compute sovereignty זה לא באזז־וורד.
יובל: אני חושב שהמפעל השקט הוא הספר הכי חשוב שקראתי השנה. כאילו, ברצינות.
נועם: ישראל וסין נמצאות בשתי נקודות הפוכות של העקומה הזאת.
דנה: בדיוק. ואם מסתכלים על נורת׳ווינד, NWND, רואים את זה בדוחות.
יובל: חחחחח, אתה תמיד מגיע למניות.
נועם: כאילו זה מה שאני עושה. תמחור דינמי זה הסיפור האמיתי פה.
דנה: אוקיי, בואו נעבור לחלק הבא.
""" * 3

TRANSCRIPT_2 = """נועם: כאילו, הפרק הזה הוא על כלכלת תשומת הלב.
דנה: אפקט הרשת ההפוך. attention economy. זה מה שאנחנו רואים ב־orbit labs.
יובל: מרקו דל־רוסו אמר לי פעם שחוב טכני זה רק ריבית דריבית על החלטות גרועות.
נועם: חחחח, זה טוב. technical debt.
דנה: יפן והודו עושות את זה אחרת לגמרי.
יובל: כאילו, שוליים הוא ספר שכל אחד צריך לקרוא.
נועם: דחיסת שוליים היא הנושא של השנה הבאה, אני אומר לכם.
""" * 3


def episode(n, guid, title, date, dur, ents, *, headline=None, number="auto"):
    """number="auto" -> use n. Pass number=None for the unnumbered-special fixture."""
    return {
        "episode": {
            "number": n if number == "auto" else number,
            "title": title,
            "headline": headline or title,
            "date": date,
            "duration": dur,
            "audio_url": f"https://example.com/audio/{guid}.mp3",
            "youtube_url": f"https://example.com/yt/{guid}",
            "spotify_url": None,
            "apple_url": f"https://example.com/apple/{guid}",
            "guid": guid,
        },
        "summary": f"סיכום לדוגמה לפרק {n}. הכול מומצא לצורך בדיקות.",
        "headline": headline or title,
        "entities": ents,
    }


def build():
    eps = []

    # --- ep 1: transcript exists; broad spread ---------------------------------
    e = [
        ent("ישראל", "israel", "place", 5, [DANA, NOAM], "מרכז טכנולוגי קטן וצפוף", ts="04:12"),
        ent("סין", "china", "place", 5, [NOAM], "השחקן השני בכל שיחה על שרשראות אספקה", ts="12:40"),
        ent("ארצות הברית", "united states", "place", 4, [DANA, YUVAL], "עדיין קובעת את הקצב"),
        ent("שרה חן", "sarah chen", "person", 5, [DANA], "חוקרת מדיניות חישוב",
            link="https://example.com/sarah", ts="06:00"),
        ent("נורת׳ווינד", "northwind", "company", 5, [NOAM], "יצרנית תשתית רשת",
            ticker="NWND", sentiment="positive", ts="18:20"),
        ent("ריבונות חישובית", "compute sovereignty", "concept", 5, [DANA, NOAM, YUVAL],
            "מי שולט על שבבי החישוב שלך"),
        ent("המפעל השקט", "the quiet factory", "book", 5, [YUVAL],
            "איך תעשייה נבנית בלי רעש", link="https://example.com/book1"),
        ent("תמחור דינמי", "dynamic pricing", "concept", 4, [NOAM], "המחיר משתנה לפי מי אתה"),
        ent("מדד ה־T7", "t7 index", "stock", 5, [NOAM], "סל שבע החברות הגדולות",
            ticker="T7X", sentiment="positive"),
        ent("כלי הניתוח שלנו", "our analysis tool", "other", 2, [DANA],
            "סקריפט קטן שדנה כתבה", is_tool=True),
    ]
    eps.append(episode(1, "ep1", "הפרק הראשון", "2025-01-06", "1:12:30", e,
                       headline="ריבונות חישובית מתחילה בבית"))

    # --- ep 2: transcript exists ----------------------------------------------
    e = [
        ent("יפן", "japan", "place", 3, [DANA], "מעבדה דמוגרפית לכל העולם"),
        ent("הודו", "india", "place", 3, [YUVAL], "הצמיחה הכי מדוברת בעשור"),
        ent("מרקו דל־רוסו", "marco del rosso", "person", 4, [YUVAL], "משקיע ותיק וציניקן",
            link="https://example.com/marco"),
        ent("אורביט לאבס", "orbit labs", "company", 4, [DANA], "לוויינים קטנים במחיר נמוך",
            ticker="ORBT", sentiment="positive"),
        ent("כלכלת תשומת הלב", "attention economy", "concept", 5, [NOAM, DANA],
            "הקשב שלך הוא המוצר"),
        ent("אפקט הרשת ההפוך", "reverse network effect", "concept", 4, [DANA],
            "לפעמים יותר משתמשים זה גרוע יותר"),
        ent("חוב טכני", "technical debt", "concept", 4, [YUVAL, NOAM],
            "ריבית דריבית על החלטות גרועות"),
        ent("דחיסת שוליים", "margin compression", "concept", 4, [NOAM],
            "כשהרווח נשחק משני הצדדים"),
        ent("שוליים", "margins", "book", 4, [YUVAL], "על מה שנשאר אחרי שהכול נמכר"),
        ent("סל המוליכים", "semi basket", "stock", 4, [NOAM], "חשיפה רחבה לשבבים",
            ticker="SEMIB", sentiment="negative"),
    ]
    eps.append(episode(2, "ep2", "הפרק השני", "2025-01-13", "58:10", e,
                       headline="הקשב הוא המוצר"))

    # --- ep 3: XSS regression fixtures live here -------------------------------
    e = [
        ent("סין", "china", "place", 4, [NOAM, YUVAL], "חוזרת שוב"),
        ent("גרמניה", "germany", "place", 2, [DANA], "התעשייה הכבדה של אירופה"),
        # XSS fixture #1: script tag in an LLM-authored one_liner.
        ent("הלנה ווס", "helena voss", "person", 3, [DANA],
            "אנליסטית <script>alert('xss')</script> אנרגיה"),
        # XSS fixture #2: javascript: URL in the link field.
        ent("פייבר־קור", "fiber core", "company", 4, [NOAM], "סיבים אופטיים לתעשייה",
            ticker="FBRC", link="javascript:alert(1)"),
        ent("ממשל אלגוריתמי", "algorithmic governance", "concept", 3, [YUVAL],
            "כשהכלל נאכף בקוד"),
        ent("הון סבלני", "patient capital", "concept", 3, [DANA], "כסף שיודע לחכות"),
        ent("איך נבנו הגשרים", "how bridges were built", "book", 4, [YUVAL],
            "הנדסה כסיפור חברתי"),
        ent("על קצב וריבית", "on tempo and interest", "article", 4, [NOAM],
            "מאמר קצר על מדיניות מוניטרית", link="https://example.com/article1"),
        ent("קרן הרכבות", "rail fund", "stock", 3, [NOAM], "תשתית משעממת ורווחית",
            ticker="RAILF"),
    ]
    eps.append(episode(3, "ep3", "הפרק השלישי", "2025-01-20", "1:04:00", e,
                       headline="כשהכלל נאכף בקוד"))

    # --- ep 4: the diarization-blanked episode (mentioned_by == [] everywhere) --
    e = [
        ent("עמק הסיליקון התחתון", "lower silicon valley", "place", 2, [],
            "מקום מומצא שלא אמור להיות ממופה"),
        ent("איי התבלין", "spice islands", "place", 1, [],
            "עוד מקום מומצא בלי קואורדינטות"),
        ent("פרופ׳ איימי לוין", "amy levin", "person", 4, [], "חוקרת מדיניות תחרות"),
        ent("הליוס", "helios energy", "company", 3, [], "אנרגיה סולארית תעשייתית",
            ticker="HLOS"),
        ent("עקומת האימוץ", "adoption curve", "concept", 3, [], "מי קונה ראשון ומי אחרון"),
        ent("סיכון זנב", "tail risk", "concept", 2, [], "האירוע הנדיר שהורס הכול"),
        ent("זיכרון של מכונה", "machine memory", "book", 3, [], "על מה שמחשבים לא שוכחים"),
        ent("אג״ח ירוק", "green bond", "stock", 2, [], "חוב עם תווית סביבתית", ticker="GRNB"),
    ]
    eps.append(episode(4, "ep4", "הפרק הרביעי", "2025-01-27", "47:55", e,
                       headline="פרק בלי ייחוס דוברים"))

    # --- ep 5: the guest episode + shortest --------------------------------------
    e = [
        ent("ישראל", "israel", "place", 4, [GUEST, DANA], "שוב, מרכז צפוף"),
        ent("ג׳ורדן אוקafor", "jordan okafor", "person", 3, [GUEST], "יזם תשתיות"),
        ent("ריטה מוראלס", "rita morales", "person", 2, [DANA], "עיתונאית כלכלית"),
        ent("סטארלייט", "starlight systems", "company", 3, [GUEST, NOAM],
            "תקשורת לוויינית", ticker="STLT", sentiment="positive"),
        ent("שרשרת אספקה קצרה", "short supply chain", "concept", 3, [GUEST],
            "לייצר קרוב לבית"),
        ent("כשל התיאום", "coordination failure", "concept", 2, [DANA],
            "כולם רוצים, אף אחד לא זז"),
        ent("הדרך הארוכה הביתה", "the long way home", "book", 3, [YUVAL], "מסע ומסחר"),
        ent("מי מחזיק את הכבלים", "who holds the cables", "article", 3, [NOAM],
            "על תשתית האינטרנט הפיזית", link="https://example.com/article2"),
    ]
    eps.append(episode(5, "ep5", "הפרק החמישי", "2025-02-03", "31:20", e,
                       headline="לייצר קרוב לבית"))

    # --- ep 6: the longest episode ----------------------------------------------
    e = [
        ent("ארצות הברית", "united states", "place", 5, [DANA, NOAM, YUVAL], "הקצב"),
        ent("סין", "china", "place", 5, [NOAM], "השחקן השני"),
        ent("יפן", "japan", "place", 3, [YUVAL], "מעבדה דמוגרפית"),
        ent("שרה חן", "sarah chen", "person", 5, [DANA, NOAM], "חוקרת מדיניות חישוב"),
        ent("טום בריידי־הול", "tom brady-hall", "person", 2, [YUVAL], "פרשן ותיק"),
        ent("נורת׳ווינד", "northwind", "company", 5, [NOAM, DANA], "תשתית רשת",
            ticker="NWND", sentiment="positive"),
        ent("קוואנטה", "quanta works", "company", 2, [YUVAL], "קבלן משנה", ticker="QNTA"),
        ent("ריבונות חישובית", "compute sovereignty", "concept", 5, [DANA, YUVAL],
            "מי שולט על השבבים"),
        ent("מלכודת הבינוניות", "mediocrity trap", "concept", 2, [NOAM],
            "מספיק טוב זה אויב של טוב"),
        ent("אפקט ההילה", "halo effect", "concept", 1, [DANA], "מותג טוב מכסה על מוצר בינוני"),
        ent("ספר החול השני", "the second book of sand", "book", 2, [YUVAL], "אוסף סיפורים"),
        ent("מדד ה־T7", "t7 index", "stock", 5, [NOAM], "סל שבע הגדולות", ticker="T7X",
            sentiment="positive"),
    ]
    eps.append(episode(6, "ep6", "הפרק השישי", "2025-02-10", "2:03:45", e,
                       headline="הפרק הארוך של העונה"))

    # --- ep 7: the number:null episode (unnumbered special) ---------------------
    e = [
        ent("הודו", "india", "place", 3, [DANA], "צמיחה"),
        ent("קנג׳י אישיקווה", "kenji ishikawa", "person", 1, [YUVAL], "ארכיטקט"),
        ent("אורביט לאבס", "orbit labs", "company", 4, [DANA, NOAM], "לוויינים קטנים",
            ticker="ORBT"),
        ent("חוב טכני", "technical debt", "concept", 4, [YUVAL], "ריבית דריבית"),
        ent("כלכלת תשומת הלב", "attention economy", "concept", 5, [NOAM], "הקשב הוא המוצר"),
        ent("שוליים", "margins", "book", 4, [YUVAL], "מה שנשאר"),
    ]
    eps.append(episode(7, "special", "פרק מיוחד ללא מספר", "2025-02-14", "39:00", e,
                       headline="מיוחד: בלי מספר", number=None))

    # --- ep 8: recent, thin ------------------------------------------------------
    e = [
        ent("ישראל", "israel", "place", 3, [NOAM], "סגירת מעגל"),
        ent("גרמניה", "germany", "place", 2, [DANA], "תעשייה כבדה"),
        ent("הלנה ווס", "helena voss", "person", 3, [DANA, NOAM], "אנליסטית אנרגיה"),
        ent("הליוס", "helios energy", "company", 3, [NOAM], "סולארי", ticker="HLOS",
            sentiment="positive"),
        ent("תמחור דינמי", "dynamic pricing", "concept", 4, [DANA], "מחיר משתנה"),
        ent("דחיסת שוליים", "margin compression", "concept", 4, [NOAM], "רווח נשחק"),
        ent("הון סבלני", "patient capital", "concept", 3, [YUVAL], "כסף שמחכה"),
        ent("איך נבנו הגשרים", "how bridges were built", "book", 4, [YUVAL], "הנדסה חברתית"),
        ent("סל המוליכים", "semi basket", "stock", 4, [NOAM], "שבבים", ticker="SEMIB"),
    ]
    eps.append(episode(8, "ep8", "הפרק השמיני", "2025-02-17", "1:08:15", e,
                       headline="סגירת מעגל"))

    return eps


def main():
    os.makedirs(EXTRACT_DIR, exist_ok=True)
    os.makedirs(TRANS_DIR, exist_ok=True)
    eps = build()
    for e in eps:
        guid = e["episode"]["guid"]
        path = os.path.join(EXTRACT_DIR, f"{guid}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(e, f, ensure_ascii=False, indent=2)
            f.write("\n")
    # Only 2 of 8 -> the partial-transcript path is exercised.
    for guid, text in (("ep1", TRANSCRIPT_1), ("ep2", TRANSCRIPT_2)):
        with open(os.path.join(TRANS_DIR, f"{guid}.txt"), "w", encoding="utf-8") as f:
            f.write(text)

    n_ent = sum(len(e["entities"]) for e in eps)
    types = {}
    for e in eps:
        for x in e["entities"]:
            types[x["type"]] = types.get(x["type"], 0) + 1
    print(f"episodes: {len(eps)}  entities: {n_ent}")
    print("by type:", dict(sorted(types.items())))
    print("unique concepts:", len({x['canonical_key'] for e in eps
                                   for x in e['entities'] if x['type'] == 'concept'}))
    print("unique books/articles:", len({x['canonical_key'] for e in eps
                                         for x in e['entities']
                                         if x['type'] in ('book', 'article')}))
    print("unique places:", len({x['canonical_key'] for e in eps
                                 for x in e['entities'] if x['type'] == 'place'}))


if __name__ == "__main__":
    main()
