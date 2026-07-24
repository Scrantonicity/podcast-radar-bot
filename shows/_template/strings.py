"""shows/_template/strings.py — user-facing text for a NEW podcast (English defaults).

Every field has an English default (see showkit.Strings), so you only override what
you want to change or translate. `{show}`, `{k}`, `{link}`, `{num}`, `{n}`,
`{subject}`, `{ctx}`, `{episode_word}` placeholders are filled by the engine — keep them.
"""

from showkit import Strings

STRINGS = Strings(
    # Header shown on every digest, e.g. "🎙️ My Podcast | Ep. 12: headline (date)".
    tg_header_prefix="🎙️ My Podcast",              # TODO: match your show name

    # Leave the rest as the English defaults, or override any of them. Examples:
    # tg_episode_word="Ep.",
    # tg_deepdive_label="🔥 Deep Dive:",
    # approve_btn="✅ Approve & post",

    # meta_context_patterns is empty by default -> the meta-context repair pass is
    # OFF. Only turn it on (with language-specific regex fragments) if your prompt
    # keeps producing "who said it" contexts instead of "what it is".
    meta_context_patterns=(),
)
