"""Notifications: Telegram (active) + email via Resend (scaffold, disabled).

The Telegram message is a DECISION TRIGGER ("what's worth exploring after a
drive?"), not a summary — the full summary lives in Notion. It curates a small
ranked set of the most notable entities, grouped into a few merged sections with
one icon each (minimalist Gemini-style skeleton). No links to Notion.
"""

import datetime
import html
import re
import time

import requests

import config
from show_loader import SHOW, STRINGS

TELEGRAM_LIMIT = 4096

# Public link to the full entity database, appended to every message.
DB_LINK = SHOW.db_link

_preflight_done = False  # run the channel access check once per process

# Merged sections in display order — ONE icon per section (from the show config).
# Types not surfaced here stay in Notion only. Types are LOWERCASE to match the
# extraction contract. Cast the config's tuples to lists for the render code.
TG_SECTIONS = [{"heading": s["heading"], "types": list(s["types"])} for s in SHOW.tg_sections]
TG_SURFACED = {t for s in TG_SECTIONS for t in s["types"]}
READING_TYPES = set(SHOW.reading_types)      # <a href> names allowed here only
SENTIMENT_TYPES = set(SHOW.sentiment_types)  # 📈/📉 + ticker shown here only
TG_TYPE_CAP = dict(SHOW.tg_type_caps)
TG_GLOBAL_CAP = SHOW.tg_global_cap
# When over the global cap, trim from least-priority types first.
TG_TRIM_ORDER = list(SHOW.tg_trim_order)


# --------------------------------------------------------------------------
# RTL/LTR directionality. For an RTL show, Telegram's full Unicode bidi can
# scramble a Latin/number run inside an RTL line (ticker, English name, date) —
# parentheses and tickers flip. Wrap each such run in a First-Strong Isolate
# (U+2068 … U+2069) so it keeps its own direction. For an LTR show this is a
# no-op. Gated on SHOW.text_direction.
# --------------------------------------------------------------------------
_RTL = SHOW.text_direction == "rtl"
_LATIN_RE = re.compile(r"[A-Za-z0-9]")


def _iso(s):
    """Wrap in a Unicode First-Strong Isolate (RTL shows only; no-op for LTR)."""
    return f"⁨{s}⁩" if _RTL else s


def _wrap_if_latin(s):
    """Isolate mixed/Latin runs inside RTL text; no-op for LTR shows."""
    return _iso(s) if (_RTL and _LATIN_RE.search(s)) else s


# --------------------------------------------------------------------------
# Ranking + segment helpers
# --------------------------------------------------------------------------
def _notability(e):
    n = e.get("notability")
    return n if isinstance(n, (int, float)) else 0


def _rank_key(e, idx):
    """Sort key (descending) for ranking entities: notability, then link, ticker,
    context length; idx keeps it stable (ascending) as the final tiebreak."""
    return (-_notability(e), 0 if e.get("link") else 1,
            0 if e.get("ticker") else 1, -len(e.get("context") or ""), idx)


def _name_html(e, linkable=False):
    """Bold name, or an anchor when linkable (reading section) and a real link
    exists. The visible name text is isolate-wrapped if it contains Latin/digits."""
    name = _wrap_if_latin(html.escape(str(e.get("name", ""))))
    link = e.get("link")
    if linkable and link:
        return f'<a href="{html.escape(str(link))}">{name}</a>'
    return f"<b>{name}</b>"


def _ticker_seg(e):
    """' (TICKER)' isolated so the parens don't flip, or '' when no ticker."""
    t = e.get("ticker")
    return f" {_iso(f'({html.escape(str(t))})')}" if t else ""


def _sentiment_seg(e):
    """📈/📉 by the host's stance; nothing for neutral/missing."""
    s = e.get("sentiment")
    if s == "positive":
        return " 📈"
    if s == "negative":
        return " 📉"
    return ""


def _returning_seg(e):
    """' 🔁 פרק N' (N isolated) when the entity recurred from an earlier episode;
    bare ' 🔁' if is_returning but the earliest episode number is unknown."""
    if not e.get("is_returning"):
        return ""
    ep = e.get("earliest_episode")
    return f" 🔁 {STRINGS.tg_returning_word} {_iso(str(ep))}" if ep else " 🔁"


