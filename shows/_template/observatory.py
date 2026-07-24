"""shows/_template/observatory.py — starter theme + copy for the Podcast Observatory.

OPTIONAL. Delete this file and the page still builds: neutral dark theme, plain
English copy, your own entity types and hosts throughout. Fill it in to make the page
look and sound like your show. See OBSERVATORY.md — including how to hand this file
to an AI and have it filled in for you.

    python build_observatory.py --dry-run     # do this FIRST: which sections have data
    python build_observatory.py               # -> dist/<show>_observatory.html

THE ONE RULE: never write a computed number into prose. The build knows every figure
and passes it in as a {field}; a caption that spells one out is wrong the next time
you publish an episode.

    wrong:  hero_kicker="65 episodes · 88.9 hours"
    right:  hero_kicker="{episodes} episodes · {hours} hours"

Everything here is optional and falls back field by field: set only `heading` on a
section and it keeps the default eyebrow and sub. Delete what you don't want to say.
"""

from showkit import Copy, Observatory, SectionCopy, Theme

# ---------------------------------------------------------------------------
# Theme. Any CSS color works ("#0b0d14", "oklch(.2 .02 260)"). Every chart reads
# these back at runtime, so this object IS the look of the page — including the
# globe, the bubbles, and the bookshelf.
# ---------------------------------------------------------------------------
THEME = Theme(
    # --- surfaces, back to front ---
    bg="#0b0d14",          # TODO: the page behind everything
    bg2="#11141f",         # alternating section background
    panel="#171b29",       # cards
    panel2="#1e2333",      # card gradient top

    # --- brand: two colors do most of the work ---
    accent="#5b6cff",      # TODO: your primary
    accent_dim="#3d49b8",
    accent2="#2f3aa8",
    accent2_glow="#6b7aff",
    highlight="#e0a44a",   # TODO: your secondary — numbers, rules, the eyebrow
    highlight2="#f5c46e",
    highlight_soft="#f0dcb4",

    # --- text ---
    ink="#e8eaf5",         # body text. Keep >= 4.5:1 against bg.
    muted="#99a0c4",       # secondary text
    muted2="#676d91",      # captions
    line="rgba(140,150,220,.16)",   # every border on the page

    # --- one color per entity type: the legend for the whole page ---
    # Keys are your config.py's entity_types. A type you don't list falls back to
    # type_color_fallback; a type you don't have is ignored.
    type_colors={
        "person": "#e0a44a", "place": "#38d9c4", "stock": "#79e07a",
        "company": "#79c0ff", "concept": "#c79bff", "book": "#ff9d5c",
        "article": "#ff7b8a", "other": "#8b93c9",
    },

    # --- the bookshelf (its own little world; leave alone unless you want to fight it) ---
    # shelf_wood="#2b1a10", shelf_gold="#e0ad4e", shelf_parch="#efe0c0",
    # book_palette=(("#3a2418", "#1d1009"), ...),   # spine gradients, cycled

    # --- the globe. Arcs/dots animate their alpha, so those two are "r,g,b". ---
    # globe_ocean="#0c1030", globe_land="#241f57",
    # globe_arc_rgb="224,164,74", globe_dot_rgb="240,169,62",

    # --- the concept cloud: a ramp from rare to constant ---
    # cloud_ramp=("#3d49b8", "#5b6cff", "#c79bff", "#e0a44a", "#f5c46e"),
    # cloud_label_ink="#140b1e",    # text drawn ON a bubble — keep it dark

    # --- type. Defaults are system stacks: no network call, works offline. ---
    # A Google Fonts link is a request on every view (and an EU privacy question)
    # for a page whose whole point is being self-contained. Opt in knowingly:
    # font_link="https://fonts.googleapis.com/css2?family=...&display=swap",
    # font_display='"Your Display Face", system-ui, sans-serif',
    # font_sans='"Your Body Face", system-ui, sans-serif',
)

