"""assemble.py — put the page together.

The template is a real, valid HTML file with `__PLACEHOLDER__` markers. This module
replaces them with the vendored libraries, the world atlas, and three JSON blobs
(stats, theme, copy), and hands back one self-contained string. No CDN, no build
toolchain, no runtime fetch: the output opens from a file:// URL on a plane.

The `:root` block is GENERATED rather than static, because the categorical colors
(`--c-person`, ...) follow the show's own entity_types and a fixed stylesheet can't
know them. Everything downstream reads colors through those variables, so this
function is the single point where a theme becomes pixels.
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "template.html")
VENDOR = os.path.join(HERE, "vendor")


def _json(obj):
    """Embed JSON inside <script>. The `</` guard is not optional: entity names and
    one-liners come from an LLM reading a transcript, and a literal '</script>' in
    any of them would end the tag and break (or hijack) the page. The original build
    guarded only the stats blob; copy is author-written but gets the same treatment."""
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return s.replace("</", "<\\/").replace(" ", "\\u2028").replace(" ", "\\u2029")


def _esc_attr(s):
    return (str(s or "").replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def root_css(theme, entity_types):
    """Render the Theme as the page's `:root` custom properties."""
    v = {
        "--night": theme.bg, "--night2": theme.bg2,
        "--panel": theme.panel, "--panel2": theme.panel2,
        "--accent": theme.accent, "--accentDim": theme.accent_dim,
        "--accent2": theme.accent2, "--accent2Glow": theme.accent2_glow,
        "--hl": theme.highlight, "--hl2": theme.highlight2, "--hlSoft": theme.highlight_soft,
        "--ink": theme.ink, "--muted": theme.muted, "--muted2": theme.muted2,
        "--line": theme.line,
        "--wood": theme.shelf_wood, "--wood2": theme.shelf_wood2,
        "--gold": theme.shelf_gold, "--goldSoft": theme.shelf_gold_soft,
        "--parch": theme.shelf_parch,
        "--globe-ocean": theme.globe_ocean, "--globe-land": theme.globe_land,
        "--globe-border": theme.globe_border, "--globe-graticule": theme.globe_graticule,
        "--globe-rim": theme.globe_rim,
        # Arcs and dots fade with weight, so JS needs the channels, not a color.
        "--globe-arc-rgb": theme.globe_arc_rgb, "--globe-dot-rgb": theme.globe_dot_rgb,
        "--cloud-label-ink": theme.cloud_label_ink,
        "--star": theme.star_color, "--star2": theme.star_color2,
        "--sans": theme.font_sans, "--serif": theme.font_serif,
        "--disp": theme.font_display, "--libserif": theme.font_libserif,
        "--mono": theme.font_mono,
    }
    for t in entity_types:
        v[f"--c-{t}"] = theme.type_colors.get(t, theme.type_color_fallback)
    body = "".join(f"  {k}:{val};\n" for k, val in v.items())
    return ":root{\n" + body + "}"


def _vendor(name):
    path = os.path.join(VENDOR, name)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"missing vendored asset: {path}\n"
            "The observatory bundles d3, topojson-client and the world atlas so the "
            "page has no network dependencies. See observatory/vendor/LICENSES.md."
        )
    with open(path, encoding="utf-8") as f:
        return f.read()


def build(stats, show, obs, template_path=None, with_vendor=True):
    """Return the finished HTML as a string."""
    path = template_path or TEMPLATE
    with open(path, encoding="utf-8") as f:
        html = f.read()

    theme, copy = obs.theme, obs.copy
    # A section that won't render is dropped from the page entirely; ship the flags
    # so the template doesn't re-derive the decision (and disagree).
    sections = stats["sections"]

    subs = {
        "__LANG__": _esc_attr(copy.lang or "en"),
        "__DIR__": _esc_attr(copy.text_direction or "ltr"),
        "__TITLE__": _esc_attr(copy.page_title),
        "__FONT_LINK__": (f'<link rel="preconnect" href="https://fonts.googleapis.com">'
                          f'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
                          f'<link href="{_esc_attr(theme.font_link)}" rel="stylesheet">')
                         if theme.font_link else "",
        "__ROOT_CSS__": root_css(theme, show.entity_types),
        "__STATS__": _json(stats),
        "__SECTIONS__": _json(sections),
        "__COPY__": _json(_copy_payload(copy)),
        "__THEME__": _json({
            # Only the list-valued theme bits live here — a CSS variable can't hold a
            # ramp, and d3 needs the array to interpolate.
            "cloud_ramp": list(theme.cloud_ramp),
            "book_palette": [list(p) for p in theme.book_palette],
        }),
        "__D3__": _vendor("d3.v7.min.js") if with_vendor else "",
        "__TOPO__": _vendor("topojson-client.min.js") if with_vendor else "",
        "__WORLD__": _vendor("world-110m.json") if with_vendor else "null",
    }
    for k, v in subs.items():
        html = html.replace(k, v)

    left = re.findall(r"__[A-Z_]+__", html)
    if left:
        raise RuntimeError(f"template still has unfilled placeholders: {sorted(set(left))}")
    return html


def _sec(s):
    return {"enabled": s.enabled, "eyebrow": s.eyebrow, "heading": s.heading, "sub": s.sub}


def _copy_payload(c):
    """The Copy dataclass as the `C` object the page reads. Flat and explicit: the
    template names every string it uses, so an unused field here is dead weight and a
    missing one is a visible blank rather than a crash."""
    return {
        "sections": {
            "globe": _sec(c.globe), "library": _sec(c.library), "records": _sec(c.records),
            "funfacts": _sec(c.funfacts), "hostface": _sec(c.hostface),
            "leaders": _sec(c.leaders), "cloud": _sec(c.cloud), "pulse": _sec(c.pulse),
            "wordlab": _sec(c.wordlab), "graph": _sec(c.graph),
            "shoutouts": _sec(c.shoutouts),
        },
        "hero": {
            "kicker": c.hero_kicker, "title_html": c.hero_title_html,
            "lead_html": c.hero_lead_html, "scroll_hint": c.hero_scroll_hint,
            "counters": c.counter_labels,
        },
        "nav": c.nav_labels,
        "episodes_word": c.episodes_word,
        # episode_label_tpl and hostface_groups are deliberately absent: stats.py
        # already applied them, so shipping them again would be dead weight the page
        # could disagree with.
        "type_labels": c.type_labels,
        "globe": {"legend": c.globe_legend, "hint": c.globe_dossier_hint},
        "library": {"kinds": c.book_kind_labels, "recommended": c.book_recommended_by,
                    "appeared": c.book_appeared_in, "gem": c.book_gem_chip},
        "records_cards": c.records_cards,
        "hostface": {"total": c.hostface_total_tpl},
        "leaders": {"cols": c.leader_col_headings, "notab_note": c.notab_note,
                    "scale": list(c.notab_scale_labels)},
        "pulse": {"streams": [dict(s) for s in c.timeline_streams],
                  "total": c.timeline_tooltip_total, "spark_heading": c.spark_strip_heading},
        "wordlab": {"stats": c.wl_stat_labels, "words_heading": c.wl_words_heading,
                    "ticker_heading": c.wl_ticker_heading, "ticker_note": c.wl_ticker_note},
        "graph": {"legend": c.graph_legend_title, "hint": c.graph_hint},
        "shoutouts": {"crowned": c.shoutout_crowned_tpl},
        "footer": {"logo_html": c.footer_logo_html, "prov": c.footer_prov_tpl,
                   "links": [list(l) for l in c.footer_links]},
    }
