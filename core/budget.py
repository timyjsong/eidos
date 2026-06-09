"""Budget governance: allocation stored; consumption event-sourced as reserve/settle.

BUDGET_RESERVED(estimate) gates work before it runs; BUDGET_SETTLED(actual) records
what it really cost (ADR-0003, ADR-0009). Consumed = settled + outstanding reserves.
"""
from . import event_types as ev
from .schemas import Budget


class BudgetExceeded(Exception):
    pass


def create_budget(store, scope, allocated, actor="system"):
    budget = Budget(scope=scope, allocated=allocated)
    store.save_budget(budget)
    store.emit(ev.BUDGET_CREATED, actor, budget.id, {"scope": scope, "allocated": allocated})
    return budget


def _ledger(store, budget_id):
    """run_id -> {reserved, settled(None until settled)} from the event log."""
    ledger = {}
    for e in store.events_of_type(ev.BUDGET_RESERVED, budget_id):
        ledger[e.payload["run_id"]] = {"reserved": e.payload["amount"], "settled": None}
    for e in store.events_of_type(ev.BUDGET_SETTLED, budget_id):
        ledger[e.payload["run_id"]]["settled"] = e.payload["amount"]
    return ledger


def consumed(store, budget_id):
    total = 0.0
    for entry in _ledger(store, budget_id).values():
        total += entry["reserved"] if entry["settled"] is None else entry["settled"]
    return total


def remaining(store, budget_id):
    return store.get_budget(budget_id).allocated - consumed(store, budget_id)


def reserve(store, budget_id, amount, actor, run_id, reason=""):
    """Gate work against the budget. Refused reserve = the work does not happen."""
    if amount <= 0:
        raise ValueError("reserve amount must be positive")
    if run_id in _ledger(store, budget_id):
        raise ValueError(f"run {run_id} already has a reservation")
    left = remaining(store, budget_id)
    if amount > left:
        store.emit(ev.BUDGET_BLOCKED, actor, budget_id,
                   {"amount": amount, "remaining": left, "run_id": run_id, "reason": reason})
        raise BudgetExceeded(f"{budget_id}: {amount} exceeds remaining {left}")
    store.emit(ev.BUDGET_RESERVED, actor, budget_id,
               {"amount": amount, "run_id": run_id, "reason": reason})


def settle(store, budget_id, run_id, actual, actor, reason=""):
    """Record what the work really cost. actual=0 releases a reserve (failed/free run)."""
    if actual < 0:
        raise ValueError("settle amount must be >= 0")
    entry = _ledger(store, budget_id).get(run_id)
    if entry is None:
        raise ValueError(f"run {run_id} has no reservation to settle")
    if entry["settled"] is not None:
        raise ValueError(f"run {run_id} is already settled")
    store.emit(ev.BUDGET_SETTLED, actor, budget_id,
               {"amount": actual, "run_id": run_id, "reason": reason})