def _attr_seg(e, show_attr):
    if not show_attr:
        return ""
    by = html.escape(", ".join(e.get("mentioned_by") or []))
    return f" ({by})" if by else ""


def _raw_context(e):
    return str(e.get("context") or e.get("one_liner") or "")


def _strip_leading_name(name, ctx):
    """Drop a leading repetition of the entity name from the context so the name
    isn't shown twice (the bold name already precedes the context). Also handles the
    name behind any of the show's article prefixes (e.g. Hebrew "ה"). If the context
    is ONLY the name, leave it untouched."""
    if not name or not ctx:
        return ctx
    c = ctx.lstrip()
    candidates = [name] + [p + name for p in SHOW.name_article_prefixes]
    for cand in candidates:
        if c.startswith(cand):
            rest = c[len(cand):].lstrip(" \t⁨⁩—–-:,.|")
            return rest or ctx
    return ctx


def _context_html(e):
    """Escaped context with any leading entity-name repetition stripped."""
    return html.escape(_strip_leading_name(str(e.get("name", "")), _raw_context(e)))


def _bullet(e, show_attr):
    """One entity bullet, eligibility driven by the entity's own type:
    • <name>{ (TICKER)}{ 📈/📉} | {context}{ (attr)}{ 🔁}
    (ticker/sentiment only for stock/company; link only for reading, which also
    shows no attribution.)"""
    t = e.get("type")
    linkable = t in READING_TYPES
    name = _name_html(e, linkable=linkable)
    ticker = _ticker_seg(e) if t in SENTIMENT_TYPES else ""
    sent = _sentiment_seg(e) if t in SENTIMENT_TYPES else ""
    ctx = _context_html(e)
    body = f" | {ctx}" if ctx else ""
    attr = "" if linkable else _attr_seg(e, show_attr)
    return f"• {name}{ticker}{sent}{body}{attr}{_returning_seg(e)}"


def _deepdive_line(e, show_attr):
    """{deepdive_label} <b>{top}</b>{ (TICKER)} | {context}{ (attr)}
    (no sentiment icon, no returning marker — kept lean.)"""
    name = _name_html(e, linkable=False)
    ctx = _context_html(e)
    body = f" | {ctx}" if ctx else ""
    return f"{STRINGS.tg_deepdive_label} {name}{_ticker_seg(e)}{body}{_attr_seg(e, show_attr)}"


def _fmt_date(date):
    """ISO YYYY-MM-DD -> the show's date_format (strftime). Pass through anything
    that isn't a parseable ISO date."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", str(date or ""))
    if not m:
        return date or ""
    try:
        d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return d.strftime(SHOW.date_format)
    except ValueError:
        return date or ""


def _header(episode):
    """Single header line: {prefix} | {episode_word} {N}: {headline} ({date}). The
    number and the date parenthetical are isolated (RTL) so they don't flip."""
    num = episode.get("number")
    date = _fmt_date(episode.get("date"))
    headline = (episode.get("headline") or "").strip()
    seg = ""
    if num is not None:
        seg = f"{STRINGS.tg_episode_word} {_iso(str(num))}"
    if headline:
        h = html.escape(headline)
        seg = f"{seg}: {h}" if seg else h
    if date:
        seg = f"{seg} {_iso(f'({date})')}" if seg else _iso(f"({date})")
    return f"{STRINGS.tg_header_prefix} | {seg}" if seg else STRINGS.tg_header_prefix


def _platform_footer(episode):
    """🔗 line of platform links; omit missing platforms, omit line if none. The
    LTR link group is isolate-wrapped so it doesn't reorder inside the Hebrew line."""
    links = []
    for url, label in ((episode.get("youtube_url"), "YouTube"),
                       (episode.get("spotify_url"), "Spotify"),
                       (episode.get("apple_url"), "Apple")):
        if url:
            links.append(f'<a href="{html.escape(str(url))}">{label}</a>')
    return (STRINGS.tg_listen_label + _iso(" · ".join(links))) if links else None


