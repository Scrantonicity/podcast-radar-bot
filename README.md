# podcast-radar-bot

Turn any podcast into a **radar for the interesting things its hosts mention** —
companies, stocks, books, people, concepts — automatically, every week, in any
language.

Each new episode is transcribed, mined for the notable entities discussed, written
to a structured **Notion** database, and broadcast as a short, ranked digest to a
**Telegram** channel. A human taps **Approve** on their phone before anything goes
public.

```
RSS feed ──▶ transcribe ──▶ extract entities ──▶ Notion (Episodes + Entities)
 (feed.py)  (Speechmatics)     (Gemini)              (notion_bridge.py)
                                                            │
                                                            ▼
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

## Deployment

- **GitHub Actions** — `.github/workflows/pipeline.yml` (manual dispatch: `auto` /
  `latest` / `episode` / `preview`, plus a weekly schedule) and
  `approve_poll.yml` (the 5-minute approval poller). Keys come from repo
  **secrets**; `SHOW` and `EXTRACTION_MODEL` from repo **variables**.
- **systemd on a VPS** — `deploy/` (`podcast-radar.service` + `.timer`, plus
  `setup.sh`). Edit the schedule/timezone in the `.timer` to match your show. See
  `deploy/README.md`.

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
  second hardcoded model).
- **`notion_bridge.py`, not `notion_client.py`** — the latter would shadow the
  official `notion-client` SDK.

---

## Layout

```
showkit.py            # the ShowConfig + Strings schema (field docs live here)
show_loader.py        # picks SHOW, exposes SHOW / STRINGS / PROMPT to the engine
config.py             # env / secrets loader
feed.py stt.py transcribe.py extract.py notion_bridge.py notify.py   # the engine
main.py auto_review.py approval_poller.py approve.py friday_preview.py
run_one.py telegram_check.py                                          # entry points
shows/table4/  shows/_template/      # per-podcast config + prompt + strings
scripts/       # reusable utilities: merge_entities, rebroadcast, backfill_notion
tests/         # test_guardrails, test_transcribe_resume, test_bridge
deploy/  .github/workflows/          # systemd + GitHub Actions
```

## Maintenance utilities (`scripts/`)

Not part of the weekly run — operator tools:

| Script | Purpose |
|--------|---------|
| `scripts/backfill_notion.py` | Fill links / entity context / transcript links on existing rows. |
| `scripts/merge_entities.py` | Merge duplicate entity pages (define groups in its `FIX` list). Dry-run by default. |
| `scripts/rebroadcast.py` | Wipe the channel and re-post every episode in the current format. |

---

Built with Speechmatics (STT), Google Gemini (extraction), Notion, and Telegram.
