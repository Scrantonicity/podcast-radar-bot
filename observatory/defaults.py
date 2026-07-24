"""defaults.py — turn a partial (or absent) shows/<name>/observatory.py into a
complete one.

`resolve()` is TOTAL: after it, every Theme and Copy field has a value, so stats.py
and assemble.py never test for None or empty. A show that never writes an
observatory.py still gets a coherent page — neutral dark theme, plain English copy,
and its own entity types and hosts throughout.

Everything derivable from ShowConfig is derived rather than defaulted: the type
labels come from the show's Notion labels, the timeline streams and face-off axes
from its entity_types, the footer link from its db_link. The show already said all
this once; it shouldn't have to say it again.
"""

import dataclasses
import re

from showkit import Copy, Observatory, SectionCopy, Theme

# The fun facts the build knows how to compute, in a sensible default order.
# stats.py owns the arithmetic; these ids are the join between the two.
# `world_vs_market` is deliberately absent — it contrasts two entity types and only
# means something for a show whose editorial line is geopolitics-vs-markets. Its
# builder exists; add the id to funfact_order to opt in.
DEFAULT_FUNFACT_ORDER = (
    "regular_star", "hours_in_ears", "busiest_episode", "one_hit_wonders",
    "inseparable_pair", "marathon", "returning_faces", "rarest_gem",
    "globetrotter_host", "reading_shelf", "average_episode", "lightest_episode",
    "longest_name", "all_the_types", "social_butterfly", "word_avalanche",
)

# {fact_id: (title, caption template)}. Caption fields are supplied by stats.py —
# see OBSERVATORY.md for the per-fact field list. No literal figures here, ever.
DEFAULT_FUNFACT_COPY = {
    "regular_star": ("The regular", "{name} turned up in {pct}% of episodes."),
    "hours_in_ears": ("Hours in your ears", "{hours} hours of talk, all told."),
    "busiest_episode": ("The busiest episode", "{label} packed in {n} entities — more than any other."),
    "one_hit_wonders": ("One-hit wonders", "{n} things came up exactly once and were never spoken of again."),
    "inseparable_pair": ("Never apart", "{a} and {b} showed up together {n} times."),
    "marathon": ("The marathon", "{label} ran {dur} — the longest of the run."),
    "returning_faces": ("Familiar faces", "{n} of them came back for more than one episode."),
    "rarest_gem": ("Rare gems", "{n} entities scored the top notability mark."),
    "globetrotter_host": ("The globetrotter", "{host} name-drops more places than anyone else: {n}."),
    "reading_shelf": ("The reading pile", "{n} books and articles worth your time."),
    "average_episode": ("The average episode", "{mins} minutes, give or take."),
    "lightest_episode": ("The quick one", "{label} was over in {dur}."),
    "longest_name": ("A mouthful", "{name} — {len} characters of it."),
    "all_the_types": ("The full spread", "{n} different kinds of thing got a mention."),
    "social_butterfly": ("The connector", "{name} shares an episode with {n} others."),
    "word_avalanche": ("Words, words, words", "{n} words spoken, about {per_ep} per episode."),
}

# {card_id: (title, caption template)} for the records bento. The per-type "top"
# cards are generated from the show's entity_types in _default_records_cards().
DEFAULT_RECORDS_CARDS = {
    "gems": ("Rare gems", "{n} entities at top notability"),
    "busiest": ("Busiest episode", "{label} — {n} entities"),
    "longest_name": ("Longest name", "{len} characters"),
    "most_places": ("Most travelled episode", "{label} — {n} places"),
    "host_counts": ("Who talks about what", "mentions attributed per host"),
    "type_totals": ("The spread", "entities by kind"),
}

_EMOJI_PREFIX = re.compile(r"^[^\w]+\s*", flags=re.UNICODE)


def _strip_icon(label):
    """'👤 People' -> 'People'. The Notion labels carry an emoji; the page draws its
    own, so reuse the words and drop the picture. Hebrew/Cyrillic letters are \\w,
    so this only eats leading symbols."""
    return _EMOJI_PREFIX.sub("", label or "").strip()


def _title(s):
    return s[:1].upper() + s[1:] if s else s


def _default_type_labels(show):
    """Prefer the show's own Notion labels; fall back to the bare type name."""
    out = {}
    for t in show.entity_types:
        label = _strip_icon(show.notion_type_labels.get(t, ""))
        out[t] = label or _title(t)
    return out


