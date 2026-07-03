"""Central config: loads .env and exposes settings for the Notion bridge + notifier."""

import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name, default=False):
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# Notion
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_EPISODES_DB_ID = os.getenv("NOTION_EPISODES_DB_ID")
NOTION_ENTITIES_DB_ID = os.getenv("NOTION_ENTITIES_DB_ID")
NOTION_EPISODES_DS_ID = os.getenv("NOTION_EPISODES_DS_ID")
NOTION_ENTITIES_DS_ID = os.getenv("NOTION_ENTITIES_DS_ID")

# Notion API version verified against live docs (data-source-centric API).
NOTION_VERSION = "2026-03-11"

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ENABLE_TELEGRAM = _bool("ENABLE_TELEGRAM", False)

# Private failure alerts — separate chat, separate flag. Independent of the
# channel broadcast above (alerts fire even when ENABLE_TELEGRAM is off).
TELEGRAM_ALERT_CHAT_ID = os.getenv("TELEGRAM_ALERT_CHAT_ID")
ENABLE_ALERTS = _bool("ENABLE_ALERTS", False)

# Numeric Telegram user id allowed to approve channel posts via the inline button.
# The approval poller refuses to release anything to the channel unless a callback
# comes from this id (fail-safe: unset => no auto-post).
TELEGRAM_APPROVER_ID = os.getenv("TELEGRAM_APPROVER_ID")

# Email (Resend) — scaffold, disabled by default
ENABLE_EMAIL = _bool("ENABLE_EMAIL", False)
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")

# Extraction LLM — SINGLE SOURCE OF TRUTH for the model id. Every stage that
# extracts (extract.py, auto_review.py, the pipeline) reads this one value so a
# model change can't half-apply. friday_preview.py is the one exception: it
# deliberately sweeps an explicit multi-model list to compare candidates.
EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL", "gemini-2.5-flash")
