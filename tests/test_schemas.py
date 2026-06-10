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
        self.assertEqual(opp.schema_version, 3)
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
        opp.scores["pain"] = Score(value=7.0, confidence=0.8,
                                   estimate="weekly blocker for Pro-plan teams",
                                   evidence=["know_1"])
        doc = json.loads(json.dumps(opp.to_doc()))
        back = Opportunity.from_doc(doc)
        self.assertEqual(back.id, opp.id)
        self.assertEqual(back.directive_id, "dir_1")
        self.assertIsInstance(back.scores["pain"], Score)
        self.assertEqual(back.scores["pain"].evidence, ["know_1"])
        self.assertEqual(back.scores["pain"].estimate, "weekly blocker for Pro-plan teams")

    def test_venue_round_trip(self):
        venue = Venue(name="Shopify App Store", kind="marketplace",
                      profile={"distribution": {"m": 1}, "monetization": {},
                               "gatekeeping": {}, "cost_benchmarks": {}})
        back = Venue.from_doc(json.loads(json.dumps(venue.to_doc())))
        self.assertEqual(back.profile["distribution"], {"m": 1})


class TestMigrations(unittest.TestCase):
    def _opp_doc(self, version):
        doc = json.loads(json.dumps(Opportunity(title="x").to_doc()))
        doc["schema_version"] = version
        return doc

    def test_v2_opportunity_loads_and_resaves_at_current_version(self):
        back = Opportunity.from_doc(self._opp_doc(2))
        self.assertEqual(back.schema_version, 3)
        self.assertEqual(back.to_doc()["schema_version"], 3)

    def test_missing_migration_step_raises_clear_error(self):
        with self.assertRaises(ValueError) as ctx:
            Opportunity.from_doc(self._opp_doc(1))
        msg = str(ctx.exception)
        self.assertIn("Opportunity", msg)
        self.assertIn("1 -> 2", msg)

    def test_missing_migration_names_each_model(self):
        doc = json.loads(json.dumps(
            KnowledgeRecord(type="t", source="s", content="c").to_doc()))
        doc["schema_version"] = 1
        with self.assertRaises(ValueError) as ctx:
            KnowledgeRecord.from_doc(doc)
        self.assertIn("KnowledgeRecord", str(ctx.exception))

    def test_current_version_doc_bypasses_migration_untouched(self):
        doc = self._opp_doc(3)
        snapshot = json.loads(json.dumps(doc))
        back = Opportunity.from_doc(doc)
        self.assertEqual(back.schema_version, 3)
        self.assertEqual(doc, snapshot)

    def test_migration_does_not_mutate_caller_doc(self):
        doc = self._opp_doc(2)
        Opportunity.from_doc(doc)
        self.assertEqual(doc["schema_version"], 2)


if __name__ == "__main__":
    unittest.main()
