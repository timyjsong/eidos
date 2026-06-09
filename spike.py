"""Spike: run fake opportunities through the governed pipeline end to end.

Demonstrates every milestone component working together:
state machine, registries, event log, budgets, permissions, worker runs, orchestrator.

All workers here are deterministic stubs and live outside core/ on purpose —
workers are replaceable implementation details.

Run: python3 spike.py
"""
import os

from core import budget as budgets
from core import permissions, state_machine
from core.orchestrator import Orchestrator, WorkerResult
from core.schemas import KnowledgeRecord, Opportunity, now_iso
from core.store import Store

DB = "spike.db"


class StubWorker:
    model = "stub-deterministic"
    cost_estimate = 0.25

    def __init__(self, worker_type, action, required_tier):
        self.worker_type = worker_type
        self.action = action
        self.required_tier = required_tier


class Classifier(StubWorker):
    def __init__(self):
        super().__init__("signal_classifier", "classify_signals", 1)

    def run(self, opp):
        return WorkerResult(
            output={"discovery": {"clusters": ["seller-productivity"]}},
            cost_usd=0.18, tokens_in=900, tokens_out=140,
        )


class Vetter(StubWorker):
    """Returns knowledge records as output; the orchestrator persists them."""

    def __init__(self):
        super().__init__("vetting_agent", "vet_market", 1)

    def run(self, opp):
        observed = now_iso()
        records = [
            KnowledgeRecord(type="competitor_observation", source="marketplace_search",
                            content=f"3 weak competitors found for '{opp.title}'",
                            confidence=0.7, observed_at=observed),
            KnowledgeRecord(type="marketplace_research", source="forum_scrape",
                            content=f"recurring complaints adjacent to '{opp.title}'",
                            confidence=0.6, observed_at=observed),
        ]
        return WorkerResult(
            output={
                "knowledge": records,
                "discovery": {"sources": [r.id for r in records]},
            },
            cost_usd=0.22, tokens_in=2100, tokens_out=300,
        )


class Evaluator(StubWorker):
    """Scores deterministically by title; evidence refs point at vetted knowledge."""

    def __init__(self):
        super().__init__("evaluator", "score_opportunity", 2)

    def run(self, opp):
        weak = "logo" in opp.title.lower()
        value = 2.0 if weak else 7.5
        evidence = list(opp.discovery.get("sources", []))
        scores = {
            dim: {"value": value, "confidence": 0.6,
                  "rationale": "stub heuristic", "evidence": evidence}
            for dim in ("pain", "market", "distribution", "cost", "risk")
        }
        return WorkerResult(output={"scores": scores},
                            cost_usd=0.21, tokens_in=1500, tokens_out=250)


class ProblemValidator(StubWorker):
    def __init__(self):
        super().__init__("problem_validator", "validate_problem", 1)

    def run(self, opp):
        return WorkerResult(
            output={"execution": {"scope": {"problem_validated_note": "stub: pain confirmed"}}},
            cost_usd=0.2, tokens_in=1200, tokens_out=180,
        )


def banner(text):
    print(f"\n=== {text} " + "=" * max(0, 60 - len(text)))


