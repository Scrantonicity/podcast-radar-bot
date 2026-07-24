"""notion_ids.py — resolve the data-source IDs for your Notion databases.

Notion's current API version writes/queries against a database's *data source*, not
the database itself, so the pipeline needs four IDs in .env: the two database IDs
(from the DB page URL) and their two data-source IDs. The data-source ID is not in
any URL — this script fetches it for you, so you never hand-copy a stale one (a wrong
data-source ID is the classic 404 on the first run).

Prerequisites in .env (or the environment):
    NOTION_TOKEN            your integration token (ntn_...)
    NOTION_EPISODES_DB_ID   Episodes database id  (the 32-hex in its page URL)
    NOTION_ENTITIES_DB_ID   Entities database id

The integration must be shared with both databases (open each DB → ••• → Connections).

Run:  ./venv/bin/python scripts/notion_ids.py
It prints the two NOTION_*_DS_ID lines to paste into .env.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from notion_client import Client
from notion_client.errors import APIResponseError


def _data_sources(client, database_id):
    """Return [(name, id), ...] for a database's data sources (current API)."""
    db = client.databases.retrieve(database_id=database_id)
    return [(ds.get("name") or "(unnamed)", ds["id"]) for ds in db.get("data_sources", [])]


def _resolve(client, label, env_name, database_id):
    if not database_id:
        print(f"  ✗ {label}: {env_name} is not set in .env — skipping", file=sys.stderr)
        return None
    try:
        sources = _data_sources(client, database_id)
    except APIResponseError as e:
        hint = " (is the integration shared with this database?)" if e.code in (
            "object_not_found", "unauthorized") else ""
        print(f"  ✗ {label}: {e.code}{hint}", file=sys.stderr)
        return None
    if not sources:
        print(f"  ✗ {label}: database has no data sources", file=sys.stderr)
        return None
    if len(sources) > 1:
        names = ", ".join(n for n, _ in sources)
        print(f"  ! {label}: multiple data sources ({names}); using the first",
              file=sys.stderr)
    name, ds_id = sources[0]
    print(f"  ✓ {label}: '{name}'", file=sys.stderr)
    return ds_id


def main():
    if not config.NOTION_TOKEN:
        sys.exit("NOTION_TOKEN is not set. Fill it in .env first.")
    client = Client(auth=config.NOTION_TOKEN, notion_version=config.NOTION_VERSION)

    print("Resolving data-source IDs…", file=sys.stderr)
    ep = _resolve(client, "Episodes", "NOTION_EPISODES_DB_ID", config.NOTION_EPISODES_DB_ID)
    en = _resolve(client, "Entities", "NOTION_ENTITIES_DB_ID", config.NOTION_ENTITIES_DB_ID)

    if not (ep and en):
        sys.exit("\nCould not resolve both data-source IDs — see the errors above.")

    print("\n# Paste these into your .env:")
    print(f"NOTION_EPISODES_DS_ID={ep}")
    print(f"NOTION_ENTITIES_DS_ID={en}")


if __name__ == "__main__":
    main()
