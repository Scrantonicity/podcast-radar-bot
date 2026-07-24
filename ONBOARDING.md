# Onboarding a new podcast

This is a step-by-step playbook for pointing podcast-radar-bot at **your** podcast —
in any language. It is written to be followed by an **AI coding agent** (Claude Code,
Codex, Gemini CLI, …) *or* by a human. If you are an agent: do the steps in order, ask
the operator the interview questions in Step 1, and stop for the human only where a step
says so (API keys, Notion duplication, paying for a transcript).

The whole idea of the bot is a clean split:

- **The engine** (repo root `.py` files) is generic and you never edit it.
- **A show** is one folder, `shows/<name>/`, describing a single podcast.

Onboarding = produce that folder for your show, wire up Notion + keys, run one episode.

> **Why an interview + a sample transcript?** Every podcast talks about different things.
> A markets show surfaces stocks, companies, and books; a history show surfaces people,
> places, and events; a cooking show surfaces recipes, ingredients, and techniques. The
> bot's **entity taxonomy adapts per show** — and the reliable way to get it right is to
> (1) ask you what the show is about and (2) read one real episode. Steps 1 and 3 feed
> Step 4, where the taxonomy is chosen.

---

## Step 0 — Prerequisites

Accounts / API keys you'll need (collect what you can now; each step says when it's used):

| Service | Env var | Needed for | Notes |
|---|---|---|---|
| **Speechmatics** | `SPEECHMATICS_API_KEY` | transcription | ~100 languages. Skip if you only ever paste your own transcripts. |
| **Google Gemini** | `GOOGLE_API_KEY` | entity extraction | Free-tier keys from [AI Studio](https://aistudio.google.com/) work to start. |
| **Notion** | `NOTION_TOKEN` + 4 IDs | structured output | An internal integration + the two databases (Step 6). |
| **Telegram** | `TELEGRAM_*` | digest delivery | **Optional.** Skip entirely for a Notion-only setup. |

```bash
git clone https://github.com/Scrantonicity/podcast-radar-bot.git
cd podcast-radar-bot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # you'll fill this in as you go
```

---

## Step 1 — The interview

Ask the operator (or answer yourself). Keep the answers — Steps 4 and 5 use them.

1. **Show name** (as it should appear in the digest header).
2. **Language** and **direction** — e.g. English / `ltr`, Hebrew or Arabic / `rtl`.
3. **Hosts** — the exact short names the hosts call each other by, in the show's own
   script. Give **every spelling** each host might appear under (native script + any
   Latin transliteration). This matters more than it looks: the transcriber mishears
   names, and hosts must never leak into the database as "entities".
4. **What should the radar track?** In plain words: "companies and stocks the hosts
   discuss", "historical figures and places", "papers and researchers", "gadgets and
   apps", … This is the seed for the taxonomy.
5. **Sponsors / ad-read brands** to always ignore (if any).
6. **Brand / proper nouns the transcriber is likely to mangle** — product names, foreign
   companies, jargon. These become `stt_additional_vocab` so Speechmatics gets them right.

---

## Step 2 — Find the real RSS feed

The pipeline reads an **RSS feed**. A Spotify or Apple *web link is not an RSS feed.*

- Easiest: find the show's **Apple Podcasts id** (the number in its Apple URL,
  `podcasts.apple.com/.../id1739161374`) → set `feed_apple_id`. The engine resolves the
  RSS and also enriches episodes with Apple/Spotify/YouTube links.
- Or find a **direct RSS url** (many shows host on anchor.fm/Spotify for Podcasters:
  `https://anchor.fm/s/XXXXXXXX/podcast/rss`) → set `feed_rss_url`.
- Supply **exactly one** of the two.

Sanity check once you've scaffolded the show (Step 5):
`SHOW=<name> python -c "import feed; print(feed.list_episodes()[:2])"` should print recent episodes.

---

## Step 3 — Get one sample transcript

Step 4 needs the text of **one** representative episode. Two ways:

- **Paste one you already have.** Any plain-text transcript of a typical episode. Best if
  it marks speakers, but not required.
- **Run Speechmatics once.** After scaffolding (Step 5) with `SPEECHMATICS_API_KEY` set:
  `SHOW=<name> python main.py --episode 1 --no-telegram` transcribes the newest episode and
  caches it under `transcripts/`. (This also runs extraction — that's fine; you'll review it.)

