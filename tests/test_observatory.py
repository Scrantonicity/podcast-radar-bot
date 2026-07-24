"""test_observatory.py — the observatory builds, gates, and escapes correctly.

All offline: no network, no keys, no Notion. Everything runs against the synthetic
archive in tests/fixtures/observatory/ (see its generate.py), because the real
extractions/ cache is gitignored and empty on a fresh clone.

Run:  SHOW=demo PYTHONPATH=. ./venv/bin/python -m unittest tests.test_observatory -v

What's actually protected here:
  * the gates — a section with too little data must hide, not render empty
  * the escaping — the archive is written by an LLM and the page gets published
  * the theming seam — a literal color below :root silently ignores a show's theme
  * the copy seam — a literal string in the template is one a show can't translate
  * the defaults — a show with no observatory.py must still build
"""

import glob
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SHOW", "demo")

from observatory import assemble, stats as stats_mod
from observatory.defaults import resolve
from show_loader import SHOW, OBSERVATORY

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures", "observatory")
TEMPLATE = os.path.join(os.path.dirname(HERE), "observatory", "template.html")


def load_fixture_episodes():
    eps = [json.load(open(p, encoding="utf-8"))
           for p in sorted(glob.glob(os.path.join(FIXTURES, "extractions", "*.json")))]
    assert eps, f"no fixtures in {FIXTURES}"
    return eps


def load_fixture_transcripts():
    return {os.path.basename(p)[:-4]: open(p, encoding="utf-8").read()
            for p in sorted(glob.glob(os.path.join(FIXTURES, "transcripts", "*.txt")))}


def compute(episodes=None, transcripts=None, obs=None):
    episodes = load_fixture_episodes() if episodes is None else episodes
    transcripts = load_fixture_transcripts() if transcripts is None else transcripts
    obs = obs or resolve(SHOW, OBSERVATORY, n_episodes=len(episodes))
    return stats_mod.compute(episodes, transcripts, SHOW, obs)


class StatsShape(unittest.TestCase):
    """The STATS object the template reads."""

    @classmethod
    def setUpClass(cls):
        cls.stats, cls.report = compute()

    def test_every_top_level_key_present(self):
        expected = {
            "totals", "places", "arcs", "books", "concepts", "timeline",
            "superlatives", "funfacts", "content", "words", "host_face",
            "leaderboard", "tickers", "notab_hist", "spark", "spark_nums",
            "shoutouts", "graph", "sections",
        }
        self.assertEqual(expected - self.stats.keys(), set())

    def test_totals_are_keyed_by_the_shows_own_types(self):
        # Nothing may assume the default taxonomy — a show can redefine it.
        self.assertEqual(set(self.stats["totals"]["by_type"]) - set(SHOW.entity_types), set())

    def test_mentions_count_episodes_not_utterances(self):
        # israel is named in 3 of the 8 fixture episodes (ep1, ep5, ep8).
        israel = next(p for p in self.stats["places"] if p["key"] == "israel")
        self.assertEqual(israel["mentions"], 3)
        self.assertEqual(len(israel["episodes"]), 3)

    def test_unnumbered_episode_sorts_last_not_as_zero(self):
        numbers = [t["number"] for t in self.stats["timeline"]]
        self.assertIsNone(numbers[-1])
        self.assertEqual(numbers[:-1], sorted(n for n in numbers if n is not None))

    def test_guest_is_excluded_from_host_attribution(self):
        # The guest label is not a regular host; their mentions must not be compared.
        self.assertNotIn(SHOW.guest_label, self.stats["superlatives"]["host_counts"])

    def test_notability_histogram_matches_the_1_to_5_contract(self):
        self.assertEqual(len(self.stats["notab_hist"]), 5)
        self.assertEqual(sum(self.stats["notab_hist"]), self.stats["totals"]["entities"])

    def test_ungeocoded_places_are_reported_not_dropped_silently(self):
        # The demo show geocodes both invented places via extra_place_coords, so the
        # report is empty here — prove the mechanism with a bare Observatory instead.
        from showkit import Observatory
        _stats, report = compute(obs=resolve(SHOW, Observatory(), n_episodes=8))
        keys = dict(report["ungeocoded"])
        self.assertIn("spice islands", keys)
        self.assertIn("lower silicon valley", keys)

    def test_facts_carry_no_prose_from_python(self):
        # Python emits numbers; the show's copy supplies the sentence. If a builder
        # ever returns a caption, the "never a stale number" guarantee is gone.
        for f in self.stats["funfacts"]:
            self.assertIn("value", f)
            self.assertTrue(f["cap"], f"fact {f['id']} rendered an empty caption")


