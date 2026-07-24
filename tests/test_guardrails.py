"""test_guardrails.py — regression tests for the invariants baked in from hard-won
lessons (see README → "Gotchas already handled"). All offline; no network, no keys.

Run:  SHOW=demo PYTHONPATH=. ./venv/bin/python -m unittest tests.test_guardrails -v
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

# Make the repo root importable when run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# These tests assert engine mechanisms; the demo show gives concrete host/sponsor data.
os.environ.setdefault("SHOW", "demo")

import notify
import notion_bridge as nb
import extract


class ApprovalGateGuardrail(unittest.TestCase):
    """Public-channel posting is fail-closed: send_telegram must refuse without an
    explicit allow_public=True (the ep-61-style accidental public post)."""

    def test_send_telegram_refuses_without_flag(self):
        with self.assertRaises(RuntimeError) as ctx:
            notify.send_telegram("hello channel")
        self.assertIn("allow_public", str(ctx.exception))

    def test_approval_request_is_the_default_path(self):
        # The private-draft function exists and does not require allow_public.
        self.assertTrue(hasattr(notify, "send_approval_request"))


class NotionUrlCapGuardrail(unittest.TestCase):
    """Notion url properties cap at 2000 chars or pages.update 400s."""

    def test_cap_url_truncates(self):
        self.assertEqual(len(nb.cap_url("a" * 5000)), 2000)

    def test_cap_url_leaves_short_untouched(self):
        self.assertEqual(nb.cap_url("https://x/y"), "https://x/y")

    def test_learn_url_never_exceeds_cap(self):
        url = nb._learn_url("Entity", "a one liner", "concept", "context " * 500)
        self.assertLessEqual(len(url), 2000)


class NotionTrashGuardrail(unittest.TestCase):
    """Trashing a page uses in_trash=True (archived=True is rejected by this API version)."""

    def test_trash_page_uses_in_trash(self):
        client = MagicMock()
        nb.trash_page(client, "page-123")
        client.pages.update.assert_called_once_with(page_id="page-123", in_trash=True)
        # And never the rejected archived= form.
        _, kwargs = client.pages.update.call_args
        self.assertNotIn("archived", kwargs)


class SelectOptionMergeGuardrail(unittest.TestCase):
    """update_select_options must PRESERVE every existing option (a partial options
    list silently deletes omitted options and strips their values from all rows)."""

    def test_existing_options_are_never_dropped(self):
        client = MagicMock()
        client.data_sources.retrieve.return_value = {
            "properties": {
                "Recommended by": {
                    "type": "multi_select",
                    "multi_select": {"options": [
                        {"name": "A", "id": "1", "color": "red"},
                        {"name": "B", "id": "2", "color": "blue"},
                    ]},
                }
            }
        }
        nb.update_select_options(client, "ds-1", "Recommended by", ["C"])
        _, kwargs = client.data_sources.update.call_args
        sent = kwargs["properties"]["Recommended by"]["multi_select"]["options"]
        names = {o["name"] for o in sent}
        self.assertEqual(names, {"A", "B", "C"})              # nothing dropped, C added
        by_name = {o["name"]: o for o in sent}
        self.assertEqual(by_name["A"]["id"], "1")             # existing ids preserved
        self.assertEqual(by_name["B"]["color"], "blue")       # existing colors preserved


class HostSponsorFilterGuardrail(unittest.TestCase):
    """Hosts and sponsors are dropped from entities, sourced from the show config."""

    def test_host_ban_includes_normalized_host_names(self):
        # Every current host short name must be banned (single-source, rename-safe).
        for host in extract.SHOW.hosts:
            self.assertIn(extract.normalize_key(host), extract.HOST_BAN_KEYS)

    def test_sponsor_ban_nonempty_for_demo(self):
        if extract.SHOW.display_name == "רדאר":
            self.assertIn("demo brand", extract.SPONSOR_BAN_KEYS)

    def test_meta_context_feature_toggles_with_patterns(self):
        # Feature is ON only when the show defines patterns; OFF (no-op) otherwise.
        if extract.STRINGS.meta_context_patterns:
            self.assertIsNotNone(extract.META_CONTEXT_RE)
        else:
            self.assertIsNone(extract.META_CONTEXT_RE)


class GuestFlagGuardrail(unittest.TestCase):
    """is_guest is a standalone stored flag: coerced to a real bool, never folded
    into action (unlike is_tool), and promote-only on the Notion write so a later
    episode that merely DISCUSSES a past guest can't clear their Guest checkbox."""

    def setUp(self):
        # _upsert_entity sleeps WRITE_DELAY after each mocked write; zero it out.
        self._wd = nb.WRITE_DELAY
        nb.WRITE_DELAY = 0

    def tearDown(self):
        nb.WRITE_DELAY = self._wd

    def _entity(self, **over):
        e = {"name": "יונתן אריאל", "canonical_key": "yonatan-ariel", "type": "person",
             "notability": 3, "mentioned_by": [], "ticker": None, "one_liner": None,
             "context": None, "link": None, "timestamp": None, "action": None,
             "sentiment": "neutral", "is_tool": False}
        e.update(over)
        return e

    def test_validate_coerces_is_guest_to_bool(self):
        obj = {"summary": "s", "headline": "h", "entities": [
            self._entity(is_guest=True),
            self._entity(canonical_key="k2"),          # is_guest absent -> False
        ]}
        out = extract._validate(obj)
        self.assertIs(out["entities"][0]["is_guest"], True)
        self.assertIs(out["entities"][1]["is_guest"], False)

    def test_is_guest_does_not_fold_into_action(self):
        # is_tool overrides action to "Tool"; is_guest must NOT touch action.
        obj = {"summary": "s", "headline": "h", "entities": [
            self._entity(type="person", is_guest=True)]}
        out = extract._validate(obj)
        self.assertNotEqual(out["entities"][0]["action"], "Tool")

    def _cur(self, page_id, episode_page_id):
        # Minimal cache row shaped like _load_entities_index output.
        return {"page_id": page_id, "episodes": {episode_page_id},
                "recommended": set(), "mentions": 1, "notability": 3,
                "has_link": True, "has_oneliner": True, "has_ticker": True,
                "aliases": [], "name": "יונתן אריאל"}

    def test_update_is_promote_only(self):
        client = MagicMock()
        key = "yonatan-ariel"
        # Already linked to this episode -> no mention bump, no body append.
        index = {key: self._cur("pg-1", "ep-1")}
        nb._upsert_entity(client, self._entity(is_guest=False), index, "ep-1", None,
                          has_guest=True)
        _, kwargs = client.pages.update.call_args
        self.assertNotIn("Guest", kwargs["properties"])   # false must NOT clear

        client.reset_mock()
        index = {key: self._cur("pg-1", "ep-1")}
        nb._upsert_entity(client, self._entity(is_guest=True), index, "ep-1", None,
                          has_guest=True)
        _, kwargs = client.pages.update.call_args
        self.assertEqual(kwargs["properties"]["Guest"], {"checkbox": True})

    def test_create_writes_definite_bool(self):
        client = MagicMock()
        client.pages.create.return_value = {"id": "new-pg"}
        nb._upsert_entity(client, self._entity(is_guest=False), {}, "ep-1", None,
                          has_guest=True)
        _, kwargs = client.pages.create.call_args
        self.assertEqual(kwargs["properties"]["Guest"], {"checkbox": False})

    def test_guest_absent_when_ds_lacks_property(self):
        client = MagicMock()
        client.pages.create.return_value = {"id": "new-pg"}
        nb._upsert_entity(client, self._entity(is_guest=True), {}, "ep-1", None,
                          has_guest=False)
        _, kwargs = client.pages.create.call_args
        self.assertNotIn("Guest", kwargs["properties"])

    def test_merge_ors_is_guest_across_duplicates(self):
        # Same canonical_key twice in one episode, is_guest=False FIRST: the merge
        # must OR the flag so the guest isn't silently dropped (matches the
        # notability strongest-signal rule).
        ents = [self._entity(canonical_key="k", is_guest=False),
                self._entity(canonical_key="k", is_guest=True)]
        merged = extract._merge_within_episode(ents)
        self.assertEqual(len(merged), 1)
        self.assertIs(merged[0]["is_guest"], True)


