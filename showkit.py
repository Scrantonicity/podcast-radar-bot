"""showkit.py — the per-show configuration contract (schemas only, no I/O).

Every podcast this repo serves is described by two objects: a `ShowConfig`
(identity, feed, language, hosts, digest layout) and a `Strings` bundle (every
piece of user-facing text). A show lives in `shows/<name>/` as three files:

    shows/<name>/config.py   ->  SHOW  = ShowConfig(...)
    shows/<name>/strings.py  ->  STRINGS = Strings(...)
    shows/<name>/prompt.txt  ->  the extraction system prompt (+ optional regen.txt)

plus one optional fourth, for the HTML statistics page (see OBSERVATORY.md):

    shows/<name>/observatory.py  ->  OBSERVATORY = Observatory(...)

`show_loader.py` picks the active show from the SHOW env var and exposes SHOW,
STRINGS, PROMPT, REGEN_PROMPT to the engine. The engine holds NO podcast- or
language-specific literals — everything it needs comes from here. Adding a podcast
never touches engine code: copy `shows/_template/`, fill these fields, set SHOW=.

This module imports nothing project-specific on purpose, so both the shows and the
loader can import it without a cycle.
"""

from dataclasses import dataclass, field
from typing import Optional


# The entity taxonomy is the frozen extraction CONTRACT (shared by the schema,
# Notion, and the digest), not a per-language choice — so it lives here as the
# default. A show may override `entity_types` but almost never should.
DEFAULT_ENTITY_TYPES = [
    "person", "company", "stock", "place", "concept", "book", "article", "other",
]


@dataclass(frozen=True)
class ShowConfig:
    """Identity, feed source, language, and digest layout for one podcast."""

    # --- identity ---
    display_name: str                    # shown in the digest header, alerts, etc.

    # --- feed source (supply exactly one) ---
    feed_apple_id: Optional[str] = None  # iTunes/Apple podcast id -> resolves RSS
    feed_rss_url: Optional[str] = None   # or a direct RSS url (skips the lookup)

    # --- language / speech-to-text ---
    stt_language: str = "en"             # Speechmatics BCP-47 code (he, en, es, ...)
    stt_additional_vocab: tuple = ()     # brand/proper-name hints the STT keeps mishearing
    text_direction: str = "ltr"          # "rtl" | "ltr" — gates bidi isolation in the digest
    date_format: str = "%b %d, %Y"       # strftime for the header date (rtl shows use "%d.%m.%y")

    # --- hosts (SINGLE SOURCE OF TRUTH) ---
    # Short forms of the show's regular hosts. These feed the extraction schema's
    # `mentioned_by` enum, the digest attribution, and the Notion "Recommended by"
    # tags. The prompt prose names them too — keep the two in sync (host_ban_keys
    # is the safety net if the model still leaks one).
    hosts: tuple = ()
    guest_label: str = "Guest"           # label for any non-regular voice
    # Every spelling/script under which a host might leak in as an entity — dropped
    # post-extraction. Include transliterations, full names, and old spellings.
    host_ban_keys: frozenset = frozenset()
    # Sponsors / ad-read brands to drop like listeners (never editorial entities).
    sponsor_ban_keys: frozenset = frozenset()

    # --- public database link (appended to every digest) ---
    db_link: str = ""

    # --- entity de-duplication: romanizing the show's script ---
    # The dedup candidate-finder compares a script-agnostic form of each name, so a
    # native-script name and its Latin twin ("אנבידיה" / "Nvidia") land close enough
    # for the fuzzy scorer to pair them. Supply a best-effort character map for your
    # language — it is for RECALL, not a faithful transliteration.
    # Leave all three empty (the default) for a Latin-script show: names are then just
    # base-normalized, which is already correct.
    native_script_re: str = ""            # regex detecting the script, e.g. r"[֐-׿]"
    translit_digraphs: dict = field(default_factory=dict)  # 2-char forms, applied FIRST
    translit_singles: dict = field(default_factory=dict)   # single chars -> latin

    # --- extraction contract ---
    entity_types: tuple = tuple(DEFAULT_ENTITY_TYPES)
    # Optional per-type -> Notion "Action" override, overlaid on the engine default
    # (book/article->To Read, concept/company->To Research, stock->To Watch,
    # person->To Look Up, place/other->none). Only needed when a show adds a type
    # beyond the defaults and wants it to land in a follow-up Action bucket; a custom
    # type left unmapped simply gets an empty Action. Value None means "no action".
    action_by_type: dict = field(default_factory=dict)
    diarization_min_speakers: int = 2    # below this -> attribution is blanked (honest-empty)
    diarization_max_char_share: float = 0.85  # one speaker owns more than this -> blanked

    # --- Telegram digest layout ---
    # Merged sections in display order; each has one heading (with its icon) and the
    # entity types it collects. Types omitted from every section stay out of the
    # digest (still written to Notion). Headings are language text -> edit per show.
    tg_sections: tuple = ()              # ({"heading": str, "types": (str, ...)}, ...)
    tg_type_caps: dict = field(default_factory=dict)  # {type: max_bullets}
    tg_global_cap: int = 13
    tg_trim_order: tuple = ()            # least->most important; trimmed first when over cap
    reading_types: frozenset = frozenset({"book", "article"})   # linked, no attribution
    sentiment_types: frozenset = frozenset({"stock", "company"})  # show ticker + 📈/📉
    # Article prefixes stripped when a context repeats the entity name (e.g. Hebrew
    # "ה"). Empty for languages without clitic articles.
    name_article_prefixes: tuple = ()

    # --- Notion page body labels (structural, language text) ---
    # Emoji + label per entity type for the grouped episode-page body.
    notion_type_labels: dict = field(default_factory=dict)   # {type: "👤 People"}
    # Singular article-less noun per type, grounds the "Learn" deep-link query.
    notion_learn_type_nouns: dict = field(default_factory=dict)  # {type: "person"}

    @property
    def mentioned_by_enum(self):
        """Values allowed in an entity's `mentioned_by` (hosts + the guest label)."""
        return list(self.hosts) + [self.guest_label]

    def resolved_host_ban_keys(self):
        """host_ban_keys plus a normalized form of each host short name, so a plain
        rename of `hosts` can't silently stop filtering that host."""
        import re
        def norm(k):
            k = (k or "").strip().lower()
            k = re.sub(r"[^\w\s-]", "", k, flags=re.UNICODE)
            return re.sub(r"\s+", " ", k).strip()
        return frozenset(self.host_ban_keys) | {norm(h) for h in self.hosts}


