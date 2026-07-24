"""Notion bridge: writes the extraction contract into the Episodes + Entities DBs.

NOTE: filename is notion_bridge.py (not notion_client.py) on purpose — a module
named notion_client.py would shadow the official `notion-client` SDK package and
break `from notion_client import Client`. Same public entry point: process_episode().

Targets the data-source-centric Notion API (Notion-Version 2026-03-11): pages are
parented on data_source_id, queries hit POST /v1/data_sources/{id}/query. Verified
against live docs.
"""

import time
import urllib.parse

from notion_client import Client
from notion_client.errors import APIResponseError

import config
import notify
from show_loader import SHOW, STRINGS

# ---- shared host options for "Recommended by" multi_select (from the show) ----
HOSTS = set(SHOW.mentioned_by_enum)

# Notion rate limit ~3 req/s; keep a small gap + backoff on 429.
WRITE_DELAY = 0.34
MAX_RETRIES = 5

# Notion url-property hard cap (values longer than this 400 with a ValidationError).
NOTION_URL_MAX = 2000


def cap_url(url, limit=NOTION_URL_MAX):
    """GUARDRAIL: Notion url-property values must be <= 2000 chars or pages.update
    400s. Any url written to a Notion url property must pass through here. Callers
    that can shorten meaningfully (e.g. _learn_url trimming context) should do so
    first; this is the final backstop that hard-truncates."""
    return url if url is None or len(url) <= limit else url[:limit]


def trash_page(client, page_id):
    """GUARDRAIL: trash a Notion page. This API version (2026-03-11) uses
    in_trash=True; the older archived=True is rejected ('body.archived should be not
    present'). Trashed pages are recoverable from Notion trash for 30 days."""
    return _retry(client.pages.update, page_id=page_id, in_trash=True)


def update_select_options(client, ds_id, prop_name, ensure_names, colors=None):
    """GUARDRAIL: safely ensure select/multi_select options WITHOUT dropping any.

    data_sources.update REPLACES the entire options list — omit an existing option
    and Notion deletes it and strips its value from every row (associations lost, not
    recoverable). So we ALWAYS retrieve the current full options first and merge the
    new names in, preserving existing ids + colors. Renaming an existing option is
    intentionally NOT done here (the API applies it flakily and it risks the wipe);
    to rename, add-new + migrate rows + remove-old.
    """
    ds = _retry(client.data_sources.retrieve, data_source_id=ds_id)
    prop = (ds.get("properties") or {}).get(prop_name)
    if not prop:
        raise RuntimeError(f"data source has no property {prop_name!r}")
    kind = prop["type"]  # "select" | "multi_select"
    current = prop[kind].get("options", [])
    merged = [dict(o) for o in current]           # keep ids + colors intact
    have = {o["name"] for o in current}
    colors = colors or {}
    for name in ensure_names:
        if name not in have:
            merged.append({"name": name, "color": colors.get(name, "default")})
    _retry(client.data_sources.update, data_source_id=ds_id,
           properties={prop_name: {kind: {"options": merged}}})
    return merged


def _client():
    if not config.NOTION_TOKEN:
        raise RuntimeError("NOTION_TOKEN not set in .env")
    return Client(auth=config.NOTION_TOKEN, notion_version=config.NOTION_VERSION)