class SuggestedCategoryGuardrail(unittest.TestCase):
    """suggested_category is the misfit signal for the taxonomy-review loop: kept
    (normalized) ONLY on `other` entities, cleared everywhere else."""

    def _entity(self, **over):
        e = {"name": "X", "canonical_key": "x", "type": "other", "notability": 3,
             "mentioned_by": [], "sentiment": "neutral", "is_tool": False, "is_guest": False}
        e.update(over)
        return e

    def _validate_one(self, **over):
        obj = {"summary": "s", "headline": "h", "entities": [self._entity(**over)]}
        return extract._validate(obj)["entities"][0]

    def test_kept_and_normalized_on_other(self):
        out = self._validate_one(type="other", suggested_category="AI Model")
        self.assertEqual(out["suggested_category"], "ai_model")   # lowercased, slugged

    def test_cleared_on_a_real_type(self):
        out = self._validate_one(type="concept", suggested_category="ai_model")
        self.assertIsNone(out["suggested_category"])              # only `other` proposes

    def test_absent_defaults_to_none(self):
        out = self._validate_one(type="other")
        self.assertIsNone(out["suggested_category"])


class ModelSingleSourceGuardrail(unittest.TestCase):
    """The extraction model resolves from config.EXTRACTION_MODEL only."""

    def test_extract_model_is_config_value(self):
        import config
        self.assertEqual(extract.MODEL, config.EXTRACTION_MODEL)

    def test_auto_review_uses_config_model(self):
        import auto_review
        import config
        self.assertEqual(auto_review.MODEL, config.EXTRACTION_MODEL)

    def test_resolver_model_is_config_value(self):
        import config
        import resolve_entities
        self.assertEqual(resolve_entities.RESOLVE_MODEL, config.RESOLVE_MODEL)


