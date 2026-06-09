"""Spike: run fake opportunities through the governed v0.3 pipeline end to end.

Demonstrates: venue + directive entry, decision-phase lifecycle, human gates,
reserve/settle budgets, the launch seam (opportunity -> product), reopen guard,
hold/resume, and full history reconstruction from events.

All workers are deterministic stubs and live outside core/ on purpose.

Run: .venv/bin/python spike.py  (or python3 spike.py)
"""
import os

from core import budget as budgets
from core import permissions, state_machine
from core.orchestrator import Orchestrator, WorkerResult, launch_product
from core.schemas import Directive, KnowledgeRecord, Opportunity, Venue, now_iso
from core.store import Store

DB = "spike.db"


class StubWorker:
    model = "stub-deterministic"
    cost_estimate = 0.25

    def __init__(self, worker_type, action, required_tier):
        self.worker_type = worker_type
        self.action = action
        self.required_tier = required_tier


class Triage(StubWorker):
    """Classify + vet in one phase; returns knowledge the platform persists."""

    def __init__(self):
        super().__init__("triage_agent", "triage_signals", 1)

    def run(self, opp):
        observed = now_iso()
        records = [
            KnowledgeRecord(type="competitor_observation", source="marketplace_search",
                            content=f"3 weak competitors for '{opp.title}'",
                            tags=["competition"], confidence=0.7, observed_at=observed),
            KnowledgeRecord(type="marketplace_research", source="forum_scrape",
                            content=f"recurring complaints adjacent to '{opp.title}'",
                            tags=["pain"], confidence=0.6, observed_at=observed),
        ]
        return WorkerResult(
            output={"knowledge": records,
                    "discovery": {"clusters": ["seller-productivity"],
                                  "sources": [r.id for r in records]}},
            cost_usd=0.20, tokens_in=2100, tokens_out=300)


class Evaluator(StubWorker):
    def __init__(self):
        super().__init__("evaluator", "score_opportunity", 2)

    def run(self, opp):
        value = 2.0 if "logo" in opp.title.lower() else 7.5
        evidence = list(opp.discovery.get("sources", []))
        scores = {dim: {"value": value, "confidence": 0.6,
                        "rationale": "stub heuristic", "evidence": evidence}
                  for dim in ("pain", "market", "distribution", "cost", "risk")}
        return WorkerResult(output={"scores": scores},
                            cost_usd=0.21, tokens_in=1500, tokens_out=250)


class Validator(StubWorker):
    def __init__(self):
        super().__init__("validator", "validate_opportunity", 1)

    def run(self, opp):
        return WorkerResult(
            output={"validation": {"problem": True, "market": True, "distribution": True}},
            cost_usd=0.20, tokens_in=1200, tokens_out=180)


class Builder(StubWorker):
    def __init__(self):
        super().__init__("builder", "build_product", 3)

    def run(self, opp):
        return WorkerResult(
            output={"execution": {"build_outputs": ["stub: repo + listing draft"]}},
            cost_usd=0.22, tokens_in=3000, tokens_out=900)


class ReleaseChecker(StubWorker):
    def __init__(self):
        super().__init__("release_checker", "check_release_bar", 1)

    def run(self, opp):
        return WorkerResult(
            output={"execution": {"qa_outputs": ["stub: venue release bar passed"]}},
            cost_usd=0.18, tokens_in=900, tokens_out=140)


def banner(text):
    print(f"\n=== {text} " + "=" * max(0, 60 - len(text)))