> **Cost:** Speechmatics batch is roughly **$0.60 for a one-hour episode** (measured:
> about $40 for 65 episodes). Extraction on Gemini Flash is negligible. Transcribing a
> whole back-catalogue is the only place real money adds up — Step 9 covers the caps that
> stop a runaway backfill.

---

## Step 4 — Derive the taxonomy (the adaptive step)

Using the **interview answers (Step 1)** and the **sample transcript (Step 3)**, decide the
show's entity taxonomy. The engine imposes no entity types of its own — they come entirely
from the show folder — so this is where a markets show and a history show diverge.

**If an agent is doing this, follow this instruction block:**

> Read the sample transcript. From it and the interview, propose:
> 1. **`entity_types`** — the 4–8 kinds of thing worth surfacing for THIS show. Start from
>    the default set (`person, company, stock, place, concept, book, article, other`) and
>    **keep what fits, drop what never occurs, add what's missing**. A cooking show might be
>    `person, ingredient, dish, technique, tool, place, other`; a history show
>    `person, place, event, concept, book, other`. Keep `other` as a catch-all.
> 2. **Digest sections** (`tg_sections`) — how those types group into headings in the
>    Telegram digest, in priority order, each with an emoji + heading text in the show's language.
> 3. **Per-type labels** (`notion_type_labels`, `notion_learn_type_nouns`) for the Notion
>    episode-page body, in the show's language.
> 4. **`action_by_type`** (only if you added a non-default type) — which Notion follow-up
>    Action a new type maps to (`To Read` / `To Research` / `To Watch` / `To Look Up`), or
>    leave it unmapped for no action.
> 5. **`stt_additional_vocab`** — the brand/proper nouns from Step 1 plus any the transcript
>    shows getting mangled.
>
> Show the operator the proposed taxonomy and get their OK before writing files.

**Load-bearing rule:** the taxonomy lives in **two places that must agree** — the
`entity_types` tuple (and the layout dicts) in `config.py`, **and** the prose list of
allowed types with their definitions in `prompt.txt`. If you change one, change the other.
The engine reads `entity_types` from config; the model reads the definitions from the prompt.

---

## Step 5 — Scaffold `shows/<name>/`

```bash
cp -r shows/_template shows/mypodcast     # lowercase, no spaces
```

Then edit the three required files (all fields marked `TODO` in `shows/_template/`):

- **`config.py`** — fill in the `ShowConfig`: `display_name`, the feed (Step 2),
  `stt_language` + `text_direction` + `date_format`, `hosts` + `host_ban_keys` (every
  spelling from Step 1), `sponsor_ban_keys`, `stt_additional_vocab`, `db_link`, and the
  taxonomy from Step 4 (`entity_types`, `tg_sections`, `tg_type_caps`, `notion_type_labels`,
  …). For a non-Latin script, also fill the romanization maps (`native_script_re`,
  `translit_singles`, `translit_digraphs`) so cross-script duplicates fold together — the
  demo show's Hebrew maps are a worked example.
- **`prompt.txt`** — the extraction prompt in the show's language. Start from the template's
  English version (it already encodes the notability rubric and exclusion rules) and adapt:
  the editorial voice, and — if you changed the taxonomy in Step 4 — the **allowed types and
  their definitions**. Markers `{{SHOW_NAME}}`, `{{HOSTS}}`, `{{GUEST_LABEL}}` are auto-filled
  from config, so hosts stay defined in one place.
- **`strings.py`** — override user-facing text you want changed/translated (at minimum
  `tg_header_prefix`). Keep the `{placeholder}` tokens.

Optional files in the same folder — omit one and that stage simply doesn't run:
`resolve.txt` (entity-resolution / name-fixing pass), `regen.txt` (meta-context repair),
`backfill.txt` (archive dedup), `observatory.py` (stats-page theme — see [OBSERVATORY.md](OBSERVATORY.md)).

Set the active show in `.env`:  `SHOW=mypodcast`

---

## Step 6 — Wire up Notion

1. **Duplicate the template.** Open the template and click **Duplicate** (top-right) into
   your own workspace:
   - English: **https://maddening-robe-93b.notion.site/3a74824966ba81b1b76fee717032eb32?v=3a74824966ba80899a43000ccbba0922**
   - Hebrew: **https://maddening-robe-93b.notion.site/3a74824966ba814bb633c51e4ccc70ac?v=3a74824966ba801eb9c7000cf455994e**

   It contains an **Episodes** database and an **Entities** database, already related, with
   the exact property names and select options the bot writes to, plus the **Tools** and
   **Guests** views. A short guide page inside the template repeats these steps with pictures.