class ResolverFailOpenGuardrail(unittest.TestCase):
    """The resolution pass must never break the pipeline: any failure returns the
    entities untouched, and a show without a resolve.txt skips it entirely."""

    def test_resolver_failure_returns_entities_unchanged(self):
        import resolve_entities
        ents = [{"name": "X", "canonical_key": "x", "type": "concept"}]
        original = resolve_entities._candidates_for
        had_key = os.environ.get("GOOGLE_API_KEY")
        # A key must be present or resolve() short-circuits before the guarded block —
        # we want to prove the try/except itself swallows a mid-flight failure.
        os.environ["GOOGLE_API_KEY"] = "test-key-not-used"
        resolve_entities._candidates_for = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("boom"))
        try:
            out, notes = resolve_entities.resolve(ents, {}, client=object())
        finally:
            resolve_entities._candidates_for = original
            if had_key is None:
                del os.environ["GOOGLE_API_KEY"]
            else:
                os.environ["GOOGLE_API_KEY"] = had_key
        self.assertEqual(out, ents)
        self.assertEqual(notes, [])

    def test_empty_entities_short_circuit(self):
        import resolve_entities
        self.assertEqual(resolve_entities.resolve([], {}), ([], []))


class TranslitIsShowDrivenGuardrail(unittest.TestCase):
    """Romanization comes from the show config, not hardcoded tables — so a
    Latin-script show is unaffected and a non-Latin show can dedup cross-script."""

    def test_latin_names_pass_through(self):
        import entity_match as em
        self.assertEqual(em.translit_normalize("Nvidia"), "nvidia")

    def test_romanization_uses_show_map(self):
        import entity_match as em
        if extract.SHOW.translit_singles:
            # A native-script name must romanize to something Latin (fuzzy-reachable).
            self.assertNotEqual(em.translit_normalize("אנבידיה"), "אנבידיה")
        else:
            self.assertEqual(em._SCRIPT_RE, None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
