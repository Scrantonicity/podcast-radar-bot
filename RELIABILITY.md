# Reliable weekly trigger — external scheduler setup

## Why

GitHub `schedule:` cron is **best-effort** — it silently drops/throttles scheduled fires
under load. In production this dropped a Friday pipeline run entirely and an episode was
never auto-processed. It is fine to start on GitHub cron, but once the pipeline matters,
move the trigger off it:

- Trigger the pipeline from an **external scheduler → GitHub `workflow_dispatch`**
  (dispatch events are NOT throttled). The example below uses GCP Cloud Scheduler; any
  scheduler that can POST to the GitHub API works (cron on a VPS, Lambda, etc.).
- Keep a **dead-man alert** (`watchdog.py` + `watchdog.yml`) as the backstop — it pings
  your private chat if the episode wasn't processed in time.
- Drive the approval **poller** densely during your publish window so an Approve tap
  releases in seconds instead of up to an hour.

A scheduler with real timezone support (`--time-zone=...`) also handles DST for you — no
UTC/DST cron math.

**Guards that make extra/duplicate triggers safe:** `concurrency: cancel-in-progress: false`
(runs never overlap) plus the reprocess safeguard in `auto_review.py` (skip-if-already-in-Notion
*before* any paid call). A double-fire costs one Notion read — no duplicate transcription,
extraction, or post.

Replace throughout: `<OWNER>/<REPO>`, `<PROJECT_ID>`, `<REGION>`, `<TZ>`, and the cron
expressions (match them to when your show publishes).

## One-time prerequisites

```bash
gcloud auth login
gcloud config set project <PROJECT_ID>
gcloud services enable cloudscheduler.googleapis.com
```

Pick a region once and use the same `--location` on every job.

### GitHub credential

Create a **fine-grained PAT**: repo `<OWNER>/<REPO>`, permission **Actions: Read and write**.
Fine-grained PATs expire (≤1 yr) — set a reminder to rotate, or use a GitHub App for
no-expiry. The token lives only in the scheduler job headers (encrypted at rest).

Shared header string (GitHub 403s without a `User-Agent`):

```bash
HDR='Authorization=Bearer <PAT>,Accept=application/vnd.github+json,X-GitHub-Api-Version=2022-11-28,User-Agent=podcast-radar-scheduler,Content-Type=application/json'
BASE='https://api.github.com/repos/<OWNER>/<REPO>/actions/workflows'
```

## Jobs

All jobs: `--time-zone="<TZ>"`, `--location=<REGION>`, `--http-method=POST`, `--headers="$HDR"`.

### 1–2. Pipeline trigger — two attempts

Two fires; the 2nd is a cheap Notion-read no-op if the 1st already processed. Schedule the
first comfortably after your episode publishes.

```bash
gcloud scheduler jobs create http podcast-radar-pipeline-1 \
  --location=<REGION> --time-zone="<TZ>" --schedule="30 8 * * 5" \
  --uri="$BASE/pipeline.yml/dispatches" --http-method=POST --headers="$HDR" \
  --message-body='{"ref":"main","inputs":{"mode":"auto","episode":"1"}}'

gcloud scheduler jobs create http podcast-radar-pipeline-2 \
  --location=<REGION> --time-zone="<TZ>" --schedule="30 9 * * 5" \
  --uri="$BASE/pipeline.yml/dispatches" --http-method=POST --headers="$HDR" \
  --message-body='{"ref":"main","inputs":{"mode":"auto","episode":"1"}}'
```

### 3. Fast approval release — every 5 min during the publish window

So your Approve tap posts to the channel within ~5 min rather than up to an hour. Safe: the
poller's concurrency group serializes runs and it stays a single `getUpdates` consumer.

```bash
gcloud scheduler jobs create http podcast-radar-poller \
  --location=<REGION> --time-zone="<TZ>" --schedule="*/5 8-12 * * 5" \
  --uri="$BASE/approve_poll.yml/dispatches" --http-method=POST --headers="$HDR" \
  --message-body='{"ref":"main"}'
```

### 4. Dead-man alert

Pings the private alert chat if this week's episode still isn't processed (i.e. the trigger
missed). Silent otherwise.

```bash
gcloud scheduler jobs create http podcast-radar-watchdog \
  --location=<REGION> --time-zone="<TZ>" --schedule="0 12 * * 5" \
  --uri="$BASE/watchdog.yml/dispatches" --http-method=POST --headers="$HDR" \
  --message-body='{"ref":"main"}'
```

## Verify (before disabling the GitHub schedule)

```bash
gcloud scheduler jobs run podcast-radar-pipeline-1 --location=<REGION>
```

Within seconds a `mode=auto` run should appear under Actions, triggered by
`workflow_dispatch`. Then:

- Confirm the private Approve message arrives; run the poller job and confirm the tap
  releases to your channel.
- Run the watchdog job BEFORE this week's episode is processed → confirm the Telegram alert
  fires; confirm it's silent once the episode is processed.
- Check each job's next-run wall-clock is the intended local time
  (`gcloud scheduler jobs describe <name> --location=<REGION>`).

## Last step — retire the GitHub schedule (only after the above works)

In `.github/workflows/pipeline.yml`, delete the `schedule:` block and the
`if [ "${{ github.event_name }}" = "schedule" ]` branch. Keep `workflow_dispatch`. The
external scheduler now owns scheduling: one trigger source, no double-fire. (Optional: drop
`schedule:` from `approve_poll.yml` too, since job #3 drives it — leaving it as an everyday
backup is harmless.)