def _default_records_cards(show, type_labels):
    cards = {}
    for t in show.entity_types:
        cards[f"top_{t}"] = {
            "title": f"Most-mentioned {type_labels.get(t, t).lower()}",
            "cap": "{name} — {n} " + "mentions",
        }
    for cid, (title, cap) in DEFAULT_RECORDS_CARDS.items():
        cards[cid] = {"title": title, "cap": cap}
    return cards


def _scaled_graph_thresholds(n_eps):
    """These thresholds assume a ~65-episode archive; below ~15 episodes they cut
    every edge and the network renders empty. Loosen as the archive shrinks."""
    if n_eps < 15:
        return 1, 1
    if n_eps < 40:
        return 2, 2
    return 2, 3


def _sections_defaults(show, type_labels):
    """Neutral English headers. Numbered in the default order; the AI renumbers after
    the user picks sections (see OBSERVATORY.md)."""
    return {
        "globe": SectionCopy(
            eyebrow="01 · The globe",
            heading="Where the conversation travels",
            sub="Every place named on the show, and which ones come up together. Drag to spin, click a dot.",
        ),
        "library": SectionCopy(
            eyebrow="02 · The library",
            heading="What got recommended",
            sub="Every book and article mentioned. Hover a spine.",
        ),
        "records": SectionCopy(
            eyebrow="03 · The records",
            heading="Bests, mosts and firsts",
            sub="The extremes of the archive, in one place.",
        ),
        "funfacts": SectionCopy(
            eyebrow="04 · The odds and ends",
            heading="Things nobody thought to count",
            sub="Dug out of the transcripts.",
        ),
        "hostface": SectionCopy(
            eyebrow="05 · Head to head",
            heading="Who brings up what",
            sub="Mentions attributed to each host, by kind.",
        ),
        "leaders": SectionCopy(
            eyebrow="06 · The league table",
            heading="The most-mentioned",
            sub="Ranked by how often each came up.",
        ),
        "cloud": SectionCopy(
            eyebrow="07 · The ideas",
            heading="What the show is actually about",
            sub="Every idea discussed, sized by how often. Hover a bubble.",
        ),
        "pulse": SectionCopy(
            eyebrow="08 · The pulse",
            heading="The rhythm of the show",
            sub="What each episode was made of, over time.",
        ),
        "wordlab": SectionCopy(
            eyebrow="09 · The language",
            heading="How the show talks",
            sub="Counted from the transcripts.",
        ),
        "graph": SectionCopy(
            eyebrow="10 · The map",
            heading="Who comes up with whom",
            sub="Two things linked if they share an episode. Drag, zoom, click to isolate.",
        ),
        "shoutouts": SectionCopy(
            enabled=False,
            eyebrow="11 · The regulars",
            heading="Friends of the show",
            sub="",
        ),
    }


def _merge_section(authored, fallback):
    """Field-level fallback: an authored section that sets only `heading` still gets
    the default eyebrow and sub. `enabled` is authoritative as authored."""
    return SectionCopy(
        enabled=authored.enabled,
        eyebrow=authored.eyebrow or fallback.eyebrow,
        heading=authored.heading or fallback.heading,
        sub=authored.sub or fallback.sub,
    )


