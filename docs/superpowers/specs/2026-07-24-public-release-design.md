# podcast-radar-bot — public release design

Date: 2026-07-24
Status: approved, in execution

## Context

podcast-radar-bot is a genericized, config-driven blueprint of a working podcast
pipeline (RSS → Speechmatics STT → Gemini extraction → entity resolution → Notion →
gated Telegram digest). The goal is to publish it as a genuinely reusable product —
any podcast, any language — not just a scrubbed personal repo.

A field test on a second Hebrew show (an isolated on-disk fork, run 2026-07-17) proved
the pipeline end-to-end and surfaced fixes and one feature that never made it back
into this repo. This release folds those in, adds an onboarding path that adapts the
entity taxonomy to each new show, refreshes the README, and ships duplicatable Notion
templates (English + Hebrew).

Security audit found no blockers: git history clean of secrets, MIT-licensed under a
pseudonym, `.env.example` carries no real values, the sole remote is the (private)
GitHub repo. Publishing waits until the whole package is ready.

## Decisions

- Ship only when the full package is complete (no partial publish).
- STT: Speechmatics + paste-your-own-transcript for v1; local faster-whisper on the roadmap.
- Extraction LLM: Gemini only for v1; other providers on the roadmap.
- Notion templates: English + Hebrew, built fresh and generic, then made duplicatable.
- README: targeted upgrade, keep the current structure.
- Cost documentation: real figure ≈ $0.60 per hour-long episode (measured: $40 / 65
  episodes on Speechmatics batch), not the erroneous $50/episode from field notes.
- Operator: an LLM coding agent (Claude Code / Codex / Gemini CLI) or a human, same docs.

## Field-test learnings folded in

1. `is_guest` — a stored boolean marking the episode's in-studio guest, distinct from
   `is_tool` (which folds into Action). Promote-only on write so a later episode that
   merely discusses a past guest can't clear the flag. Existed only in the fork.
2. Observatory feature (offline HTML stats page) was born during the test run — it is
   the uncommitted work in this tree; commit it after scrubbing real-show references.
3. `stt_additional_vocab` matters: Speechmatics mishears host and brand names; onboarding
   must collect exact host spellings and expected brand terms up front.
4. Notion's write API is data-source-scoped; a stale data-source ID is the classic first-run
   404. Ship a helper that resolves data-source IDs from database IDs.
5. Podcast feeds: Spotify links have no RSS. Onboarding needs a "find your real RSS" step.
6. Entity mix is show-specific (a tech show fired person/stock/concept, never book/place),
   which validates an adaptive taxonomy over a fixed one.

## Design

### Adaptive taxonomy (already largely supported)

The engine holds no entity-type literals: `entity_types`, `mentioned_by_enum`,
`tg_sections`, `notion_type_labels` all come from `ShowConfig`. The one gap — a hardcoded
type→Action map in `extract.py` — is closed with an optional `ShowConfig.action_by_type`
overlay, so a custom taxonomy never needs an engine edit. The Notion property *names* and
pipeline states stay fixed; only the select options / sections / vocab adapt per show.

### Onboarding (`ONBOARDING.md`)

A playbook an agent or human follows: interview (name, language, hosts, sponsors, what to
track, brand vocab) → find the real RSS → provide one sample transcript (paste or one
Speechmatics run) → derive a taxonomy from interview + sample → scaffold `shows/<name>/`
from `shows/_template/` → wire Notion (duplicate template, integration token, share,
`scripts/notion_ids.py`, fill `.env`) → optional Telegram → first run
`python main.py --episode 1 --no-telegram` → verify → enable the rest.

### Notion templates (EN + HE)

Built fresh via the Notion API in the user's workspace, nothing copied from live shows:
Episodes DB + Entities DB (bidirectional relation), the exact property names/enums the code
writes, the Tools and Guests filtered views, one fictional sample episode, and an embedded
guide page mirroring the Notion-wiring steps. Made duplicatable; links go into the README
and ONBOARDING.md.

### README (targeted upgrade)

Add an Onboarding section (point your coding agent at ONBOARDING.md), Notion template links
+ duplicate flow, an honest Costs subsection, and roadmap items (faster-whisper, multi-LLM).

## Verification

- `pip install -r requirements-dev.txt && SHOW=demo pytest tests/ -q` green (incl. new
  is_guest guardrail tests).
- `SHOW=demo python build_observatory.py --dry-run --extractions tests/fixtures/observatory/extractions`
  builds after the scrub.
- A leak scan for the original single-show identifiers returns zero hits outside legitimate uses.
- Onboarding dry-run against a real public feed with a cached transcript reproduces a
  taxonomy close to the field test's proven config — no paid STT call.
- Secrets re-scan on the final tree and history before the repo is flipped public.
