"""Orchestrator shell. Deterministic: it owns state, budgets, permissions, transitions.

Workers receive context, do work, return a WorkerResult. They never touch the store,
never own memory, never write state. A worker may *recommend* a transition via
output["transition_to"]; the state machine still validates it.

A worker is any object with: worker_type, model, action, required_tier,
cost_estimate, and run(opportunity) -> WorkerResult.
"""
from dataclasses import dataclass, field

from . import budget as budgets
from . import permissions, state_machine
from .schemas import Score, WorkerRun, now_iso


@dataclass
class WorkerResult:
    output: dict = field(default_factory=dict)
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0


def _merge_output(opp, output):
    """The platform owns state: worker outputs are merged here, never written by workers."""
    if "scores" in output:
        for dim, score in output["scores"].items():
            opp.scores[dim] = score if isinstance(score, Score) else Score(**score)
    for key in ("discovery", "decisions", "execution"):
        if key in output:
            getattr(opp, key).update(output[key])


class Orchestrator:
    """Maps lifecycle states to workers; advances opportunities one governed step at a time."""

    def __init__(self, store, budget_id):
        self.store = store
        self.budget_id = budget_id
        self.routes = {}  # state -> (worker, default next state)

    def register(self, state, worker, next_state):
        self.routes[state] = (worker, next_state)

    def step(self, opp_id):
        """One governed step. Returns the new status, or None when no worker handles
        the current state (a human gate or the end of the registered pipeline)."""
        opp = self.store.get_opportunity(opp_id)
        if opp.status not in self.routes:
            return None
        worker, default_next = self.routes[opp.status]

        permissions.check(self.store, worker.worker_type, worker.action, worker.required_tier)

        run = WorkerRun(worker_type=worker.worker_type, model=worker.model,
                        opportunity_id=opp.id, input_summary=f"status={opp.status}")
        self.store.save_run(run)

        # Budget gates the work: blocked means the worker never runs.
        try:
            budgets.spend(self.store, self.budget_id, worker.cost_estimate,
                          actor=worker.worker_type,
                          reason=f"{worker.worker_type} on {opp.id}", run_id=run.id)
        except budgets.BudgetExceeded:
            run.status = "FAILED"
            run.finished_at = now_iso()
            run.output = {"error": "budget exceeded"}
            self.store.save_run(run)
            raise

        result = worker.run(opp)

        run.status = "COMPLETED"
        run.finished_at = now_iso()
        run.output = result.output
        run.cost_usd = result.cost_usd or worker.cost_estimate
        run.tokens_in, run.tokens_out = result.tokens_in, result.tokens_out
        self.store.save_run(run)

        for record in result.output.get("knowledge", []):
            self.store.save_knowledge(record)
            self.store.emit("KNOWLEDGE_ADDED", worker.worker_type, record.id,
                            {"type": record.type, "source": record.source})

        _merge_output(opp, result.output)
        self.store.save_opportunity(opp)

        next_state = result.output.get("transition_to", default_next)
        state_machine.transition(self.store, opp, next_state, actor=worker.worker_type)
        return opp.status

    def run_pipeline(self, opp_id, max_steps=25):
        """Advance until a human gate, a terminal state, or governance stops it."""
        trace = []
        for _ in range(max_steps):
            status = self.step(opp_id)
            if status is None:
                break
            trace.append(status)
            if status in state_machine.OPPORTUNITY_TERMINAL:
                break
        return trace
