"""Budget governance (decisions/0003): allocation stored, consumption event-sourced."""
from .schemas import Budget


class BudgetExceeded(Exception):
    pass


def create_budget(store, scope, allocated, actor="system"):
    budget = Budget(scope=scope, allocated=allocated)
    store.save_budget(budget)
    store.emit("BUDGET_CREATED", actor, budget.id, {"scope": scope, "allocated": allocated})
    return budget


def consumed(store, budget_id):
    return sum(e.payload["amount"] for e in store.events_of_type("BUDGET_SPENT", budget_id))


def remaining(store, budget_id):
    return store.get_budget(budget_id).allocated - consumed(store, budget_id)


def spend(store, budget_id, amount, actor, reason="", run_id=None):
    if amount <= 0:
        raise ValueError("spend amount must be positive")
    left = remaining(store, budget_id)
    if amount > left:
        store.emit("BUDGET_BLOCKED", actor, budget_id,
                   {"amount": amount, "remaining": left, "reason": reason})
        raise BudgetExceeded(f"{budget_id}: {amount} exceeds remaining {left}")
    store.emit("BUDGET_SPENT", actor, budget_id,
               {"amount": amount, "reason": reason, "run_id": run_id})