def build_telegram_message(episode, entities, episode_url=None):
    """Curated, ranked digest in the minimalist section layout. Ranks by per-entity
    notability; one 🔥 Deep Dive pick chosen BEFORE caps; merged sections; platform
    + DB footers. episode_url is ignored on purpose (no Notion link in the body)."""
    header = _header(episode)

    # Surfaced entities (section types only; place/other never shown), carrying the
    # original index for a stable tiebreak.
    surfaced = [(i, e) for i, e in enumerate(entities) if e.get("type") in TG_SURFACED]

    # 🔥 pick: highest-notability surfaced entity, chosen from the FULL list BEFORE
    # any caps so capping can never drop the true winner.
    rec = None
    if surfaced:
        _, rec = min(surfaced, key=lambda ie: _rank_key(ie[1], ie[0]))

    # Group the REST by type, rank by notability desc, apply per-type caps. Keep
    # (idx, e) tuples so merged sections re-sort stably.
    by_type = {}
    for t in TG_SURFACED:
        grp = [(i, e) for i, e in surfaced if e.get("type") == t and e is not rec]
        grp.sort(key=lambda ie: _rank_key(ie[1], ie[0]))
        by_type[t] = grp[:TG_TYPE_CAP[t]]

    def total():
        return sum(len(v) for v in by_type.values())

    # Global cap: drop the lowest-notability bullet from the least-priority type
    # that still has bullets, repeat. (Lists are notability-desc, so pop() = lowest.)
    while total() > TG_GLOBAL_CAP:
        for t in TG_TRIM_ORDER:
            if by_type.get(t):
                by_type[t].pop()
                break
        else:
            break

    msg = _render(header, episode, by_type, rec, len(entities))

    # Telegram hard limit: drop the globally lowest-notability bullet until it fits.
    while len(msg) > TELEGRAM_LIMIT and total() > 0:
        worst_t = min((t for t in TG_SURFACED if by_type.get(t)),
                      key=lambda t: _notability(by_type[t][-1][1]))
        by_type[worst_t].pop()
        msg = _render(header, episode, by_type, rec, len(entities))
    return msg[:TELEGRAM_LIMIT]


def _render(header, episode, by_type, rec, total_entities):
    # Attribution toggle: distinct speakers across the FINAL SHOWN entities. ≤1
    # distinct (incl. the diarization-gate's blanked mentioned_by) -> drop it
    # everywhere; ≥2 -> show. Reading bullets never show attribution regardless.
    shown_ents = ([rec] if rec is not None else []) + \
        [e for v in by_type.values() for _i, e in v]
    distinct = set()
    for e in shown_ents:
        distinct.update(e.get("mentioned_by") or [])
    show_attr = len(distinct) >= 2

    parts = [header]

    if rec is not None:
        parts.append("")
        parts.append(_deepdive_line(rec, show_attr))

    shown = 1 if rec is not None else 0
    for sec in TG_SECTIONS:
        bullets = []
        for t in sec["types"]:
            bullets.extend(by_type.get(t) or [])
        if not bullets:
            continue
        bullets.sort(key=lambda ie: _rank_key(ie[1], ie[0]))
        parts.append("")
        parts.append(sec["heading"])
        for _i, e in bullets:
            parts.append(_bullet(e, show_attr))
            shown += 1

    if shown == 0:
        parts.append("")
        parts.append(STRINGS.tg_empty_state)

    # Footer 1: platform links.
    plat = _platform_footer(episode)
    if plat:
        parts.append("")
        parts.append(plat)

    # Footer 2: DB link, with a "+K more" note only when K > 0 (never "+0"/negative).
    k = total_entities - shown
    parts.append("")
    if k > 0:
        parts.append(STRINGS.tg_db_more.format(k=k, link=DB_LINK))
    else:
        parts.append(STRINGS.tg_db_all.format(link=DB_LINK))
    return "\n".join(parts)


def _api_url(method):
    return f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}"


