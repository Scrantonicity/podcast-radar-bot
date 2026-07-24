# Deploy — podcast-radar-bot weekly pipeline on a DigitalOcean VPS

The VPS only runs the **weekly delta** (`python main.py` with no flags → processes
episodes not already done in Notion). The one-time full backfill runs locally, not here.

## 1. Copy the project to the VPS

From your Mac (project root):

```bash
# pick a stable location, e.g. /opt/podcast-radar-bot
rsync -av --exclude venv --exclude transcripts --exclude extractions \
  --exclude '*.mp3' --exclude out_*.txt \
  ./ youruser@YOUR_VPS:/opt/podcast-radar-bot/
```

You need: `*.py`, `requirements.txt`, `.env`, `deploy/`. The backfill caches
(`transcripts/`, `extractions/`) are NOT needed — the weekly run only touches new episodes.

## 2. Install

```bash
ssh youruser@YOUR_VPS
cd /opt/podcast-radar-bot
sudo apt update && sudo apt install -y python3 python3-venv
bash deploy/setup.sh
```

Make sure `.env` is filled in: `NOTION_TOKEN`, the Notion DB/DS ids,
`SPEECHMATICS_API_KEY`, `GOOGLE_API_KEY`, `TELEGRAM_BOT_TOKEN`, and
`TELEGRAM_CHAT_ID` = your channel (`@name` or `-100…`). The bot must be a channel admin.

## 3. Verify Telegram

```bash
./venv/bin/python telegram_check.py
```

Expect `PASS ✅` and a test message in the channel.

## 4. Install the timer (Friday 09:00 Asia/Jerusalem)

```bash
sudo cp deploy/podcast-radar.service deploy/podcast-radar.timer /etc/systemd/system/
# if the project isn't at /opt/podcast-radar-bot, edit the paths in podcast-radar.service first
sudo systemctl daemon-reload
sudo systemctl enable --now podcast-radar.timer
systemctl list-timers podcast-radar.timer        # shows the next Friday 09:00 run
```

Test a run now (processes only new episodes):

```bash
sudo systemctl start podcast-radar.service
journalctl -u podcast-radar.service -n 50 --no-pager
```

### Cron fallback (if you prefer cron over systemd)

```cron
# /etc/crontab  — Friday 09:00 Israel time
0 9 * * 5  youruser  cd /opt/podcast-radar-bot && TZ=Asia/Jerusalem ./venv/bin/python main.py >> /var/log/podcast-radar.log 2>&1
```

> Note: plain cron uses the system timezone. Either set the server timezone to
> Asia/Jerusalem (`sudo timedatectl set-timezone Asia/Jerusalem`) or keep the
> `TZ=` prefix and accept that `* * * * 5` fires at 09:00 *server* time — the
> systemd timer with `Asia/Jerusalem` in `OnCalendar` is the robust option.