class Gates(unittest.TestCase):
    """A section renders only when it has something worth showing."""

    def test_all_sections_on_for_the_full_fixture_archive(self):
        stats, _ = compute()
        for name in ("globe", "library", "records", "funfacts", "hostface",
                     "leaders", "cloud", "pulse", "wordlab", "graph"):
            self.assertTrue(stats["sections"][name], f"{name} should render")

    def test_shoutouts_off_unless_the_show_writes_them(self):
        stats, _ = compute()
        self.assertFalse(stats["sections"]["shoutouts"])

    def test_globe_hides_without_enough_placed_dots(self):
        eps = load_fixture_episodes()
        for ep in eps:
            ep["entities"] = [e for e in ep["entities"] if e["type"] != "place"]
        stats, _ = compute(episodes=eps)
        self.assertFalse(stats["sections"]["globe"])

    def test_hostface_hides_when_attribution_is_blank(self):
        # extract.py blanks mentioned_by when diarization is unreliable. A two-host
        # show would otherwise render two zero-length bars.
        eps = load_fixture_episodes()
        for ep in eps:
            for e in ep["entities"]:
                e["mentioned_by"] = []
        stats, _ = compute(episodes=eps)
        self.assertFalse(stats["sections"]["hostface"])
        self.assertEqual(stats["host_face"]["hosts"], [])

    def test_hostface_hides_with_only_one_host_having_data(self):
        eps = load_fixture_episodes()
        for ep in eps:
            for e in ep["entities"]:
                e["mentioned_by"] = [SHOW.hosts[0]] if e["mentioned_by"] else []
        stats, _ = compute(episodes=eps)
        self.assertFalse(stats["sections"]["hostface"])

    def test_no_transcripts_drops_word_blocks_but_keeps_the_ticker_wall(self):
        stats, _ = compute(transcripts={})
        self.assertIsNone(stats["words"])
        self.assertFalse(stats["sections"]["wordlab_words"])
        self.assertTrue(stats["sections"]["wordlab_tickers"])
        self.assertTrue(stats["sections"]["wordlab"])

    def test_transcripts_are_matched_by_guid_not_globbed(self):
        # extractions/ and transcripts/ are shared across shows in one checkout;
        # a blind glob would count another podcast's words.
        stats, _ = compute()
        self.assertEqual(stats["words"]["episodes_covered"], 2)

    def test_graph_thresholds_scale_to_a_small_archive(self):
        # At a fixed weight-3 floor an 8-episode archive has zero edges.
        obs = resolve(SHOW, OBSERVATORY, n_episodes=8)
        self.assertEqual(obs.graph_min_edge_weight, 1)
        self.assertEqual(resolve(SHOW, OBSERVATORY, n_episodes=65).graph_min_edge_weight, 3)

    def test_empty_archive_raises_a_clear_error_not_a_valueerror(self):
        with self.assertRaises(ValueError) as ctx:
            compute(episodes=[])
        self.assertIn("no episodes", str(ctx.exception))


class Defaults(unittest.TestCase):
    """A show that never writes observatory.py still gets a coherent page."""

    def test_resolve_is_total(self):
        obs = resolve(SHOW, None, n_episodes=8)
        optional = {"signature_words", "laugh_pattern", "shoutout_entries"}
        import dataclasses
        empty = [f.name for f in dataclasses.fields(obs.copy)
                 if f.name not in optional and not getattr(obs.copy, f.name)]
        self.assertEqual(empty, [], f"unset after resolve(): {empty}")

    def test_defaults_derive_from_the_show_config(self):
        obs = resolve(SHOW, None, n_episodes=8)
        self.assertEqual(obs.copy.lang, SHOW.stt_language)
        self.assertEqual(obs.copy.text_direction, SHOW.text_direction)
        # Type labels come free from the show's existing Notion labels, emoji stripped.
        self.assertEqual(obs.copy.type_labels["person"], "אנשים")
        self.assertEqual(set(obs.copy.type_labels), set(SHOW.entity_types))

    def test_builds_with_no_observatory_file(self):
        stats, _ = compute(obs=resolve(SHOW, None, n_episodes=8))
        html = assemble.build(stats, SHOW, resolve(SHOW, None, n_episodes=8),
                              with_vendor=False)
        self.assertIn("<!doctype html>", html)


