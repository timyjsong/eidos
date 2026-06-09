import json
import unittest

from pydantic import ValidationError

from core.schemas import (
    Budget,
    Directive,
    KnowledgeRecord,
    Opportunity,
    PermissionPolicy,
    Score,
    SCORE_DIMENSIONS,
    Venue,
    WorkerRun,
)


class TestSchemas(unittest.TestCase):
    def test_id_prefixes(self):
        self.assertTrue(Opportunity(title="x").id.startswith("opp_"))
        self.assertTrue(Budget(scope="research", allocated=1).id.startswith("budget_"))
        self.assertTrue(WorkerRun(worker_type="w").id.startswith("run_"))
        self.assertTrue(Venue(name="v").id.startswith("venue_"))
        self.assertTrue(Directive(prompt="p").id.startswith("dir_"))

    def test_opportunity_defaults(self):
        opp = Opportunity(title="x")
        self.assertEqual(opp.status, "DISCOVERED")
        self.assertEqual(opp.schema_version, 2)
        self.assertIsNone(opp.directive_id)
        self.assertIsNone(opp.held_from)
        self.assertEqual(set(opp.scores), set(SCORE_DIMENSIONS))
        self.assertEqual(opp.validation, {"problem": None, "market": None, "distribution": None})

    def test_unknown_status_rejected(self):
        with self.assertRaises(ValidationError):
            Opportunity(title="x", status="VIBING")
        with self.assertRaises(ValidationError):
            Opportunity(title="x", status="CLASSIFIED")  # v0.1 state, gone in v0.3

    def test_confidence_bounds(self):
        with self.assertRaises(ValidationError):
            Score(confidence=1.5)
        with self.assertRaises(ValidationError):
            KnowledgeRecord(type="t", source="s", content="c", confidence=-0.1)
        Score(confidence=0.0)
        Score(confidence=1.0)

    def test_run_status_validated(self):
        with self.assertRaises(ValidationError):
            WorkerRun(worker_type="w", status="DAYDREAMING")

    def test_policy_tier_bounds(self):
        with self.assertRaises(ValidationError):
            PermissionPolicy(worker_type="w", tier=7)

    def test_negative_budget_rejected(self):
        with self.assertRaises(ValidationError):
            Budget(scope="s", allocated=-1)

    def test_directive_validation(self):
        with self.assertRaises(ValidationError):
            Directive(prompt="p", cadence="hourly")
        with self.assertRaises(ValidationError):
            Directive(prompt="p", status="PONDERING")

    def test_opportunity_json_round_trip(self):
        opp = Opportunity(title="x", directive_id="dir_1", signal_venues=["venue_1"])
        opp.scores["pain"] = Score(value=7.0, confidence=0.8, evidence=["know_1"])
        doc = json.loads(json.dumps(opp.to_doc()))
        back = Opportunity.from_doc(doc)
        self.assertEqual(back.id, opp.id)
        self.assertEqual(back.directive_id, "dir_1")
        self.assertIsInstance(back.scores["pain"], Score)
        self.assertEqual(back.scores["pain"].evidence, ["know_1"])

    def test_venue_round_trip(self):
        venue = Venue(name="Shopify App Store", kind="marketplace",
                      profile={"distribution": {"m": 1}, "monetization": {},
                               "gatekeeping": {}, "cost_benchmarks": {}})
        back = Venue.from_doc(json.loads(json.dumps(venue.to_doc())))
        self.assertEqual(back.profile["distribution"], {"m": 1})


if __name__ == "__main__":
    unittest.main()