2. **Create an internal integration** at
   [notion.so/my-integrations](https://www.notion.so/my-integrations) → copy its token
   (`ntn_…`) into `NOTION_TOKEN` in `.env`.
3. **Share both databases with the integration:** open each database → `•••` → **Connections**
   → add your integration. (Skipping this is the #1 cause of a `404` / "not found".)
4. **Get the four IDs.** The two **database IDs** are the 32-hex strings in each database's
   page URL → `NOTION_EPISODES_DB_ID`, `NOTION_ENTITIES_DB_ID`. The two **data-source IDs**
   are not in any URL — let the helper fetch them:
   ```bash
   python scripts/notion_ids.py       # prints NOTION_EPISODES_DS_ID / NOTION_ENTITIES_DS_ID
   ```
   Paste its two lines into `.env`. (A stale data-source id is the classic first-run 404 —
   this helper is exactly why.)

The bot **creates missing select options on the fly**, so a taxonomy with new types just
works; you don't have to pre-create them in Notion.

---

## Step 7 — Telegram (optional)

Skip this whole step for a Notion-only setup (run with `--no-telegram`).

To deliver the ranked digest to a channel with a human **Approve** tap:
- Create a bot with [@BotFather](https://t.me/BotFather) → `TELEGRAM_BOT_TOKEN`.
- Add it to your channel **as an admin with "Post Messages"** → set `TELEGRAM_CHAT_ID`.
- For the approval flow, also set `TELEGRAM_ALERT_CHAT_ID` (your private chat) and
  `TELEGRAM_APPROVER_ID` (your numeric user id). See `.env.example` for the full set.
- Preflight: `python telegram_check.py` posts a test message.

---

## Step 8 — First run + verify

```bash
SHOW=mypodcast python main.py --episode 1 --no-telegram
```

This runs the full pipeline on the newest episode with **no channel post**. Expect a
final line like `==== SUMMARY ==== processed=1 skipped=0 failed=0`. Then open your Notion
**Entities** database and check:

- entities from the episode appear, typed per your taxonomy;
- hosts did **not** leak in as entities (fix `host_ban_keys` if any did);
- if the episode had a guest, they're present with the **Guest** checkbox ticked;
- names look right (add mangled ones to `stt_additional_vocab` and re-run).

Re-running the same episode is cheap: transcripts and extractions are cached by GUID, so
it won't pay for STT or the LLM again.

---

## Step 9 — Going live

- **Approval-gated posting (recommended):** `auto_review.py` writes Notion and sends the
  digest to your private chat with Approve/Reject buttons; nothing hits the public channel
  until you tap Approve. See the README's *Usage* and *Deployment* sections.
- **Scheduling:** GitHub Actions (`.github/workflows/pipeline.yml`) or a systemd timer
  (`deploy/`). Read **[RELIABILITY.md](RELIABILITY.md)** before relying on cron.
- **Backfill the archive:** `python main.py --backfill` walks every episode oldest→newest,
  rate-limited and resumable. Every non-`--episode` run is capped
  (`MAX_EPISODES_PER_RUN`) so a feed glitch can't fan out into many paid transcription jobs.

---

## Troubleshooting (hard-won)

| Symptom | Cause / fix |
|---|---|
| `404` on a Notion data-source query | Wrong/stale `NOTION_*_DS_ID`, or the integration isn't shared with the DB. Re-run `scripts/notion_ids.py`; check Step 6.3. |
| Host names appear as entities | Add every spelling to `host_ban_keys` (lowercase, all scripts). |
| A guest's name is mangled / a brand is wrong | Add it to `stt_additional_vocab` and re-run (delete the cached transcript for that episode to re-transcribe). |
| "no episodes" / wrong newest episode | You gave a Spotify web link, not RSS (Step 2), or a CDN served a stale feed — the engine cache-busts, but double-check `feed_rss_url`. |
| Pipeline reads yesterday's episode as newest | Podcast CDNs serve stale feeds for a while after publish; wait, or pass `--episode` explicitly. |

When you're set up, the whole weekly loop is one command (or one cron): new episode →
transcript → entities → Notion → optional approval tap → channel.
