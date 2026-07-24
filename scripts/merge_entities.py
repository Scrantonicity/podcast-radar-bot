"""Apply the manual entity-audit decisions to the live Notion Entities DB.

Merges duplicate entity pages (survivor keeps union of episodes/recommended/
mentions; richer field wins; losers archived to Notion trash — recoverable 30d).
Disambiguates by type/ticker so same-name-different-entity clusters stay apart.

Dry-run by default. Pass  --apply  to write to Notion.

  python merge_entities.py            # dry run: prints resolved plan
  python merge_entities.py --apply    # execute against live Notion
"""

import sys
import time

import config
from notion_bridge import _client, _plain, _rt, _retry, trash_page, WRITE_DELAY


# --------------------------------------------------------------------------
# Load every entity page with the full fields we need to merge correctly.
# --------------------------------------------------------------------------
def _sel(prop):
    return ((prop or {}).get("select") or {}).get("name") or ""


def load_pages(client):
    pages = []
    cursor = None
    while True:
        kwargs = {"data_source_id": config.NOTION_ENTITIES_DS_ID, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = _retry(client.data_sources.query, **kwargs)
        for pg in resp.get("results", []):
            p = pg["properties"]
            pages.append({
                "id": pg["id"],
                "name": _plain(p.get("Name")),
                "type": _sel(p.get("Type")),
                "ticker": _plain(p.get("Ticker")),
                "episodes": {r["id"] for r in (p.get("Episodes", {}).get("relation") or [])},
                "recommended": {o["name"] for o in (p.get("Recommended by", {}).get("multi_select") or [])},
                "mentions": p.get("Mentions", {}).get("number") or 0,
                "notability": p.get("Notability", {}).get("number") or 0,
                "one_liner": _plain(p.get("One-liner")),
                "context": _plain(p.get("Context")),
                "link": (p.get("Link", {}) or {}).get("url") or "",
                "action": _sel(p.get("Action")),
                "sentiment": _sel(p.get("Sentiment")),
            })
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return pages


# --------------------------------------------------------------------------
# Selector + merge-group spec
# --------------------------------------------------------------------------
class S:
    """A page selector: exact Name, optionally filtered by type / ticker."""
    def __init__(self, name, type=None, ticker=None):
        self.name, self.type, self.ticker = name, type, ticker

    def matches(self, p):
        if p["name"] != self.name:
            return False
        if self.type and p["type"] != self.type:
            return False
        if self.ticker and (p["ticker"] or "") != self.ticker:
            return False
        return True


def P(n, **k):
    return S(n, **k)


# Each group: list of selectors. selectors[0] => survivor name. ALL pages
# matching ANY selector are gathered; survivor = best (most episodes, then
# mentions) among those matching selectors[0]; everyone else is a loser.
#
# Per-show merge groups: each inner list groups entities that are the same
# real-world thing and should be merged into one page (survivor keeps the union).
# Example:
#   [P("Microsoft"), P("מיקרוסופט")],
#   [P("Google", type="stock"), P("גוגל", type="stock")],
#   [P("Barack Obama", type="person"), P("Obama", type="person")],
GROUPS = []

# Row fixes (no merge): clear a wrong field on a single page.
# Example:  [P("Check Point", type="book")]  (a page mistyped as a book)
FIX_CLEAR_TICKER = []


def resolve(group, pages):
    """-> (survivor, [losers]) or (None, reason)."""
    gathered, seen = [], set()
    for selr in group:
        for p in pages:
            if p["id"] in seen:
                continue
            if selr.matches(p):
                gathered.append(p)
                seen.add(p["id"])
    if len(gathered) < 2:
        return None, f"only {len(gathered)} page(s) matched"
    surv_cands = [p for p in gathered if group[0].matches(p)]
    if not surv_cands:
        return None, "no survivor candidate"
    survivor = max(surv_cands, key=lambda p: (len(p["episodes"]), p["mentions"]))
    losers = [p for p in gathered if p["id"] != survivor["id"]]
    return survivor, losers


def merged_props(survivor, losers):
    eps = set(survivor["episodes"])
    rec = set(survivor["recommended"])
    notab = survivor["notability"]
    fills = {k: survivor[k] for k in ("one_liner", "context", "ticker", "link", "action", "sentiment")}
    for lo in losers:
        eps |= lo["episodes"]
        rec |= lo["recommended"]
        notab = max(notab, lo["notability"])
        for k in fills:
            if not fills[k] and lo[k]:
                fills[k] = lo[k]
    props = {
        "Episodes": {"relation": [{"id": i} for i in eps]},
        "Recommended by": {"multi_select": [{"name": n} for n in rec]},
        "Mentions": {"number": len(eps)},
        "Notability": {"number": notab},
    }
    if fills["one_liner"]:
        props["One-liner"] = {"rich_text": _rt(fills["one_liner"])}
    if fills["context"]:
        props["Context"] = {"rich_text": _rt(fills["context"])}
    if fills["ticker"]:
        props["Ticker"] = {"rich_text": _rt(fills["ticker"])}
    if fills["link"]:
        props["Link"] = {"url": fills["link"]}
    if fills["action"]:
        props["Action"] = {"select": {"name": fills["action"]}}
    if fills["sentiment"]:
        props["Sentiment"] = {"select": {"name": fills["sentiment"]}}
    return props


def main():
    apply = "--apply" in sys.argv
    client = _client()
    pages = load_pages(client)
    print(f"Loaded {len(pages)} entity pages. Mode: {'APPLY' if apply else 'DRY RUN'}\n")

    planned, skipped, archives = [], [], 0
    for group in GROUPS:
        survivor, losers = resolve(group, pages)
        if survivor is None:
            skipped.append((group[0].name, losers))
            continue
        planned.append((survivor, losers))
        archives += len(losers)

    for survivor, losers in planned:
        names = ", ".join(f'"{lo["name"]}"({lo["type"]},{",".join(sorted(str(e) for e in []))})' for lo in losers)
        lo_desc = "  +  ".join(f'"{lo["name"]}"[{lo["type"]}, {len(lo["episodes"])}ep]' for lo in losers)
        print(f'KEEP "{survivor["name"]}" [{survivor["type"]}, {len(survivor["episodes"])}ep]  <=  {lo_desc}')

    print(f"\n{len(planned)} merges, {archives} pages to archive.")
    if skipped:
        print(f"\nSKIPPED {len(skipped)} groups (need manual look):")
        for name, reason in skipped:
            print(f'  - "{name}": {reason}')

    # row fixes
    fix_targets = [p for fx in FIX_CLEAR_TICKER for p in pages if fx.matches(p) and p["ticker"]]
    if fix_targets:
        print("\nFIX (clear wrong ticker):")
        for p in fix_targets:
            print(f'  - "{p["name"]}"[{p["type"]}] ticker {p["ticker"]} -> (cleared)')

    if not apply:
        print("\nDry run only. Re-run with --apply to write to Notion.")
        return

    print("\nApplying...")
    for survivor, losers in planned:
        props = merged_props(survivor, losers)
        _retry(client.pages.update, page_id=survivor["id"], properties=props)
        time.sleep(WRITE_DELAY)
        for lo in losers:
            trash_page(client, lo["id"])
            time.sleep(WRITE_DELAY)
        print(f'  merged -> "{survivor["name"]}" (archived {len(losers)})')
    for p in fix_targets:
        _retry(client.pages.update, page_id=p["id"], properties={"Ticker": {"rich_text": []}})
        time.sleep(WRITE_DELAY)
        print(f'  fixed ticker on "{p["name"]}"')
    print("\nDone.")


if __name__ == "__main__":
    main()
