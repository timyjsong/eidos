"""Lifecycle states and the transition table.

This table is canonical (data-model.md describes the policy):
- Forward: each active state advances only to the next state in the chain.
- Reject: allowed from VETTED through DISTRIBUTION_VALIDATED (the decision window).
- Archive: allowed from any active state.
- Terminal states are frozen.
- Every blocked attempt is an event — failed attempts are evidence too.
"""
from datetime import datetime, timezone

LIFECYCLE = [
    "DISCOVERED",
    "CLASSIFIED",
    "VETTED",
    "EVALUATED",
    "APPROVED",
    "PROBLEM_VALIDATED",
    "MARKET_VALIDATED",
    "DISTRIBUTION_VALIDATED",
    "SCOPED",
    "PLANNED",
    "DESIGNED",
    "BUILDING",
    "QA",
    "READY",
    "LAUNCHED",
    "OPERATING",
]

REJECTED = [
    "REJECTED_SATURATED",
    "REJECTED_LOW_DEMAND",
    "REJECTED_LOW_ROI",
    "REJECTED_HIGH_RISK",
    "REJECTED_STRATEGIC_MISALIGNMENT",
]

OPPORTUNITY_TERMINAL = REJECTED + ["ARCHIVED"]
PRODUCT_TERMINAL = ["RETIRED", "DEPRECATED", "MERGED", "SOLD"]
ALL_OPPORTUNITY_STATES = LIFECYCLE + OPPORTUNITY_TERMINAL

_REJECTION_WINDOW = LIFECYCLE[
    LIFECYCLE.index("VETTED") : LIFECYCLE.index("DISTRIBUTION_VALIDATED") + 1
]

TRANSITIONS = {}
for _i, _state in enumerate(LIFECYCLE):
    _allowed = {"ARCHIVED"}
    if _i + 1 < len(LIFECYCLE):
        _allowed.add(LIFECYCLE[_i + 1])
    if _state in _REJECTION_WINDOW:
        _allowed.update(REJECTED)
    TRANSITIONS[_state] = _allowed
for _state in OPPORTUNITY_TERMINAL:
    TRANSITIONS[_state] = set()


class InvalidTransition(Exception):
    pass


def can_transition(current, new):
    return new in TRANSITIONS.get(current, set())


def transition(store, opportunity, new_state, actor, reason=""):
    """Move an opportunity to new_state or raise. Either way, leave an event."""
    current = opportunity.status
    if not can_transition(current, new_state):
        store.emit(
            "OPPORTUNITY_TRANSITION_BLOCKED",
            actor,
            opportunity.id,
            {"from": current, "to": new_state, "reason": reason},
        )
        raise InvalidTransition(f"{opportunity.id}: {current} -> {new_state} is not allowed")
    opportunity.status = new_state
    opportunity.updated_at = datetime.now(timezone.utc).isoformat()
    store.save_opportunity(opportunity)
    store.emit(
        "OPPORTUNITY_STATE_CHANGED",
        actor,
        opportunity.id,
        {"from": current, "to": new_state, "reason": reason},
    )
    return opportunity