@dataclass(frozen=True)
class Strings:
    """Every user-facing string. One file per language; the engine reads only these."""

    # --- Telegram digest ---
    tg_header_prefix: str = "🎙️"              # "{prefix} | פרק N: headline (date)"
    tg_episode_word: str = "Ep."               # "{word} {N}"
    tg_deepdive_label: str = "🔥 Deep Dive:"
    tg_listen_label: str = "🔗 Listen: "
    tg_returning_word: str = "ep."             # "🔁 {word} N"
    tg_empty_state: str = "No standout entities in this episode — all saved to the database."
    tg_db_more: str = "🗂️ +{k} more in the database → {link}"
    tg_db_all: str = "🗂️ All entities in the database → {link}"

    # --- approval flow (buttons + toasts + disabled-state labels) ---
    approve_btn: str = "✅ Approve & post"
    reject_btn: str = "❌ Reject"
    toast_unauthorized: str = "Not authorized"
    toast_already_sent: str = "Already sent"
    toast_no_channel: str = "Channel not configured"
    toast_sent: str = "Sent to channel ✅"
    toast_rejected: str = "Rejected"
    disabled_sent: str = "✅ Sent to channel"
    disabled_rejected: str = "❌ Rejected"

    # --- Notion episode-page body ---
    notion_summary_heading: str = "📝 Summary"
    notion_topics_heading: str = "🧭 Topics"
    notion_entities_heading: str = "🔑 Entities"
    notion_transcript_title: str = "Transcript"
    notion_episode_context_word: str = "Ep."   # entity-body bullet: "{word} {N} — <context>"

    # --- "Learn" Perplexity deep-link (built from these three parts) ---
    learn_prompt_template: str = (
        "Teach me about {subject} step by step: brief background, why it matters, "
        "3 key points, one simple analogy, and a short comprehension question at the end."
    )
    learn_prompt_context_template: str = ' On the podcast "{show}" it was said: "{ctx}" — address that too.'
    learn_prompt_suffix: str = " Keep it simple and accessible."

    # --- email (Resend scaffold, disabled by default) ---
    email_subject_template: str = "{show} — {episode_word} {num}"
    email_body_template: str = "<p>{n} entities extracted.</p>"
    email_open_notion: str = "Open in Notion"

    # --- entity resolution pass (resolve_entities.py; needs shows/<name>/resolve.txt) ---
    resolve_items_prefix: str = "Entities to resolve:"
    resolve_preview_header: str = "<b>🔎 Resolution fixes (review):</b>"
    resolve_note_dropped: str = "⚠️ dropped (not an entity): {name}"
    resolve_note_merged: str = "🔗 merged: {orig} → {target} [{confidence}]"
    resolve_note_renamed: str = "✏️ name corrected: {orig} → {new} [{confidence}]"
    resolve_note_low_conf: str = "❓ low confidence: {name} (key={key})"

    # --- extraction user-turn scaffolding + meta-context repair ---
    extract_transcript_prefix: str = "Episode transcript:"
    extract_shownotes_note: str = (
        "\n\nShownotes (use only to fill `link` when a url maps clearly to an entity, "
        "and to help spell names — never invent):\n"
    )
    regen_items_prefix: str = "Items to fix:"
    # Regex fragments flagging "meta" contexts (who said/wrote it) to auto-repair.
    # Empty tuple disables the whole meta-context repair feature for this language.
    meta_context_patterns: tuple = ()

    # --- failure alerts (private chat) ---
    alert_episode_failed_template: str = "🚨 <b>{show} — episode {num} failed</b>\n"
    alert_auto_review_failed_template: str = "🚨 <b>{show} — auto_review failed</b>\n"

    # --- watchdog dead-man alerts (see RELIABILITY.md) ---
    watchdog_empty_feed_template: str = (
        "⚠️ {show} watchdog: the feed returned no episodes — check the RSS/pipeline."
    )
    watchdog_not_processed_template: str = (
        "⚠️ {show} — episode {num} still isn't processed.\n"
        "The weekly trigger (external scheduler → pipeline) probably didn't run.\n"
        "Run it manually: gh workflow run pipeline.yml -f mode=auto -f episode=1"
    )