def preflight_channel():
    """Confirm the bot can see the target channel before broadcasting. The #1
    failure when posting to a channel is the bot not being an admin — surface a
    clear, actionable message instead of a raw 400."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in .env")
    try:
        r = requests.get(_api_url("getChat"),
                         params={"chat_id": config.TELEGRAM_CHAT_ID}, timeout=30)
        body = r.json()
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Telegram getChat request failed: {e}") from e
    if not body.get("ok"):
        desc = body.get("description", "unknown error")
        raise RuntimeError(
            f"Bot can't access the channel ({desc}). Add the bot to the channel "
            "AS AN ADMIN with 'Post Messages' permission, and check that "
            "TELEGRAM_CHAT_ID is correct (@username for public, -100… id for private)."
        )
    return body["result"]


def send_telegram(message, disable_notification=False, allow_public=False):
    """Post directly to the PUBLIC channel (TELEGRAM_CHAT_ID).

    GUARDRAIL (approval-gate invariant): this posts to the public channel, so it is
    FAIL-CLOSED — a caller must pass allow_public=True to prove the public post is
    intentional. The safe default path to the channel is send_approval_request()
    (private draft) + the approval poller's tap. Only the deliberate direct-broadcast
    dispatch (notify.notify) and explicitly human-confirmed tools (approve.py behind
    --confirm-channel, rebroadcast.py) pass allow_public=True. This exists because a
    one-off script once called send_telegram() and posted straight to the channel with
    no review — routing was by which function you call, not an explicit gate.
    """
    if not allow_public:
        raise RuntimeError(
            "send_telegram() posts to the PUBLIC channel and is fail-closed. Use "
            "send_approval_request() for the review path, or pass allow_public=True "
            "only from a deliberate, human-confirmed broadcast."
        )
    global _preflight_done
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")
    if not _preflight_done:
        preflight_channel()
        _preflight_done = True

    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": message[:TELEGRAM_LIMIT],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": disable_notification,
    }
    for attempt in range(2):
        r = requests.post(_api_url("sendMessage"), json=payload, timeout=30)
        try:
            body = r.json()
        except ValueError:
            body = {}
        if body.get("ok"):
            return body
        # 429: honor Telegram's retry_after, then retry once.
        if r.status_code == 429 and attempt == 0:
            retry_after = (body.get("parameters") or {}).get("retry_after", 3)
            time.sleep(retry_after + 1)
            continue
        desc = body.get("description") or r.text
        raise RuntimeError(f"Telegram send failed ({r.status_code}): {desc}")
    raise RuntimeError("Telegram send failed after retry")


def send_alert(text):
    """Send a failure alert to the PRIVATE alert chat (TELEGRAM_ALERT_CHAT_ID).

    Independent of ENABLE_TELEGRAM and of the public channel — gated ONLY by
    ENABLE_ALERTS, and goes to a different chat. No-op (returns None) when alerts
    are disabled or no alert chat is configured. NEVER raises into the caller: an
    alert failure must not crash the pipeline or mask the original error — it logs
    a warning and returns None instead.
    """
    if not config.ENABLE_ALERTS or not config.TELEGRAM_ALERT_CHAT_ID:
        return None
    if not config.TELEGRAM_BOT_TOKEN:
        print("  [warn] send_alert: TELEGRAM_BOT_TOKEN not set")
        return None
    payload = {
        "chat_id": config.TELEGRAM_ALERT_CHAT_ID,
        "text": text[:TELEGRAM_LIMIT],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(_api_url("sendMessage"), json=payload, timeout=30)
        body = r.json() if r.content else {}
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] alert send error: {e}")
        return None
    if not body.get("ok"):
        desc = body.get("description") or r.text
        print(f"  [warn] alert send failed ({r.status_code}): {desc}")
        return None
    return body


# --------------------------------------------------------------------------
# Approval flow: send the channel digest to the PRIVATE chat with inline
# Approve/Reject buttons; a poller (approval_poller.py) reacts to the tap and
# copies the approved message to the channel. These are thin Bot API wrappers.
# --------------------------------------------------------------------------
def _tg_api(method, payload, http_get=False):
    """Call a Telegram Bot API method. Returns the parsed body dict (ok-checked).
    One retry on 429 honoring retry_after. Raises RuntimeError on hard failure."""
    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    for attempt in range(2):
        if http_get:
            r = requests.get(_api_url(method), params=payload, timeout=60)
        else:
            r = requests.post(_api_url(method), json=payload, timeout=30)
        try:
            body = r.json()
        except ValueError:
            body = {}
        if body.get("ok"):
            return body
        if r.status_code == 429 and attempt == 0:
            retry_after = (body.get("parameters") or {}).get("retry_after", 3)
            time.sleep(retry_after + 1)
            continue
        desc = body.get("description") or r.text
        raise RuntimeError(f"Telegram {method} failed ({r.status_code}): {desc}")
    raise RuntimeError(f"Telegram {method} failed after retry")


def _approval_markup(guid):
    return {"inline_keyboard": [[
        {"text": STRINGS.approve_btn, "callback_data": f"approve:{guid}"},
        {"text": STRINGS.reject_btn, "callback_data": f"reject:{guid}"},
    ]]}


def send_approval_request(message, guid, chat_id=None):
    """Post the channel digest to the PRIVATE chat with Approve/Reject buttons.
    Returns the Telegram message result (includes message_id). guid (36 chars)
    fits the 64-byte callback_data limit."""
    chat_id = chat_id or config.TELEGRAM_ALERT_CHAT_ID
    if not chat_id:
        raise RuntimeError("TELEGRAM_ALERT_CHAT_ID (private chat) not set")
    payload = {
        "chat_id": chat_id,
        "text": message[:TELEGRAM_LIMIT],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": _approval_markup(guid),
    }
    return _tg_api("sendMessage", payload)["result"]


def copy_message(to_chat_id, from_chat_id, message_id):
    """copyMessage: reproduce a message's content (text + formatting) into another
    chat WITHOUT its inline buttons — used to release an approved preview to the
    channel byte-clean."""
    return _tg_api("copyMessage", {
        "chat_id": to_chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id,
    })["result"]


def answer_callback(callback_query_id, text=""):
    """Best-effort toast ack. answerCallbackQuery expires within seconds, so on a
    polled approval the query is usually 'too old' — that's harmless (the real release
    uses chat_id+message_id), so never let it crash the poller."""
    try:
        return _tg_api("answerCallbackQuery",
                       {"callback_query_id": callback_query_id, "text": text})
    except Exception as e:  # noqa: BLE001
        print(f"  [answer_callback ignored] {e}")
        return None


def edit_message_text(chat_id, message_id, text):
    """Replace a message's text and drop its buttons (markup omitted = cleared)."""
    return _tg_api("editMessageText", {
        "chat_id": chat_id, "message_id": message_id,
        "text": text[:TELEGRAM_LIMIT], "parse_mode": "HTML",
        "disable_web_page_preview": True,
    })


