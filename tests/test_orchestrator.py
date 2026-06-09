import unittest

from core import budget as budgets
from core import permissions, state_machine
from core.orchestrator import Orchestrator, WorkerResult
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


class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        permissions.register_policy(self.store, "stub", 1, ["do_stub_things"])
        self.budget = budgets.create_budget(self.store, "research", 10.0)
        self.orch = Orchestrator(self.store, self.budget.id)
        self.opp = Opportunity(title="t")
        self.store.save_opportunity(self.opp)

    def test_step_advances_and_records_run(self):
        self.orch.register("DISCOVERED", StubWorker(), "CLASSIFIED")
        status = self.orch.step(self.opp.id)
        self.assertEqual(status, "CLASSIFIED")
        opp = self.store.get_opportunity(self.opp.id)
        self.assertEqual(opp.discovery["clusters"], ["c1"])  # merged by the platform
        runs = self.store.list_runs(opportunity_id=self.opp.id)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].status, "COMPLETED")
        self.assertEqual(runs[0].cost_usd, 0.2)
        spent = self.store.events_of_type("BUDGET_SPENT", self.budget.id)
        self.assertEqual(spent[0].payload["run_id"], runs[0].id)

    def test_no_route_is_a_gate(self):
        self.assertIsNone(self.orch.step(self.opp.id))
        self.assertEqual(self.store.get_opportunity(self.opp.id).status, "DISCOVERED")

    def test_budget_blocks_before_work(self):
        small = budgets.create_budget(self.store, "tiny", 0.1)
        orch = Orchestrator(self.store, small.id)
        orch.register("DISCOVERED", StubWorker(), "CLASSIFIED")
        with self.assertRaises(budgets.BudgetExceeded):
            orch.step(self.opp.id)
        self.assertEqual(self.store.get_opportunity(self.opp.id).status, "DISCOVERED")
        runs = self.store.list_runs(opportunity_id=self.opp.id)
        self.assertEqual(runs[0].status, "FAILED")

    def test_permission_blocks_before_run(self):
        worker = StubWorker()
        worker.required_tier = 6
        self.orch.register("DISCOVERED", worker, "CLASSIFIED")
        with self.assertRaises(permissions.PermissionDenied):
            self.orch.step(self.opp.id)
        self.assertEqual(self.store.list_runs(opportunity_id=self.opp.id), [])

    def test_worker_recommended_transition_still_validated(self):
        self.orch.register("DISCOVERED", StubWorker(output={"transition_to": "LAUNCHED"}),
                           "CLASSIFIED")
        with self.assertRaises(state_machine.InvalidTransition):
            self.orch.step(self.opp.id)
        self.assertEqual(self.store.get_opportunity(self.opp.id).status, "DISCOVERED")

    def test_knowledge_output_persisted_by_platform(self):
        record = KnowledgeRecord(type="t", source="s", content="c")
        self.orch.register("DISCOVERED", StubWorker(output={"knowledge": [record]}),
                           "CLASSIFIED")
        self.orch.step(self.opp.id)
        self.assertEqual(self.store.get_knowledge(record.id).content, "c")
        self.assertEqual(len(self.store.events_of_type("KNOWLEDGE_ADDED", record.id)), 1)

    def test_pipeline_halts_at_human_gate(self):
        self.orch.register("DISCOVERED", StubWorker(), "CLASSIFIED")
        # nothing registered for CLASSIFIED -> human gate
        trace = self.orch.run_pipeline(self.opp.id)
        self.assertEqual(trace, ["CLASSIFIED"])


if __name__ == "__main__":
    unittest.main()