# ===========================================================================
# The observatory: an optional, self-contained HTML statistics page built from
# the episode archive. See OBSERVATORY.md.
#
# The contract that makes this work: `build_observatory.py` computes every NUMBER
# from extractions/, and these dataclasses carry only LOOK and WORDS. A caption
# never states a figure — it interpolates one ("{pct}% of episodes"), so the page
# can't go stale. Nothing below is required: a show with no observatory.py builds
# a neutral-themed page via observatory/defaults.py.
# ===========================================================================


@dataclass(frozen=True)
class Theme:
    """Colors and fonts. Rendered into the page's `:root` as CSS custom properties,
    which every chart reads at runtime — so recoloring the whole page is this object.

    Defaults are a neutral dark scheme. Override the ones that carry your show's
    mood; leave the rest. Every value is raw CSS, so `bg="#000"` and
    `bg="oklch(.2 .02 260)"` are equally fine.
    """

    # --- surfaces (back to front) ---
    bg: str = "#0b0d14"
    bg2: str = "#11141f"
    panel: str = "#171b29"
    panel2: str = "#1e2333"

    # --- brand ---
    accent: str = "#5b6cff"
    accent_dim: str = "#3d49b8"
    accent2: str = "#2f3aa8"
    accent2_glow: str = "#6b7aff"
    highlight: str = "#e0a44a"
    highlight2: str = "#f5c46e"
    highlight_soft: str = "#f0dcb4"

    # --- text + rules ---
    ink: str = "#e8eaf5"
    muted: str = "#99a0c4"
    muted2: str = "#676d91"
    line: str = "rgba(140,150,220,.16)"

    # --- categorical, one color per entity type -> emits --c-<type> ---
    # Keys not in the active show's entity_types are ignored; types missing here
    # fall back to type_color_fallback. Chosen to stay legible on a dark surface.
    type_colors: dict = field(default_factory=lambda: {
        "person": "#e0a44a", "place": "#38d9c4", "stock": "#79e07a",
        "company": "#79c0ff", "concept": "#c79bff", "book": "#ff9d5c",
        "article": "#ff7b8a", "other": "#8b93c9",
    })
    type_color_fallback: str = "#8b93c9"

    # --- the library shelf (books/articles section) ---
    shelf_wood: str = "#2b1a10"
    shelf_wood2: str = "#170d07"
    shelf_gold: str = "#e0ad4e"
    shelf_gold_soft: str = "#f0d59a"
    shelf_parch: str = "#efe0c0"
    # Spine gradients, cycled across the shelf. Each pair is (top, bottom).
    book_palette: tuple = (
        ("#3a2418", "#1d1009"), ("#2a3348", "#141a26"), ("#3d2030", "#1e0f18"),
        ("#233a33", "#111d19"), ("#3a3520", "#1d1a0f"), ("#2e2440", "#171220"),
        ("#402a1c", "#20150e"), ("#1f3340", "#0f1a20"),
    )

    # --- the globe ---
    globe_ocean: str = "#0c1030"
    globe_land: str = "#241f57"
    globe_border: str = "rgba(150,140,235,.35)"
    globe_graticule: str = "rgba(120,120,200,.10)"
    globe_rim: str = "rgba(150,140,235,.45)"
    # Arcs and dots animate their alpha, so these are "r,g,b" triples, not hex.
    globe_arc_rgb: str = "224,164,74"
    globe_dot_rgb: str = "240,169,62"

    # --- the concept cloud ---
    # Color ramp across mention count (low -> high). Any length >= 2.
    cloud_ramp: tuple = ("#3d49b8", "#5b6cff", "#c79bff", "#e0a44a", "#f5c46e")
    cloud_label_ink: str = "#140b1e"   # text drawn ON a bubble; keep it dark

    # --- the hero starfield ---
    star_color: str = "#ffffff"
    star_color2: str = "#c9d0ff"

    # --- type ---
    # Default to system stacks: no network call, no GDPR question, works offline.
    # Set font_link to a Google Fonts <link> href to opt in, then name them below.
    font_link: str = ""
    font_sans: str = "system-ui, -apple-system, Segoe UI, sans-serif"
    font_serif: str = "Georgia, 'Times New Roman', serif"
    font_display: str = "system-ui, -apple-system, Segoe UI, sans-serif"
    font_libserif: str = "Georgia, 'Times New Roman', serif"
    font_mono: str = "ui-monospace, SFMono-Regular, Menlo, monospace"


