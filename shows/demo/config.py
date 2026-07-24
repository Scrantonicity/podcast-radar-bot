"""shows/demo/config.py — a fictional Hebrew demo show ("רדאר").

This is the working EXAMPLE: a Hebrew, RTL podcast, fully invented for demonstration
(the hosts, sponsors, and feed are not real). Copy shows/_template/ for a new show;
use this as a reference for a fully-filled config.
"""

from showkit import ShowConfig

SHOW = ShowConfig(
    display_name="רדאר",

    # Feed: point at your show. Apple/iTunes id -> RSS via the iTunes lookup, OR a
    # direct RSS url. Placeholders here — this demo show is not a real feed.
    feed_apple_id=None,
    feed_rss_url="https://example.com/feed.xml",

    # Language / STT
    stt_language="he",
    # Novel brand/proper names Speechmatics keeps mishearing go here (additional_vocab).
    stt_additional_vocab=("Fable 5", "Mythos", "Palantir", "Anthropic"),
    text_direction="rtl",
    date_format="%d.%m.%y",

    # Hosts — SINGLE SOURCE OF TRUTH (short forms). The prompt names them too.
    hosts=("דנה", "נועם", "יובל"),
    guest_label="אורח",
    # Every script/spelling a host might leak under (lowercase, all spellings).
    host_ban_keys=frozenset({
        "dana", "noam", "yuval",
        "דנה", "נועם", "יובל",
    }),
    # Paid sponsors / ad-reads — never treated as editorial entities.
    sponsor_ban_keys=frozenset({
        "demo brand", "מותג לדוגמה", "חברת דוגמה",
    }),

    # Public link to your Notion entities DB, shown in the digest footer.
    db_link="https://example.com/db",

    # Hebrew -> Latin romanization for cross-script dedup ("אנבידיה" ~ "Nvidia").
    # Best-effort for RECALL, not a faithful transliteration. Digraphs (geresh forms)
    # are applied before singles.
    native_script_re=r"[֐-׿]",
    translit_digraphs={
        "ג'": "j", "ז'": "zh", "צ'": "ch", "ץ'": "ch", "ד'": "dh", "ת'": "th",
    },
    translit_singles={
        "א": "", "ב": "b", "ג": "g", "ד": "d", "ה": "h", "ו": "v", "ז": "z",
        "ח": "h", "ט": "t", "י": "y", "כ": "k", "ך": "k", "ל": "l", "מ": "m",
        "ם": "m", "נ": "n", "ן": "n", "ס": "s", "ע": "", "פ": "p", "ף": "f",
        "צ": "ts", "ץ": "ts", "ק": "k", "ר": "r", "ש": "sh", "ת": "t",
        "ְ": "", "ֱ": "e", "ֲ": "a", "ֳ": "o", "ִ": "i",
        "ֵ": "e", "ֶ": "e", "ַ": "a", "ָ": "a", "ֹ": "o",
        "ֻ": "u", "ּ": "", "ׁ": "", "ׂ": "", "׳": "",
        "״": "",
    },

    # Telegram digest layout (RTL, Hebrew headings).
    tg_sections=(
        {"heading": "🧠 מושגים לחקור:", "types": ("concept",)},
        {"heading": "🎯 רדאר חברות ומניות:", "types": ("stock", "company")},
        {"heading": "🗣️ אנשים במרכז:", "types": ("person",)},
        {"heading": "📚 לקריאה:", "types": ("book", "article")},
    ),
    tg_type_caps={"concept": 3, "book": 4, "article": 4, "stock": 4, "company": 4, "person": 4},
    tg_global_cap=13,
    tg_trim_order=("concept", "person", "company", "stock", "article", "book"),
    reading_types=frozenset({"book", "article"}),
    sentiment_types=frozenset({"stock", "company"}),
    name_article_prefixes=("ה",),   # Hebrew definite article clitic

    # Notion episode-page body labels (Hebrew).
    notion_type_labels={
        "person": "👤 אנשים",
        "company": "🏢 חברות",
        "stock": "📈 מניות",
        "place": "🌍 מקומות",
        "concept": "💡 מושגים",
        "book": "📚 ספרים",
        "article": "📰 כתבות",
        "other": "📌 נוסף",
    },
    notion_learn_type_nouns={
        "person": "אדם",
        "company": "חברה",
        "stock": "מניה",
        "place": "מקום",
        "concept": "מושג",
        "book": "ספר",
        "article": "כתבה",
    },
)
