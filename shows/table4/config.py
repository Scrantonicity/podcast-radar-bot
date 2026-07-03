"""shows/table4/config.py — the real "שולחן 4" (Table 4) show config.

This is the working EXAMPLE: a Hebrew, RTL podcast. Copy shows/_template/ for a
new show; use this as a reference for a fully-filled config.
"""

from showkit import ShowConfig

SHOW = ShowConfig(
    display_name="שולחן 4",

    # Feed: Apple/iTunes podcast id -> RSS resolved via the iTunes lookup.
    feed_apple_id="1823006955",

    # Language / STT
    stt_language="he",
    # Novel brand/proper names Speechmatics keeps mishearing go here (additional_vocab).
    stt_additional_vocab=("Fable 5", "Mythos", "Palantir", "Anthropic"),
    text_direction="rtl",
    date_format="%d.%m.%y",

    # Hosts — SINGLE SOURCE OF TRUTH (short forms). The prompt names them too.
    hosts=("גילי", "ערן", "יהונתן"),
    guest_label="אורח",
    # Every script/spelling a host might leak under (incl. the old יונתן spelling).
    host_ban_keys=frozenset({
        "gili biman", "gili", "eran gefen", "eran", "yonatan adiri", "yonatan",
        "גילי בימן", "גילי", "ערן גפן", "ערן", "יונתן אדירי", "יונתן",
        "יהונתן אדירי", "יהונתן",
    }),
    # Paid sponsors / ad-reads — dropped like listeners (never editorial entities).
    sponsor_ban_keys=frozenset({
        "eco supp", "ecosupp", "eco sup", "אקו סאפ", "אקוסאפ",
        "cover", "קאבר",
        "kiara naturals", "kiara", "קיארה naturals", "קיארה",
        "green invoice", "חשבונית ירוקה",
    }),

    db_link="https://bit.ly/tablefourdb",

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
