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

    def test_reserve_counts_as_consumed_until_settled(self):
        budgets.reserve(self.store, self.budget.id, 0.3, actor="w", run_id="run_1")
        self.assertAlmostEqual(budgets.consumed(self.store, self.budget.id), 0.3)
        budgets.settle(self.store, self.budget.id, "run_1", 0.22, actor="w")
        self.assertAlmostEqual(budgets.consumed(self.store, self.budget.id), 0.22)
        self.assertAlmostEqual(budgets.remaining(self.store, self.budget.id), 0.78)

    def test_settle_zero_releases_reserve(self):
        budgets.reserve(self.store, self.budget.id, 0.3, actor="w", run_id="run_1")
        budgets.settle(self.store, self.budget.id, "run_1", 0.0, actor="w", reason="failed")
        self.assertEqual(budgets.consumed(self.store, self.budget.id), 0.0)

    def test_overrun_blocked_and_logged(self):
        budgets.reserve(self.store, self.budget.id, 0.9, actor="w", run_id="run_1")
        with self.assertRaises(budgets.BudgetExceeded):
            budgets.reserve(self.store, self.budget.id, 0.2, actor="w", run_id="run_2")
        blocked = self.store.events_of_type("BUDGET_BLOCKED", self.budget.id)
        self.assertEqual(len(blocked), 1)
        self.assertAlmostEqual(blocked[0].payload["remaining"], 0.1)
        self.assertAlmostEqual(budgets.consumed(self.store, self.budget.id), 0.9)

    def test_settled_actuals_free_headroom(self):
        budgets.reserve(self.store, self.budget.id, 0.9, actor="w", run_id="run_1")
        budgets.settle(self.store, self.budget.id, "run_1", 0.5, actor="w")
        budgets.reserve(self.store, self.budget.id, 0.4, actor="w", run_id="run_2")  # now fits

    def test_double_settle_rejected(self):
        budgets.reserve(self.store, self.budget.id, 0.3, actor="w", run_id="run_1")
        budgets.settle(self.store, self.budget.id, "run_1", 0.3, actor="w")
        with self.assertRaises(ValueError):
            budgets.settle(self.store, self.budget.id, "run_1", 0.3, actor="w")

    def test_settle_without_reserve_rejected(self):
        with self.assertRaises(ValueError):
            budgets.settle(self.store, self.budget.id, "ghost_run", 0.3, actor="w")

    def test_duplicate_reserve_rejected(self):
        budgets.reserve(self.store, self.budget.id, 0.1, actor="w", run_id="run_1")
        with self.assertRaises(ValueError):
            budgets.reserve(self.store, self.budget.id, 0.1, actor="w", run_id="run_1")

    def test_non_positive_reserve_rejected(self):
        with self.assertRaises(ValueError):
            budgets.reserve(self.store, self.budget.id, 0, actor="w", run_id="run_1")
        with self.assertRaises(ValueError):
            budgets.settle(self.store, self.budget.id, "run_x", -1, actor="w")


if __name__ == "__main__":
    unittest.main()