class Assembly(unittest.TestCase):
    """Injection into the template."""

    @classmethod
    def setUpClass(cls):
        cls.obs = resolve(SHOW, OBSERVATORY, n_episodes=8)
        cls.stats, _ = compute(obs=cls.obs)
        cls.html = assemble.build(cls.stats, SHOW, cls.obs, with_vendor=False)

    def test_no_placeholder_survives(self):
        left = re.findall(r"__[A-Z_]+__", self.html)
        self.assertEqual(left, [], f"unfilled: {set(left)}")

    def test_lang_and_dir_come_from_the_show(self):
        self.assertIn('<html lang="he" dir="rtl">', self.html)

    def test_root_css_emits_a_color_per_entity_type(self):
        css = assemble.root_css(self.obs.theme, SHOW.entity_types)
        for t in SHOW.entity_types:
            self.assertIn(f"--c-{t}:", css)

    def test_script_terminator_is_escaped_in_every_json_blob(self):
        """An LLM-written one_liner containing "</script>" would close the tag early
        and dump the rest of the data as markup. The fixture ships exactly that."""
        self.assertIn("</script>", json.dumps(self.stats, ensure_ascii=False))
        # The blob carrying STATS/COPY/SECTIONS/THEME must contain no raw terminator
        # other than its own.
        blob = re.search(r"<script>const WORLD=.*?</script>", self.html, re.S).group(0)
        self.assertEqual(blob.count("</script>"), 1, "a data string closed the tag early")
        self.assertIn("<\\/script>", blob, "the fixture's tag should arrive escaped")

    def test_escape_applies_to_copy_too_not_just_stats(self):
        # The original build guarded only the stats blob; copy is authored but gets
        # the same treatment, since it's just as capable of carrying "</script>".
        self.assertEqual(assemble._json({"x": "</script>"}), '{"x":"<\\/script>"}')


class Escaping(unittest.TestCase):
    """The archive is model-written and the page gets published."""

    def test_fixture_ships_the_xss_probes(self):
        # If these ever vanish from the fixtures, the tests below prove nothing.
        eps = load_fixture_episodes()
        ents = [e for ep in eps for e in ep["entities"]]
        self.assertTrue(any("<script>" in (e.get("one_liner") or "") for e in ents))
        self.assertTrue(any((e.get("link") or "").startswith("javascript:") for e in ents))

    def test_template_escapes_every_interpolation_by_default(self):
        src = open(TEMPLATE, encoding="utf-8").read()
        # The tagged template `h` escapes; a bare `${}` in innerHTML would not.
        self.assertIn("const h=(strs,...vals)=>", src)
        self.assertIn("const esc=s=>", src)
        self.assertIn("const safeHref=u=>", src)

    def test_only_authored_html_is_inserted_raw(self):
        """Copy may carry markup (a wordmark needs a <span>); the archive may not.
        Exactly three Copy fields go in raw, and each is named _html to say so."""
        src = open(TEMPLATE, encoding="utf-8").read()
        # The trailing ";" matters: it means the Copy value is assigned AS IS. A
        # chained "...=C.footer.links.map(...)" is escaped downstream by `h`.
        raw = sorted(set(re.findall(r"\.innerHTML=(C\.[\w.]+);", src)))
        self.assertEqual(raw, ["C.footer.logo_html", "C.hero.lead_html",
                               "C.hero.title_html"])
        for field in raw:
            self.assertTrue(field.endswith("_html"), f"{field} is raw but unnamed as such")


class TemplateHygiene(unittest.TestCase):
    """The two rules that keep the template a template."""

    @classmethod
    def setUpClass(cls):
        cls.src = open(TEMPLATE, encoding="utf-8").read()
        cls.below_root = cls.src.split("__ROOT_CSS__", 1)[1]

    def test_no_literal_colors_below_root(self):
        """A hardcoded color is one the show's theme can't reach."""
        hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", self.below_root)
        # Allowed: black/white in a mask (opacity, not color) and a cssv() fallback.
        allowed = {"#000", "#fff"}
        self.assertEqual(set(hexes) - allowed, set(), f"literal hex: {set(hexes) - allowed}")

        rgbs = [m for m in re.findall(r"rgba?\([^)]*\)", self.below_root)
                if "${" not in m  # built from CSS variables at runtime — that's the seam
                and not re.match(r"rgba?\(\s*(0\s*,\s*0\s*,\s*0|255\s*,\s*255\s*,\s*255)\s*[,)]", m)]
        self.assertEqual(rgbs, [], f"colored rgb() literals: {rgbs}")

    def test_no_user_facing_words_in_the_template(self):
        """Every string is a lookup into C. A literal here is untranslatable."""
        hebrew = re.findall(r"[֐-׿]+", self.src)
        self.assertEqual(hebrew, [], f"literal Hebrew: {hebrew}")

    def test_template_is_a_valid_standalone_document(self):
        self.assertTrue(self.src.startswith("<!doctype html>"))
        self.assertIn("</html>", self.src)


if __name__ == "__main__":
    unittest.main()
