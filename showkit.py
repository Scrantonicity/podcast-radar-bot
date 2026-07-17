"""showkit.py — the per-show configuration contract (schemas only, no I/O).

Every podcast this repo serves is described by two objects: a `ShowConfig`
(identity, feed, language, hosts, digest layout) and a `Strings` bundle (every
piece of user-facing text). A show lives in `shows/<name>/` as three files:

    shows/<name>/config.py   ->  SHOW  = ShowConfig(...)
    shows/<name>/strings.py  ->  STRINGS = Strings(...)
    shows/<name>/prompt.txt  ->  the extraction system prompt (+ optional regen.txt)

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
