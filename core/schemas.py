"""Core artifact schemas, mirroring data-model.md.

Dataclasses with explicit validation; Pydantic is the upgrade path (decisions/0001).
The to_doc/from_doc seam is the swap point.
"""
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .state_machine import ALL_OPPORTUNITY_STATES, PRODUCT_TERMINAL

SCHEMA_VERSION = 1
SCORE_DIMENSIONS = ("pain", "market", "distribution", "cost", "risk")
RUN_STATUSES = ("STARTED", "COMPLETED", "FAILED")
PRODUCT_STATUSES = ["ACTIVE"] + PRODUCT_TERMINAL


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class DocMixin:
    """JSON-document round-trip (decisions/0002)."""

    def to_doc(self):
        return asdict(self)

    @classmethod
    def from_doc(cls, doc):
        return cls(**doc)


def _check_confidence(confidence):
    if confidence is not None and not 0 <= confidence <= 1:
        raise ValueError(f"confidence must be in [0, 1], got {confidence}")


@dataclass
class Score(DocMixin):
    value: float | None = None
    confidence: float | None = None
    rationale: str = ""
    evidence: list = field(default_factory=list)  # Knowledge Record ids

    def __post_init__(self):
        _check_confidence(self.confidence)


def _empty_scores():
    return {dim: Score() for dim in SCORE_DIMENSIONS}


@dataclass
class Opportunity(DocMixin):
    title: str
    platform: str = ""
    id: str = field(default_factory=lambda: new_id("opp"))
    schema_version: int = SCHEMA_VERSION
    status: str = "DISCOVERED"
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    discovery: dict = field(
        default_factory=lambda: {"signals": [], "sources": [], "clusters": []}
    )
    scores: dict = field(default_factory=_empty_scores)
    decisions: dict = field(
        default_factory=lambda: {
            "approval_status": None,
            "portfolio_priority": None,
            "decision_history": [],
        }
    )
    execution: dict = field(
        default_factory=lambda: {
            "scope": {},
            "plan": {},
            "design": {},
            "build_outputs": [],
            "qa_outputs": [],
        }
    )

    def __post_init__(self):
        if self.status not in ALL_OPPORTUNITY_STATES:
            raise ValueError(f"unknown opportunity status: {self.status}")
        self.scores = {
            dim: score if isinstance(score, Score) else Score(**score)
            for dim, score in self.scores.items()
        }


@dataclass
class Product(DocMixin):
    name: str
    platform: str = ""
    id: str = field(default_factory=lambda: new_id("prod"))
    schema_version: int = SCHEMA_VERSION
    status: str = "ACTIVE"
    launch_date: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    metrics: dict = field(
        default_factory=lambda: {"revenue": 0, "profit": 0, "users": 0, "churn": 0}
    )
    operations: dict = field(
        default_factory=lambda: {
            "issues": [],
            "feature_requests": [],
            "maintenance_history": [],
        }
    )

    def __post_init__(self):
        if self.status not in PRODUCT_STATUSES:
            raise ValueError(f"unknown product status: {self.status}")


@dataclass
class KnowledgeRecord(DocMixin):
    type: str
    source: str
    content: str
    id: str = field(default_factory=lambda: new_id("know"))
    schema_version: int = SCHEMA_VERSION
    confidence: float | None = None
    observed_at: str = ""
    created_at: str = field(default_factory=now_iso)
    superseded_by: str | None = None

    def __post_init__(self):
        _check_confidence(self.confidence)


@dataclass
class Event(DocMixin):
    type: str
    actor: str
    target_id: str
    payload: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: new_id("evt"))
    timestamp: str = field(default_factory=now_iso)


@dataclass
class Budget(DocMixin):
    scope: str
    allocated: float
    id: str = field(default_factory=lambda: new_id("budget"))
    schema_version: int = SCHEMA_VERSION
    created_at: str = field(default_factory=now_iso)

    def __post_init__(self):
        if self.allocated < 0:
            raise ValueError("allocated must be >= 0")


@dataclass
class PermissionPolicy(DocMixin):
    worker_type: str
    tier: int
    allowed_actions: list = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self):
        if not 0 <= self.tier <= 6:
            raise ValueError(f"tier must be 0-6, got {self.tier}")


@dataclass
class WorkerRun(DocMixin):
    worker_type: str
    model: str = ""
    opportunity_id: str | None = None
    input_summary: str = ""
    output: dict | None = None
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    status: str = "STARTED"
    id: str = field(default_factory=lambda: new_id("run"))
    schema_version: int = SCHEMA_VERSION
    started_at: str = field(default_factory=now_iso)
    finished_at: str | None = None

    def __post_init__(self):
        if self.status not in RUN_STATUSES:
            raise ValueError(f"unknown run status: {self.status}")
