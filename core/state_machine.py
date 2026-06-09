"""Lifecycle states and the transition table (canonical — data-model.md describes the policy).

States are decision phases (ADR-0007). Worker progress lives in artifact data, never
in new states — adding a worker must never require state-machine surgery.

- Forward: each phase advances only to the next.
- Reject: allowed from TRIAGED through VALIDATED (the decision window).
- Archive: allowed from any active state.
- ON_HOLD: from any active state except LAUNCHED; exits back to the state it left.
- REOPEN: REJECTED_* -> TRIAGED, human/portfolio actors only. ARCHIVED is frozen.
- Every blocked attempt is an event — failed attempts are evidence too.
"""
from datetime import datetime, timezone

from . import event_types as ev

LIFECYCLE = [
    "DISCOVERED",
    "TRIAGED",
    "EVALUATED",
    "APPROVED",
    "VALIDATED",
    "BUILDING",
    "READY",
    "LAUNCHED",
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
ALL_OPPORTUNITY_STATES = LIFECYCLE + ["ON_HOLD"] + OPPORTUNITY_TERMINAL

_REJECTION_WINDOW = LIFECYCLE[LIFECYCLE.index("TRIAGED") : LIFECYCLE.index("VALIDATED") + 1]
_REOPEN_ACTORS = ("portfolio_manager",)

TRANSITIONS = {}
for _i, _state in enumerate(LIFECYCLE):
    _allowed = {"ARCHIVED"}
    if _i + 1 < len(LIFECYCLE):
        _allowed.add(LIFECYCLE[_i + 1])
        _allowed.add("ON_HOLD")  # LAUNCHED is the end of the story; it can't be held
    if _state in _REJECTION_WINDOW:
        _allowed.update(REJECTED)
    TRANSITIONS[_state] = _allowed
for _state in REJECTED:
    TRANSITIONS[_state] = {"TRIAGED"}  # REOPEN — actor-guarded in transition()
TRANSITIONS["ARCHIVED"] = set()
TRANSITIONS["ON_HOLD"] = set()  # dynamic: held_from or ARCHIVED


class InvalidTransition(Exception):
    pass


def allowed_targets(opportunity):
    if opportunity.status == "ON_HOLD":
        return {s for s in (opportunity.held_from, "ARCHIVED") if s}
    return TRANSITIONS.get(opportunity.status, set())


def _may_reopen(actor):
    return actor.startswith("human:") or actor in _REOPEN_ACTORS


def transition(store, opportunity, new_state, actor, reason=""):
    """Move an opportunity to new_state or raise. Either way, leave an event."""
    current = opportunity.status
    blocked_why = None
    if new_state not in allowed_targets(opportunity):
        blocked_why = "not an allowed transition"
    elif current in REJECTED and not _may_reopen(actor):
        blocked_why = "reopen requires a human or the portfolio manager"
    if blocked_why:
        store.emit(
            ev.OPPORTUNITY_TRANSITION_BLOCKED,
            actor,
            opportunity.id,
            {"from": current, "to": new_state, "why": blocked_why, "reason": reason},
        )
        raise InvalidTransition(f"{opportunity.id}: {current} -> {new_state}: {blocked_why}")

    if new_state == "ON_HOLD":
        opportunity.held_from = current
    elif current == "ON_HOLD":
        opportunity.held_from = None
    opportunity.status = new_state
    opportunity.updated_at = datetime.now(timezone.utc).isoformat()
    store.save_opportunity(opportunity)
    store.emit(
        ev.OPPORTUNITY_STATE_CHANGED,
        actor,
        opportunity.id,
        {"from": current, "to": new_state, "reason": reason},
    )
    return opportunity
