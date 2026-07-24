<a id="readme-top"></a>

# The Podcast Observatory

A single self-contained HTML page of statistics about your podcast, built from the
episode archive the pipeline already caches. One file, no server, no CDN, no
tracking: open it from disk, mail it to a co-host, drop it on any static host.

**This document is written to be handed to an AI.** Say something like:

> Read OBSERVATORY.md and build my podcast's observatory.

It will read your show's config, run the build in report mode to see what your data
supports, ask you a few questions, and write exactly one new file:
`shows/<your-show>/observatory.py`. Everything else is already here.

You can of course write that file yourself — `shows/_template/observatory.py` is a
commented starter, and `shows/demo/observatory.py` is a filled-in example.

---

## The one idea

**Python computes every number. The AI only chooses colors and writes words.**

No language model does arithmetic across sixty episodes, so the figures on the page
are just correct. In return, the copy never states a figure — it interpolates one:

```python
# wrong — true the day it was written, wrong by next Tuesday
hero_kicker="65 episodes · 88.9 hours"

# right — the build fills these in on every run
hero_kicker="{episodes} episodes · {hours} hours"
```

This is the rule the whole design exists to protect. **A number typed into a caption
is a bug**, even when it's accurate today.

---

## For the AI: the procedure

### 1. Read the show's config first

`shows/<name>/config.py`. Take from it:

| Field | Why it matters |
|---|---|
| `entity_types` | The page's whole taxonomy. **Do not assume the default eight.** Every color, column, stream and card follows this list. |
| `hosts`, `guest_label` | The face-off compares hosts. Two hosts is not a given — the demo show has three. |
| `text_direction`, `stt_language` | Set `Copy.lang` / `Copy.text_direction` from these, or leave blank and they're derived. |
| `display_name` | The default page title and wordmark. |
| `notion_type_labels` | Free, already-translated type names. `type_labels` defaults to these with the emoji stripped — don't retype them. |
| `db_link` | The default footer link. |

Also read `shows/demo/observatory.py`. It is the reference: Hebrew, RTL, three hosts,
a theme with nothing in common with the default.

### 2. Run the report BEFORE writing anything

```bash
SHOW=<name> python build_observatory.py --dry-run
```

It prints, per section, whether it will render and why:

```
sections:
  ON  globe      41 placed (needs 3)
  ON  library    23 books/articles (needs 6)
  off hostface   1 of 3 hosts with attribution (needs 2)
  ON  graph      88 edges (needs 12)
```

plus every place it couldn't map, and every fun fact that found data.