@dataclass(frozen=True)
class SectionCopy:
    """One section's header. `enabled=False` drops the section even if data exists;
    a section whose data is missing or too thin hides itself regardless (run
    `build_observatory.py --dry-run` to see which will render).

    The eyebrow carries its own number ("01 · The Globe") so that turning a section
    off lets you renumber the rest by hand rather than leaving a gap.
    """

    enabled: bool = True
    eyebrow: str = ""
    heading: str = ""
    sub: str = ""


@dataclass(frozen=True)
class Copy:
    """Every word on the page. One file per show; the template holds no literals.

    THE RULE: never write a computed number into prose. Templates receive their
    figures as `{fields}` — see OBSERVATORY.md for the field list per string.
      wrong:  hero_kicker="65 episodes · 88.9 hours"
      right:  hero_kicker="{episodes} episodes · {hours} hours"
    """

    # --- document ---
    page_title: str = ""          # "" -> the show's display_name
    lang: str = ""                # "" -> SHOW.stt_language
    text_direction: str = ""      # "" -> SHOW.text_direction

    # --- hero ---
    hero_kicker: str = "{episodes} episodes · {hours} hours"   # {episodes} {hours} {entities}
    # TRUSTED RAW HTML (authored here, never from the model) — the wordmark often
    # needs markup to accent one glyph: 'Table<span class="four">4</span>'.
    hero_title_html: str = ""     # "" -> the show's display_name, escaped
    hero_lead_html: str = ""
    hero_scroll_hint: str = ""
    # {"episodes","entities","places","people","books"} -> label under each counter
    counter_labels: dict = field(default_factory=dict)

    # --- nav dots: {section_id: short label} ---
    nav_labels: dict = field(default_factory=dict)

    # --- sections ---
    globe: SectionCopy = field(default_factory=SectionCopy)
    library: SectionCopy = field(default_factory=SectionCopy)
    records: SectionCopy = field(default_factory=SectionCopy)
    funfacts: SectionCopy = field(default_factory=SectionCopy)
    hostface: SectionCopy = field(default_factory=SectionCopy)
    leaders: SectionCopy = field(default_factory=SectionCopy)
    cloud: SectionCopy = field(default_factory=SectionCopy)
    pulse: SectionCopy = field(default_factory=SectionCopy)
    wordlab: SectionCopy = field(default_factory=SectionCopy)
    graph: SectionCopy = field(default_factory=SectionCopy)
    # Editorial, never computed: in-jokes, regulars, listener shout-outs. Off unless
    # `shoutouts` below is filled. Never invent these.
    shoutouts: SectionCopy = field(default_factory=lambda: SectionCopy(enabled=False))

    # --- shared units (used by ~15 tooltips and chips) ---
    episodes_word: str = "episodes"                   # plural: "shared 5 episodes"
    episode_label_tpl: str = "Ep. {n}"                # how an episode is named everywhere
    episode_unnumbered: str = "Special"               # feed gave no number and no headline
    type_labels: dict = field(default_factory=dict)   # {entity_type: "person"}

    # --- globe ---
    globe_legend: str = ""
    globe_dossier_hint: str = ""   # shown in the dossier panel until a dot is clicked

    # --- library ---
    book_kind_labels: dict = field(default_factory=dict)   # {"book": "Book", ...}
    book_recommended_by: str = "{host} recommended"
    book_appeared_in: str = "appeared in {n}"
    book_gem_chip: str = "💎 rare gem"

    # --- records: {card_id: {"title": str, "cap": <template>}} ---
    records_cards: dict = field(default_factory=dict)

    # --- fun facts ---
    # {fact_id: {"title": str, "cap": <template>}}. The build computes each fact's
    # numbers and hands them to cap.format(); see OBSERVATORY.md for the fields.
    funfact_copy: dict = field(default_factory=dict)
    funfact_order: tuple = ()     # display order; an id left out is dropped

    # --- host face-off (a two-sided chart; picks two hosts) ---
    hostface_total_tpl: str = "{n} mentions"   # under each host's name
    # ({"label": str, "types": (type, ...)}, ...) -> the axes the two hosts are
    # compared on. The raw entity types are usually too fine-grained to be readable.
    hostface_groups: tuple = ()

    # --- leaderboards ---
    leader_col_headings: dict = field(default_factory=dict)   # {entity_type: heading}
    notab_note: str = ""
    notab_scale_labels: tuple = ()   # low -> high, one per notability point

    # --- pulse ---
    # ({"key": str, "label": str, "types": (type, ...)}, ...) -> the stacked streams
    timeline_streams: tuple = ()
    timeline_tooltip_total: str = "total"
    spark_strip_heading: str = ""

    # --- wordlab ---
    wl_stat_labels: dict = field(default_factory=dict)
    wl_words_heading: str = ""
    wl_ticker_heading: str = ""
    wl_ticker_note: str = ""
    # ((needle, display_label), ...) — counted as substrings, so they catch clitic
    # prefixes in Hebrew/Arabic; in English that over-counts ("art" hits "start").
    signature_words: tuple = ()
    laugh_pattern: str = ""       # regex, e.g. r"חחח+" or r"haha+"; "" disables the stat

    # --- graph ---
    graph_legend_title: str = ""
    graph_hint: str = ""

    # --- shout-outs: ({"name", "ep", "crown", "blurb"}, ...) ---
    shoutout_entries: tuple = ()
    shoutout_crowned_tpl: str = "crowned in {episode_word} {ep}"

    # --- footer ---
    footer_logo_html: str = ""    # TRUSTED RAW HTML, like hero_title_html
    footer_prov_tpl: str = "{episodes} episodes · built {built}"
    footer_links: tuple = ()      # ((label, url), ...)


@dataclass(frozen=True)
class Observatory:
    """The observatory's per-show settings: `OBSERVATORY = Observatory(...)` in
    shows/<name>/observatory.py. Every field is optional."""

    theme: Theme = field(default_factory=Theme)
    copy: Copy = field(default_factory=Copy)

    # --- geo ---
    # The build ships coordinates for ~350 common places, keyed by the English
    # canonical_key the extractor emits. Anything it can't place is listed in the
    # --dry-run report and simply doesn't plot; add it here as {key: [lat, lon]}.
    extra_place_coords: dict = field(default_factory=dict)
    place_key_aliases: dict = field(default_factory=dict)   # {key: canonical_key}

    # --- co-mention network tuning ---
    # Defaults scale with the archive size (see observatory/defaults.py) — a 6-episode
    # show needs looser thresholds than a 60-episode one or the graph comes out empty.
    # Set any of these to override that.
    graph_min_mentions: Optional[int] = None
    graph_min_edge_weight: Optional[int] = None
    graph_max_nodes: int = 150
    graph_max_degree: int = 7

    # The face-off compares exactly two hosts. Default: the two with the most
    # attributed mentions. Name them here to pick a different pair.
    hostface_hosts: tuple = ()
