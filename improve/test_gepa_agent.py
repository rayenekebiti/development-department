"""Tests for the GEPA scorer and constraint gate. No model calls.

  python3 -m unittest discover -s improve
"""
import json
import sys
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    import gepa  # noqa: F401
except ImportError:  # the scorer and gate don't need it
    adapter = types.ModuleType("gepa.core.adapter")
    adapter.EvaluationBatch = object
    sys.modules.update({"gepa": types.ModuleType("gepa"), "gepa.core": types.ModuleType("gepa.core"),
                        "gepa.core.adapter": adapter})

import gepa_agent as g  # noqa: E402

SPEC = json.loads((HERE / "tasks" / "codebase-scout.json").read_text())
TASKS = SPEC["train"] + SPEC["val"]
FIXTURE = HERE / SPEC["repo"]
AGENTS = HERE.parent / "agents"

EXPECTED = [["shop/pricing.py:4"], ["shop/orders.py:8"]]
ALLOWED = ["shop/orders.py:2"]


def score(text, expected=EXPECTED, allowed=ALLOWED):
    return g.score_output(text, expected, allowed)[0]


class Scorer(unittest.TestCase):
    def test_exact_answer_scores_full(self):
        self.assertEqual(score("Defined at shop/pricing.py:4, called at `shop/orders.py:8`."), 1.0)

    def test_listing_every_line_scores_near_zero(self):
        files = ["api", "config", "events", "orders", "pricing"]
        shotgun = " ".join(f"shop/{f}.py:{n}" for f in files for n in range(1, 25))
        for t in TASKS:
            with self.subTest(t["id"]):
                self.assertLess(score(shotgun, t["expected"], t.get("allowed", [])), 0.2)

    def test_a_wrong_citation_lowers_the_score(self):
        s = score("shop/pricing.py:4 shop/orders.py:8 shop/config.py:5")
        self.assertLess(s, 1.0)
        self.assertGreater(s, 0.5)

    def test_wrong_citations_are_reported(self):
        wrong = g.score_output("shop/pricing.py:4 shop/config.py:5", EXPECTED, ALLOWED)[3]
        self.assertEqual(wrong, ["shop/config.py:5"])

    def test_half_the_answer_scores_less_than_full(self):
        self.assertAlmostEqual(score("shop/pricing.py:4"), 2 / 3)

    def test_allowed_context_costs_nothing(self):
        self.assertEqual(score("shop/orders.py:2 shop/pricing.py:4 shop/orders.py:8"), 1.0)

    def test_allowed_context_alone_earns_nothing(self):
        self.assertEqual(score("shop/orders.py:2"), 0.0)

    def test_no_citations_scores_zero(self):
        self.assertEqual(score("It is in the pricing module."), 0.0)

    def test_repeating_a_location_changes_nothing(self):
        self.assertEqual(score("shop/pricing.py:4 pricing.py:4 shop/orders.py:8 shop/config.py:5"),
                         score("shop/pricing.py:4 shop/orders.py:8 shop/config.py:5"))

    def test_bare_relative_and_absolute_paths_all_count(self):
        for path in ("pricing.py", "./shop/pricing.py", "/tmp/x/fixtures/shop/shop/pricing.py"):
            with self.subTest(path):
                self.assertEqual(score(f"{path}:4", [["shop/pricing.py:4"]]), 1.0)

    def test_wrong_directory_or_line_does_not_count(self):
        for cite in ("legacy/pricing.py:4", "shop/pricing.py:40", "shop/apricing.py:4"):
            with self.subTest(cite):
                self.assertEqual(score(cite, [["shop/pricing.py:4"]]), 0.0)

    def test_a_range_counts_by_its_first_line(self):
        self.assertEqual(score("shop/pricing.py:1-24", [["shop/pricing.py:4"]]), 0.0)
        self.assertEqual(score("shop/pricing.py:4-5", [["shop/pricing.py:4"]]), 1.0)

    def test_every_task_location_is_a_real_line(self):
        for t in TASKS:
            for cite in [o for opts in t["expected"] for o in opts] + t.get("allowed", []):
                with self.subTest(task=t["id"], cite=cite):
                    path, line = cite.rsplit(":", 1)
                    lines = (FIXTURE / path).read_text().splitlines()
                    self.assertTrue(lines[int(line) - 1].strip())


class Gate(unittest.TestCase):
    def setUp(self):
        self.scout = g.split_agent((AGENTS / "codebase-scout.md").read_text())[1]

    def test_every_current_agent_passes_unchanged(self):
        for f in AGENTS.glob("*.md"):
            with self.subTest(f.name):
                body = g.split_agent(f.read_text())[1]
                self.assertEqual(g.gate(body, body), [])

    def test_removing_a_never_rule_is_rejected(self):
        rules = ["You never edit.", "Never run `codegraph init` yourself.", "Never modify files,"]
        for rule in rules:
            with self.subTest(rule):
                self.assertIn(rule, self.scout)
                self.assertTrue(g.gate(self.scout.replace(rule, ""), self.scout))

    def test_removing_all_never_lines_is_rejected(self):
        kept = "\n".join(l for l in self.scout.splitlines() if "never" not in l.lower())
        self.assertTrue(g.gate(kept, self.scout))

    def test_weakening_a_never_rule_is_rejected(self):
        baseline = "## Rules\n\n- Never modify files.\n"
        for weaker in ("- Avoid modifying files.", "- Almost never modify files.",
                       "- Never modify files unless it helps.", "- Never mind. Modify files."):
            with self.subTest(weaker):
                self.assertTrue(g.gate(f"## Rules\n\n{weaker}\n", baseline))

    def test_the_rejection_names_the_missing_rule(self):
        baseline = "## Rules\n\nNever modify files.\n"
        self.assertIn("Never modify files.", " ".join(g.gate("## Rules\n\nBe careful.\n", baseline)))

    def test_rewrapping_and_moving_a_rule_is_accepted(self):
        baseline = "Find code. Never modify files,\ninstall packages or run builds.\n\n## Bash\n\nUse it.\n"
        moved = "Find code fast.\n\n## Bash\nUse it.\n\n- Never modify files, install packages\n  or run builds.\n"
        self.assertEqual(g.gate(moved, baseline), [])

    def test_removed_heading_and_oversize_are_still_rejected(self):
        self.assertTrue(g.gate(self.scout.replace("## Report", "Report"), self.scout))
        self.assertTrue(g.gate(self.scout + "x" * 20000, self.scout))


if __name__ == "__main__":
    unittest.main()
