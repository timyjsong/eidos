import json
import unittest

from core.schemas import (
    Budget,
    KnowledgeRecord,
    Opportunity,
    PermissionPolicy,
    Score,
    SCORE_DIMENSIONS,
    WorkerRun,
)


class TestSchemas(unittest.TestCase):
    def test_id_prefixes(self):
        self.assertTrue(Opportunity(title="x").id.startswith("opp_"))
        self.assertTrue(Budget(scope="research", allocated=1).id.startswith("budget_"))
        self.assertTrue(WorkerRun(worker_type="w").id.startswith("run_"))

    def test_opportunity_defaults(self):
        opp = Opportunity(title="x")
        self.assertEqual(opp.status, "DISCOVERED")
        self.assertEqual(opp.schema_version, 1)
        self.assertEqual(set(opp.scores), set(SCORE_DIMENSIONS))

    def test_unknown_status_rejected(self):
        with self.assertRaises(ValueError):
            Opportunity(title="x", status="VIBING")

    def test_confidence_bounds(self):
        with self.assertRaises(ValueError):
            Score(confidence=1.5)
        with self.assertRaises(ValueError):
            KnowledgeRecord(type="t", source="s", content="c", confidence=-0.1)
        Score(confidence=0.0)
        Score(confidence=1.0)

    def test_run_status_validated(self):
        with self.assertRaises(ValueError):
            WorkerRun(worker_type="w", status="DAYDREAMING")

    def test_policy_tier_bounds(self):
        with self.assertRaises(ValueError):
            PermissionPolicy(worker_type="w", tier=7)

    def test_negative_budget_rejected(self):
        with self.assertRaises(ValueError):
            Budget(scope="s", allocated=-1)

    def test_opportunity_json_round_trip(self):
        opp = Opportunity(title="x")
        opp.scores["pain"] = Score(value=7.0, confidence=0.8, evidence=["know_1"])
        doc = json.loads(json.dumps(opp.to_doc()))
        back = Opportunity.from_doc(doc)
        self.assertEqual(back.id, opp.id)
        self.assertIsInstance(back.scores["pain"], Score)
        self.assertEqual(back.scores["pain"].value, 7.0)
        self.assertEqual(back.scores["pain"].evidence, ["know_1"])


if __name__ == "__main__":
    unittest.main()
