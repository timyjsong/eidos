import unittest

from core import budget as budgets
from core import permissions, state_machine
from core.orchestrator import Orchestrator, WorkerResult, launch_product
from core.schemas import KnowledgeRecord, Opportunity
from core.store import Store


class StubWorker:
    worker_type = "stub"
    model = "stub"
    action = "do_stub_things"
    required_tier = 1
    cost_estimate = 0.25

    def __init__(self, output=None):
        self.output = output or {"discovery": {"clusters": ["c1"]}}

    def run(self, opp):
        return WorkerResult(output=self.output, cost_usd=0.2, tokens_in=10, tokens_out=5)


class ExplodingWorker(StubWorker):
    def run(self, opp):
        raise RuntimeError("boom")


class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        permissions.register_policy(self.store, "stub", 1, ["do_stub_things"])
        self.budget = budgets.create_budget(self.store, "research", 10.0)
        self.orch = Orchestrator(self.store, self.budget.id)
        self.opp = Opportunity(title="t")
        self.store.save_opportunity(self.opp)

    def test_step_advances_and_settles_actual(self):
        self.orch.register("DISCOVERED", StubWorker(), "TRIAGED")
        status = self.orch.step(self.opp.id)
        self.assertEqual(status, "TRIAGED")
        opp = self.store.get_opportunity(self.opp.id)
        self.assertEqual(opp.discovery["clusters"], ["c1"])  # merged by the platform
        runs = self.store.list_runs(opportunity_id=self.opp.id)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].status, "COMPLETED")
        self.assertEqual(runs[0].cost_usd, 0.2)
        # books hold the settled actual, not the estimate
        self.assertAlmostEqual(budgets.consumed(self.store, self.budget.id), 0.2)

    def test_no_route_is_a_gate(self):
        self.assertIsNone(self.orch.step(self.opp.id))
        self.assertEqual(self.store.get_opportunity(self.opp.id).status, "DISCOVERED")

    def test_budget_blocks_before_work(self):
        small = budgets.create_budget(self.store, "tiny", 0.1)
        orch = Orchestrator(self.store, small.id)
        orch.register("DISCOVERED", StubWorker(), "TRIAGED")
        with self.assertRaises(budgets.BudgetExceeded):
            orch.step(self.opp.id)
        self.assertEqual(self.store.get_opportunity(self.opp.id).status, "DISCOVERED")
        runs = self.store.list_runs(opportunity_id=self.opp.id)
        self.assertEqual(runs[0].status, "FAILED")
        self.assertEqual(budgets.consumed(self.store, small.id), 0.0)

    def test_worker_failure_settles_zero(self):
        self.orch.register("DISCOVERED", ExplodingWorker(), "TRIAGED")
        with self.assertRaises(RuntimeError):
            self.orch.step(self.opp.id)
        runs = self.store.list_runs(opportunity_id=self.opp.id)
        self.assertEqual(runs[0].status, "FAILED")
        self.assertEqual(budgets.consumed(self.store, self.budget.id), 0.0)
        self.assertEqual(self.store.get_opportunity(self.opp.id).status, "DISCOVERED")

    def test_permission_blocks_before_run(self):
        worker = StubWorker()
        worker.required_tier = 6
        self.orch.register("DISCOVERED", worker, "TRIAGED")
        with self.assertRaises(permissions.PermissionDenied):
            self.orch.step(self.opp.id)
        self.assertEqual(self.store.list_runs(opportunity_id=self.opp.id), [])

    def test_worker_recommended_transition_still_validated(self):
        self.orch.register("DISCOVERED", StubWorker(output={"transition_to": "LAUNCHED"}),
                           "TRIAGED")
        with self.assertRaises(state_machine.InvalidTransition):
            self.orch.step(self.opp.id)
        self.assertEqual(self.store.get_opportunity(self.opp.id).status, "DISCOVERED")

    def test_knowledge_persisted_and_run_output_json_pure(self):
        record = KnowledgeRecord(type="t", source="s", content="c")
        self.orch.register("DISCOVERED", StubWorker(output={"knowledge": [record]}),
                           "TRIAGED")
        self.orch.step(self.opp.id)
        self.assertEqual(self.store.get_knowledge(record.id).content, "c")
        run = self.store.list_runs(opportunity_id=self.opp.id)[0]
        self.assertEqual(run.output["knowledge"], [record.id])

    def test_validation_output_merges(self):
        opp = Opportunity(title="v", status="APPROVED")
        self.store.save_opportunity(opp)
        self.orch.register("APPROVED", StubWorker(
            output={"validation": {"problem": True}}), "VALIDATED")
        self.orch.step(opp.id)
        merged = self.store.get_opportunity(opp.id)
        self.assertTrue(merged.validation["problem"])
        self.assertIsNone(merged.validation["market"])

    def test_pipeline_halts_at_human_gate(self):
        self.orch.register("DISCOVERED", StubWorker(), "TRIAGED")
        trace = self.orch.run_pipeline(self.opp.id)
        self.assertEqual(trace, ["TRIAGED"])

    def test_launch_creates_product_with_provenance(self):
        opp = Opportunity(title="launchable", status="READY")
        self.store.save_opportunity(opp)
        product = launch_product(self.store, opp, "venue_1", actor="human:tim")
        self.assertEqual(opp.status, "LAUNCHED")
        stored = self.store.get_product(product.id)
        self.assertEqual(stored.opportunity_id, opp.id)
        self.assertEqual(stored.target_venue, "venue_1")
        self.assertEqual(len(self.store.events_of_type("PRODUCT_LAUNCHED", product.id)), 1)


if __name__ == "__main__":
    unittest.main()
