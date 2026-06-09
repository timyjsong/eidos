import unittest

from core import budget as budgets
from core.store import Store


class TestBudget(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.budget = budgets.create_budget(self.store, "research", 1.0)

    def test_fresh_budget(self):
        self.assertEqual(budgets.consumed(self.store, self.budget.id), 0)
        self.assertEqual(budgets.remaining(self.store, self.budget.id), 1.0)
        self.assertEqual(len(self.store.events_of_type("BUDGET_CREATED", self.budget.id)), 1)

    def test_consumption_is_event_derived(self):
        budgets.spend(self.store, self.budget.id, 0.3, actor="w", run_id="run_1")
        budgets.spend(self.store, self.budget.id, 0.2, actor="w", run_id="run_2")
        self.assertAlmostEqual(budgets.consumed(self.store, self.budget.id), 0.5)
        self.assertAlmostEqual(budgets.remaining(self.store, self.budget.id), 0.5)
        spent = self.store.events_of_type("BUDGET_SPENT", self.budget.id)
        self.assertEqual([e.payload["run_id"] for e in spent], ["run_1", "run_2"])

    def test_overrun_blocked_and_logged(self):
        budgets.spend(self.store, self.budget.id, 0.9, actor="w")
        with self.assertRaises(budgets.BudgetExceeded):
            budgets.spend(self.store, self.budget.id, 0.2, actor="w")
        blocked = self.store.events_of_type("BUDGET_BLOCKED", self.budget.id)
        self.assertEqual(len(blocked), 1)
        self.assertAlmostEqual(blocked[0].payload["remaining"], 0.1)
        # the blocked spend consumed nothing
        self.assertAlmostEqual(budgets.consumed(self.store, self.budget.id), 0.9)

    def test_non_positive_spend_rejected(self):
        with self.assertRaises(ValueError):
            budgets.spend(self.store, self.budget.id, 0, actor="w")
        with self.assertRaises(ValueError):
            budgets.spend(self.store, self.budget.id, -1, actor="w")


if __name__ == "__main__":
    unittest.main()