def main():
    if os.path.exists(DB):
        os.remove(DB)  # spike sandbox only — platform data is never deleted
    store = Store(DB)

    # Governance first: policies and a research budget.
    for worker_type, action, tier in [
        ("signal_classifier", "classify_signals", 1),
        ("vetting_agent", "vet_market", 1),
        ("evaluator", "score_opportunity", 2),
        ("problem_validator", "validate_problem", 1),
        ("launch_bot", "publish_listing", 2),  # deliberately under-tiered
    ]:
        permissions.register_policy(store, worker_type, tier, [action])
    research = budgets.create_budget(store, "research", 1.85)

    orch = Orchestrator(store, research.id)
    orch.register("DISCOVERED", Classifier(), "CLASSIFIED")
    orch.register("CLASSIFIED", Vetter(), "VETTED")
    orch.register("VETTED", Evaluator(), "EVALUATED")
    orch.register("APPROVED", ProblemValidator(), "PROBLEM_VALIDATED")
    # No route for EVALUATED: approval is a human boundary, the pipeline halts there.

    opp_a = Opportunity(title="Shopify review-reply autoresponder", platform="shopify")
    opp_b = Opportunity(title="AI logo generator #4912", platform="web")
    opp_c = Opportunity(title="Etsy fee calculator", platform="etsy")
    for opp in (opp_a, opp_b, opp_c):
        store.save_opportunity(opp)
        store.emit("OPPORTUNITY_CREATED", "signal_harvester", opp.id, {"title": opp.title})

    banner("Illegal transition attempt (DISCOVERED -> LAUNCHED)")
    try:
        state_machine.transition(store, store.get_opportunity(opp_a.id), "LAUNCHED",
                                 actor="impatient_worker")
    except state_machine.InvalidTransition as e:
        print(f"BLOCKED as expected: {e}")

    banner("Permission denial (launch_bot, tier 2, attempts a tier-6 action)")
    try:
        permissions.check(store, "launch_bot", "publish_listing", 6)
    except permissions.PermissionDenied as e:
        print(f"DENIED as expected: {e}")

    banner("Pipeline: A and B run until the human approval gate")
    print(f"A trace: {orch.run_pipeline(opp_a.id)}")
    print(f"B trace: {orch.run_pipeline(opp_b.id)}")

    banner("Human decisions at the gate (the primary human decision point)")
    a = store.get_opportunity(opp_a.id)
    print(f"A scores: pain={a.scores['pain'].value} evidence={a.scores['pain'].evidence}")
    state_machine.transition(store, a, "APPROVED", actor="human:tim", reason="strong scores")
    b = store.get_opportunity(opp_b.id)
    print(f"B scores: pain={b.scores['pain'].value}")
    state_machine.transition(store, b, "REJECTED_LOW_ROI", actor="human:tim",
                             reason="weak scores, saturated niche")
    print(f"A -> {a.status}, B -> {b.status}")

    banner("A continues past approval")
    print(f"A trace: {orch.run_pipeline(opp_a.id)}")

    banner("C hits the budget ceiling")
    try:
        orch.run_pipeline(opp_c.id)
    except budgets.BudgetExceeded as e:
        print(f"BLOCKED as expected: {e}")
    print(f"C status: {store.get_opportunity(opp_c.id).status} (work gated, state intact)")

    banner("Budget report (derived from events, not stored)")
    print(f"allocated={research.allocated} "
          f"consumed={budgets.consumed(store, research.id):.2f} "
          f"remaining={budgets.remaining(store, research.id):.2f}")

    banner("Worker runs (every decision has a cost)")
    for run in store.list_runs():
        print(f"{run.worker_type:<18} opp={run.opportunity_id} {run.status:<10}"
              f" ${run.cost_usd:.2f} tokens={run.tokens_in}/{run.tokens_out}")

    banner("A's history, reconstructed purely from the event log")
    for e in store.events_for(opp_a.id):
        detail = ""
        if e.type == "OPPORTUNITY_STATE_CHANGED":
            detail = f" {e.payload['from']} -> {e.payload['to']}"
        elif e.type == "OPPORTUNITY_TRANSITION_BLOCKED":
            detail = f" {e.payload['from']} -x-> {e.payload['to']}"
        print(f"{e.timestamp}  {e.type:<32} actor={e.actor}{detail}")

    banner("Event totals")
    counts = {}
    for e in store.all_events():
        counts[e.type] = counts.get(e.type, 0) + 1
    for event_type, n in sorted(counts.items()):
        print(f"{event_type:<32} {n}")

    print(f"\nSpike complete. Durable state in {DB} — inspect with sqlite3.")


if __name__ == "__main__":
    main()