**Writing copy for a section that will auto-hide is the single most common way to
waste an hour here.** A section renders only when it's both switched on and backed by
enough data — see [what makes a section appear](#what-makes-a-section-appear).

### 3. Ask the user — actually ask, then wait

Four questions. Show them the dry-run's ON/off list so the first one is informed.

1. **Which sections?** Offer a choice:
   - **Lean core** — hero, records, league table, pulse, map, odds-and-ends, footer.
     A tight page that works on a young archive.
   - **The full set** — everything the data supports: globe, library, head-to-head,
     ideas cloud, language.
   - Or pick individually from the ON list.
2. **Mood, vibe, colors.** Two or three adjectives, any brand colors, and whether
   the show has an existing visual identity. This is what the theme is for — the
   default is deliberately neutral so it looks unfinished until someone chooses.
3. **The wordmark.** The hero title may carry markup, e.g.
   `hero_title_html='Table<span class="ac">4</span>'` accents the "4" in the accent
   color. Ask how they want their name set.
4. **A running bit?** Only if they volunteer one — a recurring guest, a listener who
   built something, an in-joke award — turn on `shoutouts` and write the entries.
   **Never invent shout-outs.** Off is the correct default.

### 4. Write exactly one file

`shows/<name>/observatory.py`, starting from `shows/_template/observatory.py`.

Do not touch `observatory/`, `showkit.py`, `build_observatory.py`, or the template.
If something genuinely needs a structural change, say so and stop — don't work
around it in a show file.

### 5. Renumber the eyebrows

Section numbers are hand-written into the eyebrow (`"01 · The globe"`) precisely so
you can renumber after the user drops a section. Don't leave a gap at 03.

### 6. Build it, read the report, close the loop

```bash
SHOW=<name> python build_observatory.py
open dist/<name>_observatory.html
```

- **UNGEOCODED places**: the report prints them ready to paste into
  `Observatory.extra_place_coords`. You know most latitudes and longitudes — fill
  them in. That is the intended workflow; there is no geocoding API here.
- **facts with no copy**: a fact that found data but has no caption is listed. Write
  it or leave it out of `funfact_order` on purpose.
- **Check contrast**: the page is dark-on-dark by default. If the user picked a
  palette, `ink` against `bg` and against `panel` should clear 4.5:1. A washed-out
  `muted` is the usual casualty.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

---

## The fields

### Copy templates

Every one of these is optional; each falls back on its own.

| Field | Fields it can interpolate |
|---|---|
| `hero_kicker` | `{episodes}` `{entities}` `{hours}` `{places}` |
| `footer_prov_tpl` | `{episodes}` `{entities}` `{from}` `{to}` `{built}` |
| `hostface_total_tpl` | `{n}` |
| `book_recommended_by` | `{host}` |
| `book_appeared_in` | `{n}` (the episode label) |
| `shoutout_crowned_tpl` | `{ep}` `{episode_word}` |
| `episode_label_tpl` | `{n}` — how an episode is named across the whole page |

### Fun facts

`funfact_copy = {id: {"title": ..., "cap": <template>}}`, ordered by `funfact_order`.
A fact renders only if it found data **and** is in the order **and** has copy.

| fact id | fields available to `cap` |
|---|---|
| `all_the_types` | `{n}`, `{kinds}` |
| `average_episode` | `{n}`, `{mins}` |
| `busiest_episode` | `{label}`, `{n}`, `{headline}`, `{number}` |
| `globetrotter_host` | `{host}`, `{n}` |
| `hours_in_ears` | `{hours}`, `{days}` |
| `inseparable_pair` | `{a}`, `{b}`, `{n}` |
| `lightest_episode` | `{label}`, `{dur}`, `{number}` |
| `longest_name` | `{name}`, `{len}`, `{type}` |
| `marathon` | `{label}`, `{dur}`, `{number}` |
| `one_hit_wonders` | `{n}`, `{pct}` |
| `rarest_gem` | `{n}` |
| `reading_shelf` | `{n}`, `{books}`, `{articles}`, `{per_ep}` |
| `regular_star` | `{name}`, `{n}`, `{eps}`, `{pct}` |
| `returning_faces` | `{n}`, `{pct}` |
| `social_butterfly` | `{name}`, `{n}` |
| `word_avalanche` | `{n}`, `{per_ep}` |
| `world_vs_market` | `{ratio}` — off by default; only means something if your show's line really is world-vs-markets |

A caption naming a field a fact doesn't emit renders the `{marker}` literally rather
than failing the build — so proofread the page, and check the report.

### Records cards

`records_cards = {id: {"title": ..., "cap": <template>}}`.

| card id | fields |
|---|---|
| `top_<type>` — one per entity type, e.g. `top_person` | `{name}`, `{n}`, `{one_liner}` |
| `gems` | `{n}` |
| `busiest` | `{label}`, `{n}`, `{headline}` |
| `most_places` | `{label}`, `{n}` |
| `longest_name` | `{len}`, `{name}`, `{type}` |
| `host_counts`, `type_totals` | — (the card is the chart) |

### Grouping the taxonomy

Eight entity types is too fine-grained for two of the charts. Group them into axes
that mean something for the show — this is an editorial choice, and it's the one
place the page says what the show is *about*:

```python
hostface_groups=(
    {"label": "People",  "types": ("person",)},
    {"label": "Markets", "types": ("stock", "company")},
    {"label": "Ideas",   "types": ("concept", "book", "article")},
)
timeline_streams=(
    {"key": "geo",  "label": "The world", "types": ("place", "other")},
    {"key": "mkt",  "label": "Markets",   "types": ("stock", "company")},
    {"key": "idea", "label": "Ideas",     "types": ("concept", "book", "article")},
)
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

---

## What makes a section appear

`enabled` in the copy, **and** enough data to be worth drawing. The thresholds exist
because an empty chart looks more broken than a missing one.

| Section | Needs |
|---|---|
| `globe` | 3+ places with known coordinates |
| `library` | 6+ books/articles |
| `records` | any type with a leader |
| `funfacts` | 4+ facts with data and copy |
| `hostface` | 2+ hosts with attributed mentions |
| `leaders` | any ranked type |
| `cloud` | 12+ concepts |
| `pulse` | 4+ episodes |
| `wordlab` | transcripts, or 8+ tickers (each block gates separately) |
| `graph` | 12+ surviving edges |
| `shoutouts` | entries you wrote — off otherwise |

Two things worth knowing:

- **Attribution can be blank.** `extract.py` deliberately drops `mentioned_by` when
  speaker diarization is unreliable. A two-host show can still have no face-off, and
  that's honest rather than broken.
- **The language section needs `transcripts/`.** They're a local cache. If they were
  cleaned up, the word blocks vanish and the ticker wall carries the section alone.

## The theme

Every chart reads its colors out of CSS variables at runtime, so `Theme` really is
the look of the page — including the canvas globe, the force-packed bubbles and the
bookshelf. There are no hardcoded colors below `:root`; a test enforces it.

Start with `bg`, `accent`, `highlight`, `ink` and `type_colors`. The rest inherit
sensibly. `type_colors` is the legend for the whole page: it's the same color for a
type in the globe, the map, the league table, the pulse and the spread.

Fonts default to system stacks. `font_link` accepts a Google Fonts URL, but weigh it:
it's a network request on every view — and an EU privacy question — for a page whose
whole point is that it works from a `file://` URL with no network at all.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

---

## Running it

```bash
SHOW=<name> python build_observatory.py --dry-run     # what would render, and why
SHOW=<name> python build_observatory.py               # -> dist/<name>_observatory.html

# Try it without your own archive — the test fixtures are a synthetic 8-episode show:
SHOW=demo python build_observatory.py \
  --extractions tests/fixtures/observatory/extractions \
  --transcripts tests/fixtures/observatory/transcripts \
  --out dist/demo.html && open dist/demo.html
```

| Flag | |
|---|---|
| `--extractions DIR` | Where the episode json lives. Default `./extractions`. |
| `--transcripts DIR` | Transcripts, matched by guid. Default `./transcripts`. |
| `--out PATH` | Output file. |
| `--dry-run` | Report only; writes nothing. |
| `--stats-json PATH` | Also dump the computed STATS, for debugging. |
| `--no-vendor` | Skip inlining d3 — a fast, tiny, non-working page. Tests use it. |

**One caveat worth knowing:** `extractions/` and `transcripts/` live at the repo root
and are **not** per-show. If you run two podcasts from one checkout, both shows'
episodes are in the same directory and a plain build would quietly mix them into one
page. Point `--extractions` at the right data when that applies to you.

## How it fits together

```
build_observatory.py        entry point: load, report, write
observatory/
  stats.py                  pure: (episodes, transcripts, show, obs) -> STATS
  defaults.py               fills in whatever your observatory.py didn't say
  place_coords.py           ~330 bundled place -> [lat, lon] entries
  assemble.py               injects stats/theme/copy/vendor into the template
  template.html             the page itself — no copy, no colors, no show
  vendor/                   d3 + topojson + world atlas (ISC; see LICENSES.md)
shows/<name>/observatory.py  ← the only file you write
```

The page weighs roughly 500 KB for a small archive: about 395 KB of that is the
vendored d3 and the world map, and the rest is your data, which grows with the
archive. It gzips to a fraction of that and it is genuinely one file.

<p align="right">(<a href="#readme-top">back to top</a>)</p>