def _retry(fn, *args, **kwargs):
    """Call a Notion SDK method with backoff on 429 / transient errors."""
    delay = 1.0
    for attempt in range(MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except APIResponseError as e:
            if e.code == "rate_limited" or getattr(e, "status", None) == 429:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    return fn(*args, **kwargs)


# --------------------------------------------------------------------------
# Small property/text helpers
# --------------------------------------------------------------------------
def _rt(text):
    return [{"type": "text", "text": {"content": (text or "")[:2000]}}] if text else []


def _plain(prop):
    """Extract plain string from a rich_text / title property value."""
    if not prop:
        return ""
    arr = prop.get("rich_text") or prop.get("title") or []
    return "".join(p.get("plain_text", "") for p in arr)


# --------------------------------------------------------------------------
# Schema fix: convert "Recommended by" select -> multi_select
# --------------------------------------------------------------------------
def ensure_recommended_by_multiselect(client=None):
    """Convert Entities "Recommended by" to multi_select if it is still select.

    Returns one of: "already", "converted", or raises with a clear message if
    the API rejects the in-place conversion (then the user does it in the UI).
    """
    client = client or _client()
    ds = _retry(client.data_sources.retrieve, data_source_id=config.NOTION_ENTITIES_DS_ID)
    prop = ds["properties"].get("Recommended by")
    if prop is None:
        raise RuntimeError('Entities DB has no "Recommended by" property')
    if prop["type"] == "multi_select":
        return "already"
    if prop["type"] != "select":
        raise RuntimeError(f'"Recommended by" is {prop["type"]}, expected select/multi_select')

    # Preserve existing options when converting.
    options = prop["select"].get("options", [])
    keep = [{"name": o["name"], "color": o.get("color", "default")} for o in options]
    for h in HOSTS:
        if not any(o["name"] == h for o in keep):
            keep.append({"name": h, "color": "default"})
    try:
        _retry(
            client.data_sources.update,
            data_source_id=config.NOTION_ENTITIES_DS_ID,
            properties={"Recommended by": {"multi_select": {"options": keep}}},
        )
    except APIResponseError as e:
        raise RuntimeError(
            "API rejected select->multi_select conversion: "
            f"{e}. Change it in the Notion UI (Select -> Multi-select; options "
            "are preserved), then re-run."
        )
    return "converted"


def ensure_context_property(client=None):
    """Add a "Context" rich_text property to the Entities DB if missing.

    Returns "already" or "added". Raises with a UI-fallback message if the API
    rejects the add.
    """
    client = client or _client()
    ds = _retry(client.data_sources.retrieve, data_source_id=config.NOTION_ENTITIES_DS_ID)
    if "Context" in (ds.get("properties") or {}):
        return "already"
    try:
        _retry(
            client.data_sources.update,
            data_source_id=config.NOTION_ENTITIES_DS_ID,
            properties={"Context": {"rich_text": {}}},
        )
    except APIResponseError as e:
        raise RuntimeError(
            f"API rejected adding Context property: {e}. Add a Text property named "
            '"Context" to the Entities DB in the Notion UI, then re-run.'
        )
    return "added"


def ensure_aliases_property(client=None):
    """Add an "Aliases" rich_text property to the Entities DB if missing.

    Holds newline-joined variant spellings folded into a page by the resolution pass
    (cross-script twins, STT mis-hears, subtitle variants) so future variants resolve
    to the canonical page instead of minting a duplicate. Returns "already" or "added";
    raises with a UI-fallback message if the API rejects the add.
    """
    client = client or _client()
    ds = _retry(client.data_sources.retrieve, data_source_id=config.NOTION_ENTITIES_DS_ID)
    if "Aliases" in (ds.get("properties") or {}):
        return "already"
    try:
        _retry(
            client.data_sources.update,
            data_source_id=config.NOTION_ENTITIES_DS_ID,
            properties={"Aliases": {"rich_text": {}}},
        )
    except APIResponseError as e:
        raise RuntimeError(
            f"API rejected adding Aliases property: {e}. Add a Text property named "
            '"Aliases" to the Entities DB in the Notion UI, then re-run.'
        )
    return "added"


def ensure_transcript_url(client=None):
    """Convert the Episodes "Transcript" property to url (from file) if needed.

    The column is empty so nothing is lost. Returns "already", "converted", or
    "missing" (no such property). Raises with a UI-fallback message on rejection.
    """
    client = client or _client()
    ds = _retry(client.data_sources.retrieve, data_source_id=config.NOTION_EPISODES_DS_ID)
    prop = (ds.get("properties") or {}).get("Transcript")
    if prop is None:
        return "missing"
    if prop["type"] == "url":
        return "already"
    try:
        _retry(
            client.data_sources.update,
            data_source_id=config.NOTION_EPISODES_DS_ID,
            properties={"Transcript": {"url": {}}},
        )
    except APIResponseError as e:
        raise RuntimeError(
            f"API rejected Transcript file->url conversion: {e}. Change the "
            '"Transcript" property type to URL in the Notion UI, then re-run.'
        )
    return "converted"


# --------------------------------------------------------------------------
# Entities index (dedup)
# --------------------------------------------------------------------------
def _load_entities_index(client):
    """Query Entities data source once -> { key: {page_id, episodes, recommended,
    mentions, has_link, has_oneliner, has_ticker} }."""
    index = {}
    cursor = None
    while True:
        kwargs = {"data_source_id": config.NOTION_ENTITIES_DS_ID, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = _retry(client.data_sources.query, **kwargs)
        for page in resp.get("results", []):
            props = page["properties"]
            key = _plain(props.get("Key"))
            if not key:
                continue
            episodes = {r["id"] for r in (props.get("Episodes", {}).get("relation") or [])}
            recommended = {o["name"] for o in (props.get("Recommended by", {}).get("multi_select") or [])}
            mentions = props.get("Mentions", {}).get("number") or 0
            # Aliases: newline-joined variant spellings absorbed into this page. Used by
            # the resolution pass so a known variant short-circuits to this entity.
            aliases = [a.strip() for a in _plain(props.get("Aliases")).splitlines() if a.strip()]
            index[key] = {
                "page_id": page["id"],
                "name": _plain(props.get("Name")),
                "type": (props.get("Type", {}).get("select") or {}).get("name"),
                "aliases": aliases,
                "episodes": episodes,
                "recommended": recommended,
                "mentions": mentions,
                "notability": props.get("Notability", {}).get("number") or 0,
                "has_link": bool(props.get("Link", {}).get("url")),
                "has_oneliner": bool(_plain(props.get("One-liner"))),
                "has_ticker": bool(_plain(props.get("Ticker"))),
            }
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return index


def _has_property(client, ds_id, name):
    """True if the data source has a property called `name`. Best-effort (False on
    error). Lets writes stay guarded so a missing optional prop never 400s."""
    try:
        ds = _retry(client.data_sources.retrieve, data_source_id=ds_id)
        return name in (ds.get("properties") or {})
    except Exception:  # noqa: BLE001
        return False


def _learn_url(name, one_liner=None, etype=None, context=None):
    """A Perplexity 'quick-learn' deep-link for an entity: a *step-by-step* teaching
    prompt (background, why it matters, key points, an analogy, a closing check) built
    from the show's Strings, grounded in the entity's type noun, one-liner, and (when
    present) the claim raised about it on the podcast. Perplexity exposes only ?q=, so
    the pedagogy is baked into the prompt text. Click it in Notion to drop into a
    guided explainer."""
    label = SHOW.notion_learn_type_nouns.get(etype)
    descr = " — ".join(p for p in (label, one_liner) if p)
    subject = f"{name} ({descr})" if descr else name
    base = "https://www.perplexity.ai/search?q="

    def build(ctx):
        q = STRINGS.learn_prompt_template.format(subject=subject)
        if ctx:
            q += STRINGS.learn_prompt_context_template.format(show=SHOW.display_name, ctx=ctx)
        q += STRINGS.learn_prompt_suffix
        return base + urllib.parse.quote(q)

    # GUARDRAIL: Notion url property caps at 2000 chars. URL-encoded non-Latin text is
    # ~9 bytes/char, so a long episode context can overflow — trim it word-by-word
    # (then drop it) until the encoded URL fits; cap_url is the final backstop.
    ctx = context
    url = build(ctx)
    while ctx and len(url) > NOTION_URL_MAX:
        ctx = ctx.rsplit(" ", 1)[0] if " " in ctx else ""
        url = build(ctx + "…" if ctx else None)
    return cap_url(url)


def _ensure_learn_property(client):
    """Idempotently add a 'Learn' URL property to the Entities data source. Additive
    only — passing a single property to data_sources.update merges it in and does NOT
    touch existing select/multi_select option lists (the rename-wipes-options gotcha
    applies to changing an existing select's options, not to adding a new property).
    Returns True if the property is present afterwards."""
    if _has_property(client, config.NOTION_ENTITIES_DS_ID, "Learn"):
        return True
    try:
        _retry(client.data_sources.update, data_source_id=config.NOTION_ENTITIES_DS_ID,
               properties={"Learn": {"url": {}}})
        print("  [learn] added 'Learn' URL property to Entities DS")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  [learn] could not add 'Learn' property: {e}")
        return False


def _load_episode_numbers(client):
    """Map {episode_page_id: Episode #} from the Episodes data source. Used to turn
    an entity's prior episode page-ids into the earliest prior episode NUMBER for the
    🔁 returning marker. Best-effort: returns {} on failure. Called per-episode in
    process_episode (NOT hoisted to backfill scope), so it stays fresh as episodes
    are added during a backfill."""
    numbers = {}
    try:
        cursor = None
        while True:
            kwargs = {"data_source_id": config.NOTION_EPISODES_DS_ID, "page_size": 100}
            if cursor:
                kwargs["start_cursor"] = cursor
            resp = _retry(client.data_sources.query, **kwargs)
            for page in resp.get("results", []):
                num = (page["properties"].get("Episode #", {}) or {}).get("number")
                if num is not None:
                    numbers[page["id"]] = num
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
    except Exception as e:  # noqa: BLE001 - best effort; returning marker is optional
        print(f"  [warn] could not load episode numbers: {e}")
    return numbers


# --------------------------------------------------------------------------
# Episode page
# --------------------------------------------------------------------------
def _find_episode_by_guid(client, guid):
    resp = _retry(
        client.data_sources.query,
        data_source_id=config.NOTION_EPISODES_DS_ID,
        filter={"property": "GUID", "rich_text": {"equals": guid}},
    )
    results = resp.get("results", [])
    return results[0] if results else None


def _episode_properties(ep, status, summary=None):
    props = {
        "Title": {"title": _rt(ep.get("title"))},
        "GUID": {"rich_text": _rt(ep.get("guid"))},
        "Status": {"select": {"name": status}},
    }
    # Write Summary at create time so it survives even if a later step fails
    # (and shows in the table view).
    if summary:
        props["Summary"] = {"rich_text": _rt(summary)}
    if ep.get("number") is not None:
        props["Episode #"] = {"number": ep["number"]}
    if ep.get("date"):
        props["Date"] = {"date": {"start": ep["date"]}}
    if ep.get("duration"):
        props["Duration"] = {"rich_text": _rt(ep["duration"])}
    if ep.get("audio_url"):
        props["Audio URL"] = {"url": ep["audio_url"]}
    if ep.get("youtube_url"):
        props["YouTube URL"] = {"url": ep["youtube_url"]}
    if ep.get("spotify_url"):
        props["Spotify"] = {"url": ep["spotify_url"]}
    if ep.get("apple_url"):
        props["Apple Music"] = {"url": ep["apple_url"]}
    return props


# Entity type -> emoji heading label (from the show). Render order follows the
# show's entity_types taxonomy.
TYPE_LABELS = dict(SHOW.notion_type_labels)
TYPE_ORDER = [t for t in SHOW.entity_types if t in TYPE_LABELS]


def _h2(text):
    return {"object": "block", "type": "heading_2", "heading_2": {"rich_text": _rt(text)}}


def _h3(text):
    return {"object": "block", "type": "heading_3", "heading_3": {"rich_text": _rt(text)}}


def _bullet(rich_text):
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": rich_text}}


def _seg(text, bold=False, link=None):
    """One rich_text 'text' segment, optionally bold and/or hyperlinked."""
    t = {"content": (text or "")[:2000]}
    if link:
        t["link"] = {"url": link}
    seg = {"type": "text", "text": t}
    if bold:
        seg["annotations"] = {"bold": True}
    return seg


def _entity_bullet(e):
    """Bold (optionally linked) name + a plain tail segment."""
    rt = [_seg(e.get("name", ""), bold=True, link=e.get("link"))]
    tail = ""
    if e.get("ticker"):
        tail += f" ({e['ticker']})"
    if e.get("one_liner"):
        tail += f" — {e['one_liner']}"
    if e.get("context"):
        tail += f". {e['context']}"
    by = ", ".join(e.get("mentioned_by") or [])
    if by:
        tail += f" · {by}"
    if e.get("timestamp"):
        tail += f" · {e['timestamp']}"
    if tail:
        rt.append(_seg(tail))
    return _bullet(rt)


def _episode_body_blocks(data):
    """Rich episode-page body: summary, optional chapters, entities grouped by type."""
    blocks = []
    ep = data.get("episode", {})
    entities = data.get("entities", [])

    # 1. Summary
    blocks.append(_h2(STRINGS.notion_summary_heading))
    if data.get("summary"):
        blocks.append({"object": "block", "type": "paragraph",
                       "paragraph": {"rich_text": _rt(data["summary"])}})

    # 2. Chapters (only if present — supplied later by feed.py)
    chapters = ep.get("chapters")
    if chapters:
        blocks.append(_h2(STRINGS.notion_topics_heading))
        for ch in chapters:
            ts = ch.get("timestamp", "")
            title = ch.get("title", "")
            line = f"{ts} — {title}" if ts else title
            blocks.append(_bullet(_rt(line)))

    # 3. Entities grouped by type
    blocks.append(_h2(STRINGS.notion_entities_heading))
    grouped = {}
    for e in entities:
        t = e.get("type") or "other"
        if t not in TYPE_LABELS:
            t = "other"
        grouped.setdefault(t, []).append(e)
    for t in TYPE_ORDER:
        group = grouped.get(t)
        if not group:
            continue
        blocks.append(_h3(TYPE_LABELS[t]))
        for e in group:
            blocks.append(_entity_bullet(e))
    return blocks


# --------------------------------------------------------------------------
# Transcript child page
# --------------------------------------------------------------------------
CHILDREN_PER_REQUEST = 100   # Notion max blocks per create/append
RT_CHARS = 2000              # Notion max chars per rich_text segment


def _transcript_blocks(text):
    """One paragraph block per non-empty line; long lines split into <=2000-char
    multi-segment rich_text (Notion caps each segment, but a paragraph may hold
    several)."""
    blocks = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        segs = [_seg(line[i:i + RT_CHARS]) for i in range(0, len(line), RT_CHARS)]
        blocks.append({"object": "block", "type": "paragraph",
                       "paragraph": {"rich_text": segs}})
    return blocks


def _create_transcript_page(client, episode_page_id, text, title=None):
    title = title or STRINGS.notion_transcript_title
    """Create a child page under the episode page and fill it with the transcript,
    appending blocks in batches of <=100. Best-effort; returns the child page id
    or None on failure (never blocks the pipeline)."""
    try:
        blocks = _transcript_blocks(text)
        first, rest = blocks[:CHILDREN_PER_REQUEST], blocks[CHILDREN_PER_REQUEST:]
        child = _retry(
            client.pages.create,
            parent={"type": "page_id", "page_id": episode_page_id},
            properties={"title": {"title": _rt(title)}},
            children=first,
        )
        child_id = child["id"]
        for i in range(0, len(rest), CHILDREN_PER_REQUEST):
            _retry(client.blocks.children.append,
                   block_id=child_id, children=rest[i:i + CHILDREN_PER_REQUEST])
            time.sleep(WRITE_DELAY)
        return child_id
    except Exception as e:  # noqa: BLE001 - best effort
        print(f"  [transcript] page creation failed: {e}")
        return None


def _set_transcript_url(client, episode_page_id, child_id):
    """Point the episode's Transcript url property at the transcript child page.

    Best effort: silently skips if the property is not a url type (still file) or
    the child url can't be retrieved."""
    try:
        child = _retry(client.pages.retrieve, page_id=child_id)
        url = child.get("url")
        if not url:
            return
        _retry(client.pages.update, page_id=episode_page_id,
               properties={"Transcript": {"url": url}})
        time.sleep(WRITE_DELAY)
    except Exception as e:  # noqa: BLE001 - best effort
        print(f"  [transcript] could not set Transcript url: {e}")


# --------------------------------------------------------------------------
# Entity upsert
# --------------------------------------------------------------------------
def _context_bullet(episode_number, context):
    """Bullet for an entity page body: '{episode_word} N — <context>'."""
    label = (f"{STRINGS.notion_episode_context_word} {episode_number} — "
             if episode_number is not None else "")
    return _bullet([_seg(label, bold=True), _seg(context)])


def _upsert_entity(client, ent, index, episode_page_id, episode_date, ep_numbers=None,
                   has_notability=False, episode_number=None, has_context=False,
                   has_action=False, has_sentiment=False, has_learn=False,
                   has_aliases=False, has_guest=False):
    ep_numbers = ep_numbers or {}
    key = ent["canonical_key"]
    mentioned = [m for m in (ent.get("mentioned_by") or [])]

    if key in index:
        cur = index[key]
        # Returning signal: was this entity linked to an EARLIER episode (any page
        # other than the current one) before now? Compute BEFORE the union below.
        prior_pages = cur["episodes"] - {episode_page_id}
        ent["is_returning"] = bool(prior_pages)
        prior_nums = [ep_numbers[p] for p in prior_pages if ep_numbers.get(p) is not None]
        ent["earliest_episode"] = min(prior_nums) if prior_nums else None
        # Idempotent: only count this episode once. If it's already in the
        # entity's Episodes, a re-run must NOT re-increment Mentions.
        already_linked = episode_page_id in cur["episodes"]
        new_mentions = cur["mentions"] if already_linked else cur["mentions"] + 1
        episodes = cur["episodes"] | {episode_page_id}
        recommended = cur["recommended"] | set(mentioned)
        props = {
            "Mentions": {"number": new_mentions},
            "Episodes": {"relation": [{"id": pid} for pid in episodes]},
            "Recommended by": {"multi_select": [{"name": n} for n in recommended]},
        }
        # Fill empties only.
        if not cur["has_link"] and ent.get("link"):
            props["Link"] = {"url": ent["link"]}
        if not cur["has_oneliner"] and ent.get("one_liner"):
            props["One-liner"] = {"rich_text": _rt(ent["one_liner"])}
        if not cur["has_ticker"] and ent.get("ticker"):
            props["Ticker"] = {"rich_text": _rt(ent["ticker"])}
        # Notability: keep the strongest signal seen across episodes (matches the
        # in-episode MAX merge). Guarded — only if the DS has the property.
        new_notability = max(cur.get("notability") or 0, ent.get("notability") or 0)
        if has_notability:
            props["Notability"] = {"number": new_notability}
        # Context column: overwrite with the current episode's sentence so the
        # column always reflects the most-recent mention.
        if has_context and ent.get("context"):
            props["Context"] = {"rich_text": _rt(ent["context"])}
        # Action (type-derived) + Sentiment (this episode's stance): overwrite,
        # guarded. action may be null (place/other) -> leave the select empty.
        if has_action and ent.get("action"):
            props["Action"] = {"select": {"name": ent["action"]}}
        if has_sentiment and ent.get("sentiment"):
            props["Sentiment"] = {"select": {"name": ent["sentiment"]}}
        # Guest flag: promote-only. Once a person has guested they stay flagged, so a
        # later episode that merely DISCUSSES them (is_guest false) must not clear it.
        if has_guest and ent.get("is_guest"):
            props["Guest"] = {"checkbox": True}
        # Learn deep-link: refresh each episode so it reflects the latest one-liner.
        if has_learn and ent.get("name"):
            props["Learn"] = {"url": _learn_url(ent["name"], ent.get("one_liner"),
                                                ent.get("type"), ent.get("context"))}
        # Aliases: record the variant spelling(s) the resolver folded into this page
        # (the pre-correction name, and the display name when it differs from the
        # stored Name) so future variants short-circuit here. Dedup + preserve order.
        if has_aliases:
            variants = [v for v in (ent.get("alias"), ent.get("name")) if v]
            merged = list(cur.get("aliases") or [])
            page_name = cur.get("name") or ""
            for v in variants:
                if v and v != page_name and v not in merged:
                    merged.append(v)
            if merged != (cur.get("aliases") or []):
                props["Aliases"] = {"rich_text": _rt("\n".join(merged))}
                cur["aliases"] = merged
        _retry(client.pages.update, page_id=cur["page_id"], properties=props)
        time.sleep(WRITE_DELAY)
        # Body: append this episode's context bullet (only the first time this
        # episode links the entity, so re-runs don't duplicate).
        if ent.get("context") and not already_linked:
            try:
                _retry(client.blocks.children.append, block_id=cur["page_id"],
                       children=[_context_bullet(episode_number, ent["context"])])
                time.sleep(WRITE_DELAY)
            except Exception as e:  # noqa: BLE001 - body is best effort
                print(f"  [entity body] append failed for {key}: {e}")
        # Refresh cache so repeated keys within one run stay consistent.
        cur.update(
            episodes=episodes, recommended=recommended, mentions=new_mentions,
            notability=new_notability,
            has_link=cur["has_link"] or bool(ent.get("link")),
            has_oneliner=cur["has_oneliner"] or bool(ent.get("one_liner")),
            has_ticker=cur["has_ticker"] or bool(ent.get("ticker")),
        )
        return cur["page_id"]

    # Create — brand new entity, never seen before this episode.
    ent["is_returning"] = False
    ent["earliest_episode"] = None
    props = {
        "Name": {"title": _rt(ent.get("name"))},
        "Key": {"rich_text": _rt(key)},
        "Mentions": {"number": 1},
        "Episodes": {"relation": [{"id": episode_page_id}]},
        "Recommended by": {"multi_select": [{"name": n} for n in mentioned]},
    }
    if ent.get("type"):
        props["Type"] = {"select": {"name": ent["type"]}}
    if has_notability:
        props["Notability"] = {"number": ent.get("notability")}
    if ent.get("one_liner"):
        props["One-liner"] = {"rich_text": _rt(ent["one_liner"])}
    if ent.get("ticker"):
        props["Ticker"] = {"rich_text": _rt(ent["ticker"])}
    if ent.get("link"):
        props["Link"] = {"url": ent["link"]}
    if has_context and ent.get("context"):
        props["Context"] = {"rich_text": _rt(ent["context"])}
    if has_action and ent.get("action"):
        props["Action"] = {"select": {"name": ent["action"]}}
    if has_sentiment and ent.get("sentiment"):
        props["Sentiment"] = {"select": {"name": ent["sentiment"]}}
    if has_guest:
        props["Guest"] = {"checkbox": bool(ent.get("is_guest"))}
    if has_learn and ent.get("name"):
        props["Learn"] = {"url": _learn_url(ent["name"], ent.get("one_liner"),
                                            ent.get("type"), ent.get("context"))}
    if episode_date:
        props["First seen"] = {"date": {"start": episode_date}}

    create_kwargs = {
        "parent": {"type": "data_source_id",
                   "data_source_id": config.NOTION_ENTITIES_DS_ID},
        "properties": props,
    }
    if ent.get("context"):
        create_kwargs["children"] = [_context_bullet(episode_number, ent["context"])]
    page = _retry(client.pages.create, **create_kwargs)
    time.sleep(WRITE_DELAY)
    index[key] = {
        "page_id": page["id"], "episodes": {episode_page_id},
        "recommended": set(mentioned), "mentions": 1,
        "notability": ent.get("notability") or 0,
        "has_link": bool(ent.get("link")), "has_oneliner": bool(ent.get("one_liner")),
        "has_ticker": bool(ent.get("ticker")),
    }
    return page["id"]


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------
def process_episode(data, transcript_path=None, client=None):
    """Write one extraction-contract episode into Notion + notify.

    Returns dict: {status, episode_page_id, episode_url, entity_page_ids}.
    """
    client = client or _client()
    ep = data["episode"]
    guid = ep["guid"]
    entities = data.get("entities", [])

    # Idempotency.
    existing = _find_episode_by_guid(client, guid)
    if existing:
        status = (existing["properties"].get("Status", {}).get("select") or {}).get("name")
        if status == "done":
            print(f"  [skip] episode guid={guid} already done")
            return {"status": "skipped", "episode_page_id": existing["id"],
                    "episode_url": existing.get("url"), "entity_page_ids": []}

    # Create episode page (processing) — or reuse existing non-done page.
    summary = data.get("summary")
    if existing:
        episode_page_id = existing["id"]
        _retry(client.pages.update, page_id=episode_page_id,
               properties=_episode_properties(ep, "processing", summary))
    else:
        page = _retry(
            client.pages.create,
            parent={"type": "data_source_id", "data_source_id": config.NOTION_EPISODES_DS_ID},
            properties=_episode_properties(ep, "processing", summary),
        )
        episode_page_id = page["id"]
    time.sleep(WRITE_DELAY)

    # Upsert entities with dedup. Reload the episode-number map here (per episode,
    # not hoisted) so a backfill sees episodes added earlier in the same run when
    # computing each entity's earliest prior episode for the 🔁 marker.
    index = _load_entities_index(client)
    ep_numbers = _load_episode_numbers(client)
    has_notability = _has_property(client, config.NOTION_ENTITIES_DS_ID, "Notability")
    has_context = _has_property(client, config.NOTION_ENTITIES_DS_ID, "Context")
    has_action = _has_property(client, config.NOTION_ENTITIES_DS_ID, "Action")
    has_sentiment = _has_property(client, config.NOTION_ENTITIES_DS_ID, "Sentiment")
    has_learn = _ensure_learn_property(client)
    has_aliases = _has_property(client, config.NOTION_ENTITIES_DS_ID, "Aliases")
    has_guest = _has_property(client, config.NOTION_ENTITIES_DS_ID, "Guest")
    entity_page_ids = []
    for ent in entities:
        pid = _upsert_entity(client, ent, index, episode_page_id, ep.get("date"),
                             ep_numbers, has_notability, ep.get("number"), has_context,
                             has_action=has_action, has_sentiment=has_sentiment,
                             has_learn=has_learn, has_aliases=has_aliases,
                             has_guest=has_guest)
        entity_page_ids.append(pid)

    # No explicit Episode -> Entities write. The relation is two-way
    # (dual_property): _upsert_entity sets each entity's "Episodes" side (one id
    # each, never near Notion's 100-per-write cap) and Notion auto-syncs the
    # episode's "Entities" side. An explicit forward write would just duplicate
    # that work and 400s once an episode has >100 entities. Verified empirically:
    # setting only the entity side populates the episode side.

    # Episode body — append in batches of <=100 (Notion's per-request block cap;
    # a 100+ entity episode produces more than that).
    body_blocks = _episode_body_blocks(data)
    for i in range(0, len(body_blocks), CHILDREN_PER_REQUEST):
        _retry(
            client.blocks.children.append,
            block_id=episode_page_id,
            children=body_blocks[i:i + CHILDREN_PER_REQUEST],
        )
        time.sleep(WRITE_DELAY)

    # Transcript as its own child page under the episode (best effort). Point the
    # episode's Transcript url property at that child page so it's clickable in the
    # table view.
    if transcript_path:
        try:
            with open(transcript_path, encoding="utf-8") as f:
                child_id = _create_transcript_page(client, episode_page_id, f.read())
            if child_id and _has_property(client, config.NOTION_EPISODES_DS_ID, "Transcript"):
                _set_transcript_url(client, episode_page_id, child_id)
        except OSError as e:
            print(f"  [transcript] could not read {transcript_path}: {e}")

    # Summary property is written at create time (see _episode_properties).

    # Done.
    _retry(client.pages.update, page_id=episode_page_id,
           properties={"Status": {"select": {"name": "done"}}})

    final = _retry(client.pages.retrieve, page_id=episode_page_id)
    episode_url = final.get("url")

    # Notify.
    try:
        notify.notify(ep, entities, episode_url)
    except Exception as e:  # noqa: BLE001
        print(f"  [notify] failed: {e}")

    return {"status": "done", "episode_page_id": episode_page_id,
            "episode_url": episode_url, "entity_page_ids": entity_page_ids,
            "has_notability": has_notability}
