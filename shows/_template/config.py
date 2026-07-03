"""shows/_template/config.py — starter config for a NEW podcast.

Copy this whole folder:  cp -r shows/_template shows/mypodcast
then edit the three files (config.py, strings.py, prompt.txt) and set SHOW=mypodcast
in your .env. You never edit engine code. See README → "Add your own podcast".

Everything below with a TODO is required; the rest has sensible defaults.
"""

from showkit import ShowConfig

SHOW = ShowConfig(
    display_name="My Podcast",                       # TODO: your show's name

    # Feed source — supply exactly ONE:
    feed_apple_id=None,                              # TODO: Apple/iTunes podcast id, OR
    feed_rss_url="https://example.com/feed.xml",     # TODO: a direct RSS url

    # Language / speech-to-text
    stt_language="en",                              # TODO: Speechmatics code (en, he, es, ...)
    stt_additional_vocab=(),                        # optional: names the STT keeps mishearing
    text_direction="ltr",                           # "ltr" or "rtl"
    date_format="%b %d, %Y",                        # header date format (strftime)

    # Hosts — SINGLE SOURCE OF TRUTH. Short forms of your regular hosts. Name the
    # SAME people in prompt.txt. host_ban_keys is the safety net if one still leaks
    # in as an entity (include every spelling/transliteration).
    hosts=("Alex", "Sam"),                          # TODO
    guest_label="Guest",
    host_ban_keys=frozenset({"alex", "sam"}),       # TODO: lowercase, all spellings
    sponsor_ban_keys=frozenset(),                   # TODO: ad-read brands to drop

    db_link="",                                     # TODO: public link to your Notion DB

    # Telegram digest layout — sections in display order, one icon per heading.
    # Types not listed in any section stay in Notion but not the digest.
    tg_sections=(
        {"heading": "🧠 Concepts to explore:", "types": ("concept",)},
        {"heading": "🎯 Companies & stocks:", "types": ("stock", "company")},
        {"heading": "🗣️ People:", "types": ("person",)},
        {"heading": "📚 To read:", "types": ("book", "article")},
    ),
    tg_type_caps={"concept": 3, "book": 4, "article": 4, "stock": 4, "company": 4, "person": 4},
    tg_global_cap=13,
    tg_trim_order=("concept", "person", "company", "stock", "article", "book"),
    reading_types=frozenset({"book", "article"}),
    sentiment_types=frozenset({"stock", "company"}),
    name_article_prefixes=(),                       # e.g. ("the",) — usually empty

    # Notion episode-page body labels (per entity type).
    notion_type_labels={
        "person": "👤 People",
        "company": "🏢 Companies",
        "stock": "📈 Stocks",
        "place": "🌍 Places",
        "concept": "💡 Concepts",
        "book": "📚 Books",
        "article": "📰 Articles",
        "other": "📌 Other",
    },
    notion_learn_type_nouns={
        "person": "person",
        "company": "company",
        "stock": "stock",
        "place": "place",
        "concept": "concept",
        "book": "book",
        "article": "article",
    },
)
