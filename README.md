# podcast-radar-bot

Turn any podcast into a **radar for the interesting things its hosts mention** —
companies, stocks, books, people, concepts — automatically, every week, in any
language.

Each new episode is transcribed, mined for the notable entities discussed, written
to a structured **Notion** database, and broadcast as a short, ranked digest to a
**Telegram** channel. A human taps **Approve** on their phone before anything goes
public.

```
RSS feed ──▶ transcribe ──▶ extract entities ──▶ resolve ──▶ Notion (Episodes + Entities)
 (feed.py)  (Speechmatics)     (Gemini)         (dedup +      (notion_bridge.py)
                                              name-fixing)          │
                                          (resolve_entities.py)     ▼
                                     private "Approve?" draft ──tap──▶ Telegram channel
                                            (notify.py)              (approval_poller.py)
```

It ships configured for a real Hebrew show (**שולחן 4 / "Table 4"**) as a working
example. Pointing it at *your* podcast, in *any* language, is **three files and one
env var — no engine code changes.**

---

## How it's built: engine vs. show

Everything splits into two layers:

- **The engine** (repo root: `feed.py`, `stt.py`, `transcribe.py`, `extract.py`,
  `notion_bridge.py`, `notify.py`, the orchestrators) — generic, podcast- and
  language-agnostic. You never edit it to add a show.
- **A show** (`shows/<name>/`) — three files that describe one podcast:

  | File | What it holds |
  |------|---------------|
  | `config.py` | Identity, feed source, STT language, hosts, sponsors, digest layout — a `ShowConfig` object. |
  | `prompt.txt` | The extraction system prompt (the editorial brain, in your language). |
  | `strings.py` | Every user-facing string — Telegram + Notion labels, buttons, alerts. |

  Plus three **optional** prompt files in the same folder; omit one and that stage
  simply doesn't run:

  | Optional file | Enables |
  |---------------|---------|
  | `resolve.txt` | The entity resolution pass — fixes speech-to-text-garbled names and folds variants onto existing DB entities before writing. |
  | `regen.txt` | Meta-context repair (rewrites "who said it" contexts into "what it is"). |
  | `backfill.txt` | The archive dedup clustering pass (`scripts/backfill_cleanup.py`). |

`SHOW=<name>` in `.env` selects which show runs. The engine reads it through
`show_loader.py` and pulls in that show's config, prompt, and strings. The schema
for `config.py` / `strings.py` lives in `showkit.py` (well-commented defaults).

Two shows are bundled: **`table4`** (the filled Hebrew example) and **`_template`**
(a blank, English, left-to-right starter).

---