def resolve(show, obs=None, n_episodes=0):
    """Fill every unset field of `obs` from `show` and the built-in defaults.

    Returns a new Observatory. Total: no field is empty afterwards, except the ones
    whose emptiness is meaningful (`signature_words`, `laugh_pattern`,
    `shoutout_entries` — each disables its own feature).
    """
    obs = obs or Observatory()
    theme, copy = obs.theme, obs.copy

    type_labels = copy.type_labels or _default_type_labels(show)

    # --- theme: one color per active entity type, authored ones winning ---
    type_colors = {}
    for t in show.entity_types:
        type_colors[t] = theme.type_colors.get(t) or theme.type_color_fallback
    theme = dataclasses.replace(theme, type_colors=type_colors)

    # --- copy ---
    sec = _sections_defaults(show, type_labels)

    streams = copy.timeline_streams or tuple(
        {"key": t, "label": type_labels.get(t, t), "types": (t,)}
        for t in show.entity_types
    )
    groups = copy.hostface_groups or tuple(
        {"label": type_labels.get(t, t), "types": (t,)} for t in show.entity_types
    )
    leader_cols = copy.leader_col_headings or {
        t: type_labels.get(t, t) for t in show.entity_types
    }

    footer_links = copy.footer_links
    if not footer_links and show.db_link:
        footer_links = (("The database", show.db_link),)

    copy = dataclasses.replace(
        copy,
        page_title=copy.page_title or show.display_name,
        lang=copy.lang or show.stt_language,
        text_direction=copy.text_direction or show.text_direction,
        hero_title_html=copy.hero_title_html or _escape(show.display_name),
        hero_lead_html=copy.hero_lead_html or _escape(
            f"Everything {show.display_name} has talked about, counted."
        ),
        hero_scroll_hint=copy.hero_scroll_hint or "Scroll",
        counter_labels=copy.counter_labels or {
            "episodes": "episodes", "entities": "entities", "places": "places",
            "people": "people", "books": "books",
        },
        nav_labels=copy.nav_labels or {
            k: v.heading for k, v in sec.items()
        },
        globe=_merge_section(copy.globe, sec["globe"]),
        library=_merge_section(copy.library, sec["library"]),
        records=_merge_section(copy.records, sec["records"]),
        funfacts=_merge_section(copy.funfacts, sec["funfacts"]),
        hostface=_merge_section(copy.hostface, sec["hostface"]),
        leaders=_merge_section(copy.leaders, sec["leaders"]),
        cloud=_merge_section(copy.cloud, sec["cloud"]),
        pulse=_merge_section(copy.pulse, sec["pulse"]),
        wordlab=_merge_section(copy.wordlab, sec["wordlab"]),
        graph=_merge_section(copy.graph, sec["graph"]),
        shoutouts=_merge_section(copy.shoutouts, sec["shoutouts"]),
        type_labels=type_labels,
        globe_legend=copy.globe_legend or "Dot size = how often it came up",
        globe_dossier_hint=copy.globe_dossier_hint or "Pick a place to see its file.",
        book_kind_labels=copy.book_kind_labels or {
            t: type_labels.get(t, t) for t in ("book", "article") if t in show.entity_types
        },
        records_cards=copy.records_cards or _default_records_cards(show, type_labels),
        funfact_copy=copy.funfact_copy or {
            k: {"title": t, "cap": c} for k, (t, c) in DEFAULT_FUNFACT_COPY.items()
        },
        funfact_order=copy.funfact_order or DEFAULT_FUNFACT_ORDER,
        hostface_groups=groups,
        leader_col_headings=leader_cols,
        notab_note=copy.notab_note or "How much airtime each one actually got.",
        notab_scale_labels=copy.notab_scale_labels or (
            "a passing mention", "in passing", "discussed", "dug into", "the main event",
        ),
        timeline_streams=streams,
        spark_strip_heading=copy.spark_strip_heading or "Who shows up when",
        wl_stat_labels=copy.wl_stat_labels or {
            "hours": "hours of talk", "total": "words spoken",
            "per_ep": "words per episode", "avg_min": "minutes per episode",
            "latin_words": "words in Latin script", "laughs": "bursts of laughter",
        },
        wl_words_heading=copy.wl_words_heading or "Signature words",
        wl_ticker_heading=copy.wl_ticker_heading or "The ticker wall",
        wl_ticker_note=copy.wl_ticker_note or "Every ticker symbol the show has said out loud.",
        graph_legend_title=copy.graph_legend_title or "Kinds",
        graph_hint=copy.graph_hint or "Click a node to isolate it. Scroll to zoom.",
        footer_links=footer_links,
        footer_logo_html=copy.footer_logo_html or _escape(show.display_name),
    )

    # --- graph thresholds: scale to the archive unless pinned ---
    min_m, min_w = _scaled_graph_thresholds(n_episodes)
    return dataclasses.replace(
        obs,
        theme=theme,
        copy=copy,
        graph_min_mentions=obs.graph_min_mentions if obs.graph_min_mentions is not None else min_m,
        graph_min_edge_weight=obs.graph_min_edge_weight if obs.graph_min_edge_weight is not None else min_w,
    )


def _escape(s):
    """hero_title_html/footer_logo_html are raw-HTML slots. When WE fill them from
    display_name rather than the author, escape — a show name with an & or < must not
    become markup."""
    return (str(s or "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