def get_updates(offset=None, timeout=0):
    """getUpdates (callback_query allowed). Pass offset=last_update_id+1 to ack."""
    payload = {"timeout": timeout, "allowed_updates": ["callback_query"]}
    if offset is not None:
        payload["offset"] = offset
    return _tg_api("getUpdates", payload, http_get=True).get("result", [])


def send_email(subject, body_html):
    """Scaffold via Resend. Disabled unless ENABLE_EMAIL and RESEND_API_KEY set."""
    if not config.RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY not set")
    r = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {config.RESEND_API_KEY}"},
        json={
            "from": config.EMAIL_FROM,
            "to": [config.EMAIL_TO],
            "subject": subject,
            "html": body_html,
        },
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"Resend failed {r.status_code}: {r.text}")
    return r.json()


def notify(episode, entities, episode_url):
    """Dispatch notifications based on enable flags. Returns dict of results."""
    results = {}
    if config.ENABLE_TELEGRAM:
        msg = build_telegram_message(episode, entities, episode_url)
        # Deliberate direct-broadcast dispatch (the unattended main.py path). The
        # approval-gated path never calls notify.notify — it drafts privately instead.
        results["telegram"] = send_telegram(msg, allow_public=True)
    if config.ENABLE_EMAIL:
        num = episode.get("number", "?")
        subject = STRINGS.email_subject_template.format(
            show=SHOW.display_name, episode_word=STRINGS.tg_episode_word, num=num)
        body = STRINGS.email_body_template.format(n=len(entities))
        if episode_url:
            body += f'<p><a href="{html.escape(episode_url)}">{STRINGS.email_open_notion}</a></p>'
        results["email"] = send_email(subject, body)
    return results
