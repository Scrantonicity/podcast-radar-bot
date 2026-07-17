"""show_loader.py — pick the active podcast and expose its config to the engine.

The engine imports from here and nowhere else for podcast/language specifics:

    from show_loader import SHOW, STRINGS, PROMPT, REGEN_PROMPT

Which show loads is chosen by the `SHOW` env var (default: "table4"). It maps to
the directory `shows/<SHOW>/`, which must contain `config.py` (defines `SHOW`),
`strings.py` (defines `STRINGS`), and `prompt.txt` (the extraction system prompt).
An optional `regen.txt` holds the meta-context repair prompt; absent -> "".
"""

import importlib
import os

from dotenv import load_dotenv

load_dotenv()

SHOW_NAME = os.getenv("SHOW", "table4").strip()

_SHOWS_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shows")
_SHOW_DIR = os.path.join(_SHOWS_ROOT, SHOW_NAME)


def _require_dir():
    if not os.path.isdir(_SHOW_DIR):
        available = sorted(
            d for d in os.listdir(_SHOWS_ROOT)
            if os.path.isdir(os.path.join(_SHOWS_ROOT, d)) and not d.startswith("__")
        )
        raise RuntimeError(
            f"SHOW={SHOW_NAME!r} not found: no directory shows/{SHOW_NAME}/. "
            f"Available shows: {', '.join(available) or '(none)'}. "
            "Set SHOW in your .env (see README → 'Add your own podcast')."
        )


def _load_text(basename):
    path = os.path.join(_SHOW_DIR, basename)
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


_require_dir()

# shows/ is a namespace of plain modules; import them by dotted path.
_config_mod = importlib.import_module(f"shows.{SHOW_NAME}.config")
_strings_mod = importlib.import_module(f"shows.{SHOW_NAME}.strings")

SHOW = _config_mod.SHOW
STRINGS = _strings_mod.STRINGS


def _fill_tokens(text):
    """Inject a few config values into a prompt via {{TOKEN}} markers, so hosts stay
    single-source. A no-op for prompts that hardcode their own names (no markers)."""
    return (text
            .replace("{{SHOW_NAME}}", SHOW.display_name)
            .replace("{{HOSTS}}", ", ".join(SHOW.hosts))
            .replace("{{GUEST_LABEL}}", SHOW.guest_label))


PROMPT = _fill_tokens(_load_text("prompt.txt"))
REGEN_PROMPT = _fill_tokens(_load_text("regen.txt"))
# Optional per-show prompts. Empty string => that stage is skipped entirely:
#   resolve.txt  -> the entity resolution pass (resolve_entities.py)
#   backfill.txt -> the archive dedup clustering pass (scripts/backfill_cleanup.py)
RESOLVE_PROMPT = _fill_tokens(_load_text("resolve.txt"))
BACKFILL_PROMPT = _fill_tokens(_load_text("backfill.txt"))

if not PROMPT.strip():
    raise RuntimeError(f"shows/{SHOW_NAME}/prompt.txt is empty — the extraction prompt is required.")
