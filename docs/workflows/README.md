# Parked production workflows

These three GitHub Actions workflows are the **reference deployment** for a live show. They
are parked here rather than in `.github/workflows/` because this repository is the public
blueprint — it holds no API keys, so every run of a credentialed workflow would fail. GitHub
only schedules and dispatches workflows that live in `.github/workflows/` on the default
branch, so parking them keeps the Actions tab green and quiet.

The two workflows that *do* run here — `tests` and `observatory` — need no credentials and
stay in [`.github/workflows/`](../../.github/workflows/).

| File | What it does | Trigger |
|---|---|---|
| `pipeline.yml` | The weekly run: RSS → STT → extraction → Notion, then an approval-gated digest. Modes: `auto` / `latest` / `episode` / `preview`. | Friday cron + `workflow_dispatch` |
| `approve_poll.yml` | Releases an approved private preview to the channel when you tap Approve (`getUpdates` → `copyMessage`). | 5-minute cron + `workflow_dispatch` |
| `watchdog.yml` | Dead-man alert: pings your private chat if the week's episode wasn't processed. Silent otherwise. | `workflow_dispatch` (external scheduler) |

## Activating them

```bash
cp docs/workflows/*.yml .github/workflows/
git add .github/workflows && git commit -m "ci: enable production workflows" && git push
```

Then set them up in your fork under **Settings → Secrets and variables → Actions**:

**Secrets**

```
SPEECHMATICS_API_KEY     GOOGLE_API_KEY
NOTION_TOKEN             NOTION_EPISODES_DB_ID   NOTION_ENTITIES_DB_ID
                         NOTION_EPISODES_DS_ID   NOTION_ENTITIES_DS_ID
TELEGRAM_BOT_TOKEN       TELEGRAM_CHAT_ID        TELEGRAM_ALERT_CHAT_ID
TELEGRAM_APPROVER_ID
```

**Variables**

```
SHOW                     # e.g. demo — selects shows/<SHOW>/
EXTRACTION_MODEL         # optional; defaults to gemini-2.5-flash
```

Each of these is documented in [`.env.example`](../../.env.example); the workflows read the
same names from the Actions context that `config.py` reads from `.env` locally.

Two things that bite if you skip them:

- **`approve_poll.yml` requires that NO Telegram webhook is set** — it is a `getUpdates`
  consumer, and the two are mutually exclusive.
- **`TELEGRAM_APPROVER_ID` unset means nothing is ever auto-posted.** That is the fail-safe,
  not a bug.

## They must be in `.github/workflows/` to be dispatchable

[RELIABILITY.md](../../RELIABILITY.md) sets up an external scheduler that POSTs to

```
/repos/<OWNER>/<REPO>/actions/workflows/pipeline.yml/dispatches
```

That endpoint resolves a workflow by its path under `.github/workflows/` on the default
branch. Until you run the `cp` above, those calls return 404 — copy the files in first, then
wire up the scheduler.
