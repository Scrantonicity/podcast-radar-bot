# Contributing

Thanks for taking the time. This is a small project with one strong opinion — read
the first rule, then the rest is ordinary.

## The rule: the engine stays podcast-agnostic

Everything at the repo root (`feed.py`, `stt.py`, `transcribe.py`, `extract.py`,
`notion_bridge.py`, `notify.py`, the orchestrators) is generic. It must not contain
literals belonging to any one podcast — no show names, no host names, no feed ids, no
Hebrew (or any other language's) user-facing strings, no hardcoded entity types.

All of that lives in `shows/<name>/` — `config.py`, `strings.py`, `prompt.txt`. If your
change wants a show-specific value in an engine file, the value belongs in `ShowConfig`
or `Strings` instead (schemas in `showkit.py`). This is what lets one engine run a
Hebrew RTL show and an English one with no code changes, and it's the invariant most
worth protecting.

## Adding your own podcast is not a pull request

A new show is a directory in your own fork or checkout — `cp -r shows/_template
shows/mypodcast`. Don't open a PR to add it here.

PRs *are* welcome for: engine improvements, new STT or LLM backends, docs, tests, and
fixes to `shows/_template`.

## Flow

1. Fork the repo and create a branch (`git checkout -b feature/thing`).
2. Make your change.
3. Run the tests (below). They must pass.
4. Commit, push, open a PR describing what changed and why.

## Tests

Standard library `unittest` — no runner dependency:

```bash
python -m unittest discover tests
```

If you're adding an invariant — something that must never regress, especially anything
touching public posting, Notion writes, or cost — add it to `tests/test_guardrails.py`
alongside the existing ones. That file is the project's memory of things that broke in
production once.

## Style

Match the surrounding code. No formatter is enforced; no linter config ships with the
repo. Keep comments for constraints the code can't express.
