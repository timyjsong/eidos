"""Core artifact schemas (Pydantic), mirroring data-model.md v0.3.

The to_doc/from_doc seam is stable across schema backends (ADR-0001).
"""
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

from .state_machine import ALL_OPPORTUNITY_STATES, PRODUCT_TERMINAL

SCORE_DIMENSIONS = ("pain", "market", "distribution", "cost", "risk")
RUN_STATUSES = ("STARTED", "COMPLETED", "FAILED")
PRODUCT_STATUSES = ["ACTIVE"] + PRODUCT_TERMINAL
DIRECTIVE_CADENCES = ("one_shot", "standing")
DIRECTIVE_STATUSES = ("ACTIVE", "CLOSED")
VALIDATION_CHECKS = ("problem", "market", "distribution")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class DocModel(BaseModel):
    """JSON-document round-trip (decisions/0002)."""

    def to_doc(self):
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc):
        return cls.model_validate(doc)


def _check_confidence(confidence):
    if confidence is not None and not 0 <= confidence <= 1:
        raise ValueError(f"confidence must be in [0, 1], got {confidence}")
    return confidence


class Score(DocModel):
    value: float | None = None
    confidence: float | None = None
    estimate: str = ""  # grounded quantity in the dimension's native units — the real forecast
    rationale: str = ""
    evidence: list = Field(default_factory=list)  # Knowledge Record ids

    @field_validator("confidence")
    @classmethod
    def _confidence(cls, v):
        return _check_confidence(v)


def _empty_scores():
    return {dim: Score() for dim in SCORE_DIMENSIONS}


class Opportunity(DocModel):
    title: str
    id: str = Field(default_factory=lambda: new_id("opp"))
    schema_version: int = 3
    status: str = "DISCOVERED"
    directive_id: str | None = None
    signal_venues: list = Field(default_factory=list)
    target_venues: list = Field(default_factory=list)
    held_from: str | None = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    discovery: dict = Field(
        default_factory=lambda: {"signals": [], "sources": [], "clusters": []}
    )
    scores: dict[str, Score] = Field(default_factory=_empty_scores)
    validation: dict = Field(
        default_factory=lambda: {check: None for check in VALIDATION_CHECKS}
    )
    decisions: dict = Field(
        default_factory=lambda: {
            "approval_status": None,
            "portfolio_priority": None,
            "decision_history": [],
        }
    )
    execution: dict = Field(
        default_factory=lambda: {
            "scope": {},
            "plan": {},
            "design": {},
            "build_outputs": [],
            "qa_outputs": [],
        }
    )

    @field_validator("status")
    @classmethod
    def _check_status(cls, v):
        if v not in ALL_OPPORTUNITY_STATES:
            raise ValueError(f"unknown opportunity status: {v}")
        return v


class Product(DocModel):
    name: str
    id: str = Field(default_factory=lambda: new_id("prod"))
    schema_version: int = 2
    status: str = "ACTIVE"
    launch_date: str = ""
    opportunity_id: str | None = None  # permanent provenance
    target_venue: str | None = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    metrics: dict = Field(
        default_factory=lambda: {"revenue": 0, "profit": 0, "users": 0, "churn": 0}
    )
    operations: dict = Field(
        default_factory=lambda: {
            "issues": [],
            "feature_requests": [],
            "maintenance_history": [],
        }
    )

    @field_validator("status")
    @classmethod
    def _check_status(cls, v):
        if v not in PRODUCT_STATUSES:
            raise ValueError(f"unknown product status: {v}")
        return v


class KnowledgeRecord(DocModel):
    type: str
    source: str
    content: str
    id: str = Field(default_factory=lambda: new_id("know"))
    schema_version: int = 2
    tags: list = Field(default_factory=list)
    entities: list = Field(default_factory=list)
    venue_id: str | None = None
    confidence: float | None = None
    observed_at: str = ""
    created_at: str = Field(default_factory=now_iso)
    superseded_by: str | None = None

    @field_validator("confidence")
    @classmethod
    def _confidence(cls, v):
        return _check_confidence(v)


class Venue(DocModel):
    name: str
    kind: str = ""
    id: str = Field(default_factory=lambda: new_id("venue"))
    schema_version: int = 1
    profile: dict = Field(
        default_factory=lambda: {
            "distribution": {},
            "monetization": {},
            "gatekeeping": {},
            "cost_benchmarks": {},
        }
    )


class Directive(DocModel):
    prompt: str
    id: str = Field(default_factory=lambda: new_id("dir"))
    schema_version: int = 1
    venues: list = Field(default_factory=list)
    budget_id: str | None = None
    cadence: str = "one_shot"
    status: str = "ACTIVE"
    created_at: str = Field(default_factory=now_iso)

    @field_validator("cadence")
    @classmethod
    def _check_cadence(cls, v):
        if v not in DIRECTIVE_CADENCES:
            raise ValueError(f"unknown cadence: {v}")
        return v

    @field_validator("status")
    @classmethod
    def _check_status(cls, v):
        if v not in DIRECTIVE_STATUSES:
            raise ValueError(f"unknown directive status: {v}")
        return v


class Event(DocModel):
    type: str
    actor: str
    target_id: str
    payload: dict = Field(default_factory=dict)
    id: str = Field(default_factory=lambda: new_id("evt"))
    timestamp: str = Field(default_factory=now_iso)


class Budget(DocModel):
    scope: str
    allocated: float = Field(ge=0)
    id: str = Field(default_factory=lambda: new_id("budget"))
    schema_version: int = 2
    created_at: str = Field(default_factory=now_iso)


class PermissionPolicy(DocModel):
    worker_type: str
    tier: int = Field(ge=0, le=6)
    allowed_actions: list = Field(default_factory=list)
    schema_version: int = 1


class WorkerRun(DocModel):
    worker_type: str
    model: str = ""
    opportunity_id: str | None = None
    input_summary: str = ""
    output: dict | None = None
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    status: str = "STARTED"
    id: str = Field(default_factory=lambda: new_id("run"))
    schema_version: int = 1
    started_at: str = Field(default_factory=now_iso)
    finished_at: str | None = None

    @field_validator("status")
    @classmethod
    def _check_status(cls, v):
        if v not in RUN_STATUSES:
            raise ValueError(f"unknown run status: {v}")
        return v
