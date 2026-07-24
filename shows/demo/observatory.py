"""shows/demo/observatory.py — the observatory for the demo show ("רדאר").

A worked example of the optional fourth show file: Hebrew, RTL, three hosts, and a
theme that has nothing to do with the default. Copy shows/_template/observatory.py
for a new show; read this one to see what a filled-in version looks like.

Two things to notice, because they are the whole design:

1. NOT ONE NUMBER IS WRITTEN HERE. Every caption interpolates a `{field}` that
   build_observatory.py computed from the archive. That's why the page can't go
   stale: it says "{pct}% of episodes", never "25% of episodes".

2. Nothing here is engine code. The theme, the words, and the section list are this
   show's; the arithmetic is the build's. See OBSERVATORY.md.
"""

from showkit import Copy, Observatory, SectionCopy, Theme

# ---------------------------------------------------------------------------
# Theme — a radar screen: phosphor green on deep navy, amber for the alerts.
# Deliberately nothing like the default, to prove a theme swap reaches everything:
# the globe, the shelf, the bubbles and the charts all read these back at runtime.
# ---------------------------------------------------------------------------
THEME = Theme(
    bg="#050a10", bg2="#081420", panel="#0c1c2b", panel2="#112a3d",

    accent="#2ee6a8", accent_dim="#1a9e73", accent2="#0f6f57", accent2_glow="#4dffc3",
    highlight="#ffb454", highlight2="#ffd08a", highlight_soft="#ffe8c4",

    ink="#e8f6f0", muted="#8fb3a6", muted2="#5a7a70",
    line="rgba(46,230,168,.16)",

    # One per entity type in shows/demo/config.py. Distinct hues that all survive a
    # dark background — this is the legend for the whole page.
    type_colors={
        "person": "#ffb454",    # amber, the show's second voice
        "place": "#2ee6a8",     # phosphor green — the radar itself
        "stock": "#7ef58a",
        "company": "#63c8ff",
        "concept": "#c79bff",
        "book": "#ff9d5c",
        "article": "#ff7b8a",
        "other": "#8fa6c9",
    },

    # The shelf keeps its own wooden world; only the gold is pulled toward the amber.
    shelf_wood="#241a12", shelf_wood2="#120b06",
    shelf_gold="#d9a154", shelf_gold_soft="#f0d9a8", shelf_parch="#f2e6cd",

    # A radar's globe: green land on a near-black ocean, green sweep arcs.
    globe_ocean="#061520", globe_land="#123d33", globe_border="rgba(46,230,168,.35)",
    globe_graticule="rgba(46,230,168,.10)", globe_rim="rgba(46,230,168,.45)",
    globe_arc_rgb="255,180,84", globe_dot_rgb="46,230,168",

    cloud_ramp=("#0f6f57", "#1a9e73", "#2ee6a8", "#ffb454", "#ffd08a"),
    cloud_label_ink="#04140e",

    star_color="#d8fff0", star_color2="#9effd8",

    # Left on the system stacks on purpose: a Google Fonts <link> is a network call
    # on every view (and an EU privacy question) for a page whose selling point is
    # that it works from a file:// URL on a plane. To opt in anyway:
    #   font_link="https://fonts.googleapis.com/css2?family=Secular+One&family=Heebo:wght@300;400;700;900&display=swap",
    #   font_display='"Secular One", system-ui, sans-serif',
    font_sans='"Heebo", "Assistant", system-ui, sans-serif',
    font_display='"Secular One", "Heebo", system-ui, sans-serif',
    font_serif='"Frank Ruhl Libre", Georgia, serif',
    font_libserif='"Frank Ruhl Libre", Georgia, serif',
    font_mono='"Azeret Mono", ui-monospace, Menlo, monospace',
)