## Quickstart (run the bundled example)

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # then fill in the keys (see below)
```

You need accounts / keys for:

- **Speechmatics** — `SPEECHMATICS_API_KEY` (speech-to-text; ~100 languages).
- **Google Gemini** — `GOOGLE_API_KEY` (entity extraction). Model via `EXTRACTION_MODEL`.
- **Notion** — `NOTION_TOKEN` + two databases (Episodes + Entities) and their four
  DB / data-source IDs.
- **Telegram** — a bot (`TELEGRAM_BOT_TOKEN` from @BotFather) added to your channel
  **as an admin with "Post Messages"**, plus `TELEGRAM_CHAT_ID`. For the approval
  flow, also a private chat (`TELEGRAM_ALERT_CHAT_ID`) and your user id
  (`TELEGRAM_APPROVER_ID`).

Preflight the Telegram wiring, then run one episode:

```bash
python telegram_check.py            # posts a test message to the channel
python main.py --episode 1          # newest episode, end-to-end
```

---

## Add your own podcast (in 3 files)

```bash
cp -r shows/_template shows/mypodcast
```

Then edit the three files and set `SHOW=mypodcast` in `.env`. That's it.

**1. `shows/mypodcast/config.py`** — fill in the `ShowConfig`. The fields:

| Field | Meaning |
|-------|---------|
| `display_name` | Shown in the digest header and alerts. |
| `feed_apple_id` **or** `feed_rss_url` | Where episodes come from. Give one. An Apple id also enriches with Apple/Spotify/YouTube links. |
| `stt_language` | Speechmatics language code (`en`, `he`, `es`, …). |
| `stt_additional_vocab` | Names the transcriber keeps mishearing (brands, people) — no code edit needed to fix them. |
| `text_direction` | `"ltr"` or `"rtl"` — controls bidi handling in the digest. |
| `date_format` | strftime for the header date (`"%b %d, %Y"` / `"%d.%m.%y"`). |
| `hosts` | Your regular hosts (short names). **Single source of truth** — used by the prompt, the schema, attribution, and Notion tags. |
| `host_ban_keys` / `sponsor_ban_keys` | Never surface hosts or ad-read sponsors as entities. |
| `native_script_re`, `translit_singles`, `translit_digraphs` | Only for non-Latin scripts: a best-effort romanization map so a native-script name and its Latin twin ("אנבידיה"/"Nvidia") are recognised as one entity. Leave empty for Latin-script shows. |
| `db_link` | Public link to your Notion database (appended to every digest). |
| `tg_sections`, `tg_type_caps`, … | The digest layout: which entity types appear, section headings, per-type caps. |
| `notion_type_labels`, `notion_learn_type_nouns` | Labels for the Notion episode-page body. |

**2. `shows/mypodcast/prompt.txt`** — the extraction prompt, in your language. Start
from the template's English version (it already encodes the entity taxonomy, the
1–5 "notability" rubric, and the exclusion rules) and adapt the editorial voice.
Markers `{{SHOW_NAME}}`, `{{HOSTS}}`, `{{GUEST_LABEL}}` are auto-filled from your
config, so hosts stay in one place.

**3. `shows/mypodcast/strings.py`** — override any user-facing text. Defaults are
English; translate the ones you want. Keep the `{placeholder}` tokens.

Nothing else changes — the same engine, the same Notion/Telegram wiring, your show.

---

## Running

`main.py` selects targets and runs the pipeline:

```bash
python main.py                  # weekly: only episodes not yet "done" in Notion
python main.py --episode N       # one episode (N=1 = newest)
python main.py --backfill        # every episode oldest→newest (rate-limited, resumable)
python main.py --cached-only     # only episodes with a cached transcript (no STT calls)
python main.py --no-telegram     # suppress the channel post (testing)
```

**Two ways episodes reach the channel:**

1. **Direct** — `main.py` posts the digest straight to the channel. Simple,
   unattended. Good for a VPS timer.
2. **Approval-gated (recommended)** — `auto_review.py` writes Notion and sends the
   digest to your **private** chat with Approve / Reject buttons; nothing reaches
   the public channel until you tap Approve (a 5-minute `approval_poller.py` cron
   releases it). This is the safe default the CI workflow uses.

Caches (`transcripts/`, `extractions/`, keyed by episode GUID) are checkpoints:
re-running an episode reuses them instead of paying for STT / the LLM again. Every
non-`--episode` run is capped (`MAX_EPISODES_PER_RUN`) so a feed glitch can't fan
out into many paid jobs.

---

## Entity resolution (keeping the database clean)

Speech-to-text garbles names, and the same thing gets said two ways ("אנבידיה" one
week, "Nvidia" the next) — so a naive pipeline slowly fills your database with
duplicates. Between extraction and the Notion write, `resolve_entities.py` runs a
resolution pass that:

1. finds candidate matches among existing entities (`entity_match.py`: romanized
   comparison + fuzzy matching via rapidfuzz + cross-lingual embeddings),
2. asks the LLM, per entity, to correct STT mis-hears to the true name, emit a clean
   canonical key, and decide *same-as-existing* vs *new*,
3. folds variants onto the existing page and records the old spelling in an
   **Aliases** column, so the same variant short-circuits next time.

It is **fail-open** — any error and the raw extraction flows through untouched; it can
never break the pipeline. It only runs if your show has a `resolve.txt`. In the
approval-gated flow the corrections are appended to the private draft so you can review
them before approving. Models: `RESOLVE_MODEL` + `EMBEDDING_MODEL`.

Already-messy archive? `scripts/backfill_cleanup.py` clusters duplicate candidates and
LLM-confirms merges into a proposals file; `scripts/apply_backfill.py` applies the ones
you approve (losers go to Notion trash — recoverable for 30 days).

---

## Deployment

- **GitHub Actions** — `.github/workflows/pipeline.yml` (manual dispatch: `auto` /
  `latest` / `episode` / `preview`, plus a weekly schedule) and
  `approve_poll.yml` (the 5-minute approval poller). Keys come from repo
  **secrets**; `SHOW` and `EXTRACTION_MODEL` from repo **variables**.
- **systemd on a VPS** — `deploy/` (`podcast-radar.service` + `.timer`, plus
  `setup.sh`). Edit the schedule/timezone in the `.timer` to match your show. See
  `deploy/README.md`.

**Once it matters, get off GitHub cron.** GitHub's `schedule:` is best-effort and
silently drops runs — in production it dropped a Friday run and an episode was never
processed. **[RELIABILITY.md](RELIABILITY.md)** walks through triggering the pipeline
from an external scheduler (GCP Cloud Scheduler → `workflow_dispatch`, which isn't
throttled), plus `watchdog.py` — a dead-man alert that pings your private chat if the
week's episode wasn't processed in time, and stays silent otherwise.

---

## Gotchas already handled for you

Hard-won lessons from running this in production, baked into the engine as
invariants (and covered by `tests/test_guardrails.py`):

- **Public posts are fail-closed.** `notify.send_telegram()` refuses to post to the
  channel unless a caller explicitly passes `allow_public=True`. The safe path is
  the private draft + approval tap. (A one-off script once posted straight to the
  channel with no review — gating by intent, not by which function you call, fixes it.)
- **Notion "trash", not "archive".** `notion_bridge.trash_page()` uses `in_trash=True`
  (this API version rejects `archived=True`).
- **Editing a select never drops options.** `notion_bridge.update_select_options()`
  always re-sends the full options list; a partial update silently deletes omitted
  options and strips their values from every row.
- **URLs are capped at 2000 chars.** `notion_bridge.cap_url()` guards every url-property
  write (Notion 400s past 2000; non-Latin text URL-encodes to ~9 bytes/char).
- **Hosts & sponsors can't drift.** They live once in `config.py` and feed the prompt,
  schema, attribution, and Notion tags; a rename can't half-apply.
- **One model id.** Extraction reads `config.EXTRACTION_MODEL` everywhere (never a
  second hardcoded model). The resolver has its own `RESOLVE_MODEL` on purpose.
- **`notion_bridge.py`, not `notion_client.py`** — the latter would shadow the
  official `notion-client` SDK.
- **The RSS feed is cache-busted.** Podcast CDNs happily serve a stale feed for an
  hour+ after publish; a plain GET made the pipeline read yesterday's episode as
  "newest" and skip the real one. `feed.list_episodes()` forces a fresh fetch.
- **GitHub cron drops runs.** Don't trust `schedule:` for anything that matters —
  see [RELIABILITY.md](RELIABILITY.md) + `watchdog.py`.

---

## Layout

```
showkit.py            # the ShowConfig + Strings schema (field docs live here)
show_loader.py        # picks SHOW, exposes SHOW / STRINGS / PROMPT / RESOLVE_PROMPT
config.py             # env / secrets loader
feed.py stt.py transcribe.py extract.py notion_bridge.py notify.py   # the engine
entity_match.py resolve_entities.py   # entity dedup + resolution
main.py auto_review.py approval_poller.py approve.py friday_preview.py
run_one.py telegram_check.py watchdog.py                              # entry points
shows/table4/  shows/_template/      # per-podcast config + prompt + strings
scripts/       # operator utilities (see below)
tests/         # guardrails, entity_match, resolve, transcribe_resume, bridge
deploy/  .github/workflows/          # systemd + GitHub Actions
RELIABILITY.md        # getting off GitHub cron: external trigger + dead-man alert
```

## Maintenance utilities (`scripts/`)

Not part of the weekly run — operator tools:

| Script | Purpose |
|--------|---------|
| `scripts/backfill_notion.py` | Fill links / entity context / transcript links on existing rows. |
| `scripts/merge_entities.py` | Merge duplicate entity pages by hand (define groups in its `FIX` list). Dry-run by default. |
| `scripts/backfill_cleanup.py` | Cluster duplicate candidates across the whole archive + LLM-confirm merges → a proposals file. |
| `scripts/apply_backfill.py` | Apply approved proposals (merges + renames; losers → Notion trash, 30-day recoverable). |
| `scripts/rebroadcast.py` | Wipe the channel and re-post every episode in the current format. |

---

Built with Speechmatics (STT), Google Gemini (extraction), Notion, and Telegram.