# ---------------------------------------------------------------------------
# Copy. Every word on the page. {fields} are filled by the build.
# ---------------------------------------------------------------------------
COPY = Copy(
    page_title="",         # TODO: browser tab. Defaults to your display_name.

    # --- hero. Fields: {episodes} {entities} {hours} {places} ---
    hero_kicker="{episodes} episodes · {hours} hours",
    # RAW HTML — the one place markup is expected, so a wordmark can accent a glyph:
    #   hero_title_html='Table<span class="ac">4</span>'
    # It's your code, never the model's. Defaults to your display_name, escaped.
    hero_title_html="",                              # TODO
    hero_lead_html="",                               # TODO: one or two sentences
    hero_scroll_hint="Scroll",
    counter_labels={
        "episodes": "episodes", "entities": "entities", "places": "places",
        "people": "people", "books": "books",
    },

    # --- sections ---
    # Numbering lives in the eyebrow, so if you turn one off, renumber the rest.
    # enabled=False drops a section outright; a section without the data to fill it
    # hides itself regardless (--dry-run tells you which).
    globe=SectionCopy(eyebrow="01 · The globe", heading="", sub=""),        # TODO
    library=SectionCopy(eyebrow="02 · The library", heading="", sub=""),
    records=SectionCopy(eyebrow="03 · The records", heading="", sub=""),
    funfacts=SectionCopy(eyebrow="04 · The odds and ends", heading="", sub=""),
    hostface=SectionCopy(eyebrow="05 · Head to head", heading="", sub=""),
    leaders=SectionCopy(eyebrow="06 · The league table", heading="", sub=""),
    cloud=SectionCopy(eyebrow="07 · The ideas", heading="", sub=""),
    pulse=SectionCopy(eyebrow="08 · The pulse", heading="", sub=""),
    wordlab=SectionCopy(eyebrow="09 · The language", heading="", sub=""),
    graph=SectionCopy(eyebrow="10 · The map", heading="", sub=""),
    # Editorial, never computed. Turn this on only if your show HAS a running bit —
    # a recurring guest, a listener who built something, an in-joke award. Don't
    # invent one, and fill shoutout_entries below if you do.
    shoutouts=SectionCopy(enabled=False),

    # --- words that repeat everywhere ---
    episodes_word="episodes",          # "shared 5 episodes"
    episode_label_tpl="Ep. {n}",       # how an episode is named on the whole page
    episode_unnumbered="Special",      # for a feed entry with no number
    # Defaults come from your notion_type_labels, emoji stripped. Override to taste.
    # type_labels={"person": "people", ...},

    # --- the fun facts ---
    # {fact_id: {"title": ..., "cap": <template>}}. The full id list and the fields
    # each one provides are in OBSERVATORY.md. Drop a fact by leaving its id out of
    # funfact_order; the build reports any that had data but no copy.
    funfact_copy={
        # "regular_star": {"title": "The regular", "cap": "{name} turned up in {pct}% of episodes."},
    },
    funfact_order=(),                  # () = the built-in order

    # --- the host face-off (a two-sided chart: it names exactly two hosts) ---
    hostface_total_tpl="{n} mentions",
    # Your raw entity types are usually too fine-grained to compare hosts on; group
    # them into a handful of axes that mean something for your show.
    # hostface_groups=(
    #     {"label": "People", "types": ("person",)},
    #     {"label": "Markets", "types": ("stock", "company")},
    #     {"label": "Ideas", "types": ("concept", "book", "article")},
    # ),

    # --- the pulse: same idea, as stacked streams over time ---
    # timeline_streams=(
    #     {"key": "geo", "label": "The world", "types": ("place", "other")},
    #     {"key": "mkt", "label": "Markets", "types": ("stock", "company")},
    #     {"key": "idea", "label": "Ideas", "types": ("concept", "book", "article")},
    # ),

    # --- the language section (needs transcripts/; skipped if you don't keep them) ---
    # Counted as SUBSTRINGS — which is what you want in a language with clitic
    # prefixes, and over-counts in English ("art" matches "start"). Pick words your
    # show actually says.
    signature_words=(),                # (("like", "«like»"), ...)
    laugh_pattern="",                  # r"haha+" — "" turns the stat off

    # --- shout-outs (only if the section above is on) ---
    shoutout_entries=(),               # ({"name": ..., "ep": 12, "crown": True, "blurb": ...},)

    footer_logo_html="",               # TODO: raw HTML, like hero_title_html
    footer_prov_tpl="{entities} entities from {episodes} episodes · {from} — {to}",
    footer_links=(),                   # (("Label", "https://..."),) — defaults to your db_link
)

OBSERVATORY = Observatory(
    theme=THEME,
    copy=COPY,
    # Places the bundled lookup doesn't know. `--dry-run` prints them ready to paste.
    extra_place_coords={},             # {"my town": [lat, lon]}
    # The face-off shows the two hosts with the most attributed mentions. Name two
    # to override. hostface_hosts=("Alex", "Sam"),
)