def main():
    if os.path.exists(DB):
        os.remove(DB)  # spike sandbox only — platform data is never deleted
    store = Store(DB)

    # Governance first.
    for worker_type, action, tier in [
        ("triage_agent", "triage_signals", 1),
        ("evaluator", "score_opportunity", 2),
        ("validator", "validate_opportunity", 1),
        ("builder", "build_product", 3),
        ("release_checker", "check_release_bar", 1),
        ("launch_bot", "publish_listing", 2),  # deliberately under-tiered
    ]:
        permissions.register_policy(store, worker_type, tier, [action])
    research = budgets.create_budget(store, "research", 1.55)

    # Venue-first entry: a venue, a directive, opportunities under it.
    venue = Venue(name="Shopify App Store", kind="marketplace",
                  profile={"distribution": {"mechanic": "store search"},
                           "monetization": {"rev_share": 0.0},
                           "gatekeeping": {"review_days": 5},
                           "cost_benchmarks": {}})
    store.save_venue(venue)
    directive = Directive(prompt="explore seller-productivity gaps on the Shopify App Store",
                          venues=[venue.id], budget_id=research.id)
    store.save_directive(directive)

    orch = Orchestrator(store, research.id)
    orch.register("DISCOVERED", Triage(), "TRIAGED")
    orch.register("TRIAGED", Evaluator(), "EVALUATED")
    orch.register("APPROVED", Validator(), "VALIDATED")
    orch.register("VALIDATED", Builder(), "BUILDING")
    orch.register("BUILDING", ReleaseChecker(), "READY")
    # No routes for EVALUATED or READY: approval and launch are human boundaries.

    opp_a = Opportunity(title="Shopify review-reply autoresponder",
                        directive_id=directive.id, signal_venues=[venue.id])
    opp_b = Opportunity(title="AI logo generator #4912",
                        directive_id=directive.id, signal_venues=[venue.id])
    opp_c = Opportunity(title="Etsy fee calculator",
                        directive_id=directive.id, signal_venues=[venue.id])
    for opp in (opp_a, opp_b, opp_c):
        store.save_opportunity(opp)
        store.emit("OPPORTUNITY_CREATED", "triage_agent", opp.id,
                   {"title": opp.title, "directive_id": directive.id})

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

    banner("Pipeline: A and B run to the human approval gate")
    print(f"A trace: {orch.run_pipeline(opp_a.id)}")
    print(f"B trace: {orch.run_pipeline(opp_b.id)}")

    banner("Human decisions at the gate")
    a = store.get_opportunity(opp_a.id)
    print(f"A pain={a.scores['pain'].value} evidence={a.scores['pain'].evidence}")
    state_machine.transition(store, a, "APPROVED", actor="human:tim", reason="strong scores")
    b = store.get_opportunity(opp_b.id)
    print(f"B pain={b.scores['pain'].value}")
    state_machine.transition(store, b, "REJECTED_LOW_ROI", actor="human:tim",
                             reason="weak scores, saturated niche")

    banner("A: validation -> build -> release bar (halts at READY)")
    print(f"A trace: {orch.run_pipeline(opp_a.id)}")

    banner("Human launches A — the opportunity->product seam")
    a = store.get_opportunity(opp_a.id)
    product = launch_product(store, a, venue.id, actor="human:tim")
    print(f"A -> {a.status}; product {product.id} born with provenance {product.opportunity_id}")

    banner("Reopen guard: a worker may not revive the dead, a human may")
    b = store.get_opportunity(opp_b.id)
    try:
        state_machine.transition(store, b, "TRIAGED", actor="overeager_worker")
    except state_machine.InvalidTransition as e:
        print(f"BLOCKED as expected: {e}")
    state_machine.transition(store, b, "TRIAGED", actor="human:tim",
                             reason="market shifted, revisit")
    print(f"B reopened -> {b.status} (full history retained)")

    banner("C: hold/resume, then the budget ceiling")
    c = store.get_opportunity(opp_c.id)
    state_machine.transition(store, c, "ON_HOLD", actor="portfolio_manager", reason="capacity")
    print(f"C held from {c.held_from} -> {c.status}")
    state_machine.transition(store, c, "DISCOVERED", actor="portfolio_manager", reason="capacity freed")
    print(f"C resumed -> {c.status}")
    try:
        orch.run_pipeline(opp_c.id)
    except budgets.BudgetExceeded as e:
        print(f"BLOCKED as expected: {e}")
    print(f"C status: {store.get_opportunity(opp_c.id).status} (work gated, state intact)")

    banner("Budget report (reserve/settle, derived from events)")
    print(f"allocated={research.allocated} "
          f"consumed={budgets.consumed(store, research.id):.2f} "
          f"remaining={budgets.remaining(store, research.id):.2f} "
          f"(settled actuals, not estimates)")

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

    print(f"\nSpike complete. Durable state in {DB} — inspect with sqlite3 or core.cli --db {DB}.")


if __name__ == "__main__":
    main()