# ---------------------------------------------------------------------------
# Copy — every word on the page.
# ---------------------------------------------------------------------------
COPY = Copy(
    page_title="רדאר · מצפה הנתונים",

    # --- hero ---
    # {episodes} {hours} {entities} {places}. The figures arrive from the build.
    hero_kicker="מצפה הנתונים · {episodes} פרקים · {hours} שעות",
    # Raw HTML on purpose — the wordmark accents its last letter. This is the one
    # field where markup is expected; it's authored here, never from the model.
    hero_title_html='רד<span class="ac">אר</span>',
    hero_lead_html=(
        "כל שם, מקום, מניה, ספר ורעיון שעלו בשיחה — "
        "<b>נחפרו מהתמלולים</b> והפכו למפה אחת."
    ),
    hero_scroll_hint="יאללה, גוללים פנימה",
    counter_labels={
        "episodes": "פרקים",
        "entities": "ישויות",
        "places": "מקומות בעולם",
        "people": "אנשים",
        "books": "ספרים וכתבות",
    },

    nav_labels={
        "hero": "פתיחה", "globe": "הגלובוס", "library": "הספרייה", "records": "שיאים",
        "funfacts": "עובדות", "hostface": "דו־קרב", "leaders": "טבלת הליגה",
        "cloud": "רעיונות", "pulse": "הדופק", "wordlab": "השפה", "graph": "קשרים",
    },

    # --- sections ---
    globe=SectionCopy(
        eyebrow="01 · הגלובוס",
        heading="העולם של רדאר",
        sub="כל מקום שעלה בשיחה, בגודל לפי כמה דיברו עליו. קו בין שתי נקודות אומר "
            "שהן חלקו פרק. סובבו את הכדור, לחצו על נקודה.",
    ),
    library=SectionCopy(
        eyebrow="02 · הספרייה",
        heading="מה הומלץ לקרוא",
        sub="כל ספר וכתבה שקיבלו אזכור, על מדף אחד. העבירו עכבר על ספר.",
    ),
    records=SectionCopy(
        eyebrow="03 · טבלת השיאים",
        heading="שיאים ושברי־שיאים",
        sub="מי הכי, מה הכי, ואיפה מסתתרות הפינות המוזרות של המסד.",
    ),
    funfacts=SectionCopy(
        eyebrow="04 · מגירת הפינות",
        heading="עובדות שלא חשבתם לחפש",
        sub="דברים שאף אחד לא חיפש, אבל אי אפשר להפסיק לקרוא.",
    ),
    hostface=SectionCopy(
        eyebrow="05 · דו־קרב",
        heading="מי מביא מה לרדאר",
        sub="כל אזכור שיוחס למנחה, מפורק לפי קטגוריה. הגרף משווה שניים — "
            "שני המנחים עם הכי הרבה אזכורים מיוחסים.",
    ),
    leaders=SectionCopy(
        eyebrow="06 · טבלת הליגה",
        heading="מצעד המוזכרים",
        sub="המובילים בכל קטגוריה — ורמת ה״חפירה״ של האזכורים.",
    ),
    cloud=SectionCopy(
        eyebrow="07 · ענן הרעיונות",
        heading="על מה באמת מדברים",
        sub="כל מושג שעלה, בגודל לפי כמה חזר. העבירו עכבר לפרטים.",
    ),
    pulse=SectionCopy(
        eyebrow="08 · הדופק",
        heading="הקצב של הפודקאסט",
        sub="ממה הורכב כל פרק לאורך הזמן. עברו עם העכבר על פרק.",
    ),
    wordlab=SectionCopy(
        eyebrow="09 · השפה",
        heading="איך מדברים ברדאר",
        sub="נספר מהתמלולים — המילים שחוזרות, והטיקרים שנאמרו בקול.",
    ),
    graph=SectionCopy(
        eyebrow="10 · מפת הקשרים",
        heading="מי מוזכר עם מי",
        sub="שתי ישויות מחוברות אם עלו יחד באותו פרק. גררו, עשו זום, "
            "ולחצו על צומת כדי להאיר את מי שסביבו.",
    ),
    # Off, and staying off: this section is for a real running bit the show actually
    # has. There isn't one to invent for a demo. See OBSERVATORY.md.
    shoutouts=SectionCopy(enabled=False),

    # --- shared units ---
    episodes_word="פרקים",
    episode_label_tpl="פרק {n}",
    episode_unnumbered="פרק מיוחד",
    type_labels={
        "person": "אנשים", "place": "מקומות", "stock": "מניות", "company": "חברות",
        "concept": "מושגים", "book": "ספרים", "article": "כתבות", "other": "נוסף",
    },

    globe_legend="● גודל = אזכורים · קו = הוזכרו יחד",
    globe_dossier_hint="לחצו על נקודה בגלובוס כדי לפתוח את התיק שלה",

    book_kind_labels={"book": "ספר", "article": "כתבה"},
    book_recommended_by="{host} המליץ",
    book_appeared_in="הופיע ב{n}",
    book_gem_chip="💎 פנינה נדירה",

    # --- records: {n}, {name}, {label}, {len}, {one_liner} come from the build ---
    records_cards={
        "top_person": {"title": "👤 שם על כל שפה", "cap": "{name} — האדם המוזכר ביותר, ב־{n} פרקים"},
        "top_place": {"title": "🌍 המקום הכי מדובר", "cap": "{one_liner}"},
        "top_stock": {"title": "📈 מניית הבית", "cap": "המניה המדוברת, ב־{n} פרקים"},
        "top_company": {"title": "🏢 חברת השיחה", "cap": "החברה המוזכרת, ב־{n} פרקים"},
        "top_concept": {"title": "💡 המושג המוביל", "cap": "הרעיון המדובר, ב־{n} פרקים"},
        "top_book": {"title": "📚 הספר המדובר", "cap": "חזר ב־{n} פרקים"},
        "top_article": {"title": "📰 הכתבה המדוברת", "cap": "חזרה ב־{n} פרקים"},
        "top_other": {"title": "📌 המוזכר הנוסף", "cap": "עלה ב־{n} פרקים"},
        "gems": {"title": "💎 פנינים נדירות", "cap": "{n} ישויות בדרגת החפירה הגבוהה ביותר"},
        "busiest": {"title": "🔥 הפרק העמוס", "cap": "{n} ישויות בפרק אחד · {headline}"},
        "most_places": {"title": "🗺️ הפרק הכי גלובלי", "cap": "{n} מקומות שונים בפרק אחד"},
        "host_counts": {"title": "🎙️ קרב המנחים", "cap": "סך האזכורים המיוחסים לכל מנחה"},
        "longest_name": {"title": "📏 השם הארוך", "cap": "{len} תווים · «{name}»"},
        "type_totals": {"title": "🧮 סך הכל במסד", "cap": ""},
    },

    # --- fun facts: the caption fields per id are listed in OBSERVATORY.md ---
    funfact_copy={
        "regular_star": {"title": "הכוכב הקבוע", "cap": "{name} צץ ב-{pct}% מהפרקים. אי אפשר בלעדיו"},
        "hours_in_ears": {"title": "שעות באוזניים", "cap": "{hours} שעות של רדאר — כמעט {days} ימים רצופים"},
        "busiest_episode": {"title": "פרק הפיצוץ", "cap": "{label} — {n} ישויות בפרק אחד, שיא הבית"},
        "one_hit_wonders": {"title": "כאן היום, אין מחר", "cap": "{n} ישויות קיבלו אזכור אחד — ונעלמו"},
        "inseparable_pair": {"title": "הצמד שלא נפרד", "cap": "{a} ו{b} הופיעו יחד ב-{n} פרקים"},
        "marathon": {"title": "המרתון", "cap": "{label} — הפרק שהכי לא רצה להיגמר ({dur})"},
        "returning_faces": {"title": "החוזרים בתשובה", "cap": "{n} ישויות חזרו ליותר מפרק אחד"},
        "rarest_gem": {"title": "פנינים נדירות", "cap": "{n} ישויות קיבלו את ציון החפירה הגבוה ביותר"},
        "globetrotter_host": {"title": "מי הכי מטייל", "cap": "{host} לבד סימן ברדאר {n} מקומות שונים"},
        "reading_shelf": {"title": "מדף ההמלצות", "cap": "{n} ספרים וכתבות — בערך {per_ep} לפרק"},
        "average_episode": {"title": "פרק ממוצע", "cap": "בערך {n} ישויות נדחסות לכל פרק, ב-{mins} דקות"},
        "lightest_episode": {"title": "הכי קליל שהיה", "cap": "{label} — נגמר תוך {dur}"},
        "longest_name": {"title": "הארוך בהיסטוריה", "cap": "«{name}» — {len} תווים"},
        "all_the_types": {"title": "כל הסוגים", "cap": "{n} קטגוריות: {kinds}"},
        "social_butterfly": {"title": "הפרפר החברתי", "cap": "{name} חלק פרק עם {n} ישויות שונות"},
        "word_avalanche": {"title": "מפל של מילים", "cap": "{n} מילים יצאו מהפה — בערך {per_ep} בכל פרק"},
    },
    # The order they appear in. An id left out here simply isn't rendered — that's how
    # you drop a fact you don't like without touching code.
    funfact_order=(
        "regular_star", "hours_in_ears", "busiest_episode", "inseparable_pair",
        "one_hit_wonders", "marathon", "returning_faces", "globetrotter_host",
        "rarest_gem", "reading_shelf", "average_episode", "social_butterfly",
        "longest_name", "all_the_types", "word_avalanche", "lightest_episode",
    ),

    # --- host face-off ---
    hostface_total_tpl="{n} אזכורים",
    # The eight raw types are too fine-grained to compare hosts on; four editorial
    # groups say something.
    hostface_groups=(
        {"label": "אנשים", "types": ("person",)},
        {"label": "מקומות", "types": ("place",)},
        {"label": "שווקים", "types": ("stock", "company")},
        {"label": "רעיונות", "types": ("concept",)},
        {"label": "קריאה", "types": ("book", "article")},
    ),

    # --- leaderboards: the first two get a column; the third slot is the histogram ---
    leader_col_headings={
        "person": "👤 האנשים",
        "place": "🌍 המקומות",
        "concept": "💡 המושגים",
        "company": "🏢 החברות",
        "stock": "📈 המניות",
    },
    notab_note="📊 רמת החפירה",
    notab_scale_labels=(
        "שם מוכר לכולם", "מוכר", "נישתי", "נישתי מאוד", "פנינה נדירה",
    ),

    # --- pulse: same idea as the face-off — group the taxonomy into streams ---
    timeline_streams=(
        {"key": "people", "label": "אנשים", "types": ("person",)},
        {"key": "geo", "label": "גאופוליטיקה", "types": ("place", "other")},
        {"key": "mkt", "label": "שווקים", "types": ("stock", "company")},
        {"key": "idea", "label": "רעיונות וקריאה", "types": ("concept", "book", "article")},
    ),
    timeline_tooltip_total="סה״כ ישויות",
    spark_strip_heading="מדד הנוכחות — מתי כל אחד היה על הרדאר",

    # --- word lab ---
    wl_stat_labels={
        "hours": "שעות תוכן",
        "total": "מילים נאמרו",
        "per_ep": "מילים בפרק ממוצע",
        "avg_min": "דקות לפרק",
        "latin_words": "מילים באנגלית",
        "laughs": "התפרצויות צחוק",
    },
    wl_words_heading="🗣️ המילים שחוזרות הכי הרבה",
    wl_ticker_heading="📈 קיר המניות",
    wl_ticker_note="כל טיקר שהוזכר אי־פעם, גולל בלולאה אחת ארוכה",
    # Counted as substrings, which is what you want in Hebrew: it catches the clitic
    # prefixes (ו/ה/ב/ל) that would otherwise each count as a different word.
    signature_words=(
        ("כאילו", "«כאילו»"),
        ("בדיוק", "«בדיוק»"),
        ("ברצינות", "«ברצינות»"),
        ("מטורף", "«מטורף»"),
        ("כסף", "«כסף»"),
        ("מלחמה", "«מלחמה»"),
    ),
    laugh_pattern=r"חחח+",

    graph_legend_title="סוג ישות",
    graph_hint="גרירה · גלגלת = זום · לחיצה = הדגשה",

    footer_logo_html='רד<span class="ac">אר</span>',
    footer_prov_tpl="נבנה מ־{entities} ישויות שחולצו מ־{episodes} פרקים · {from} — {to}",
    footer_links=(
        ("מסד הנתונים המלא ↗", "https://example.com/db"),
    ),
)

OBSERVATORY = Observatory(
    theme=THEME,
    copy=COPY,
    # Places the bundled lookup doesn't know. `build_observatory.py --dry-run` prints
    # exactly this list, ready to paste — these two are invented for the demo
    # fixtures, which is why no real gazetteer has them.
    extra_place_coords={
        "lower silicon valley": [37.32, -122.03],
        "spice islands": [-3.2, 129.0],
    },
)
