# Data Model Draft v0.3

> Status: Draft — change cadence: **constantly**, for the first few months.
>
> This document is intentionally optimized for speed of iteration.
> Schemas are expected to change frequently during early development.
> Stability of concepts matters more than stability of fields.
>
> This doc owns the canonical lifecycle states and transition rules as policy;
> the transition table in `core/state_machine.py` is the canonical implementation.
> Code and doc agree as of v0.3 (2026-06-09).

---

# Philosophy

The platform is a state machine operating on artifacts.

Workers are temporary.

Data structures are durable.

When in doubt:

- Preserve information
- Avoid deleting fields
- Favor extensibility over optimization
- Keep schemas human-readable

---

# Core Objects

1. Opportunity
2. Product
3. Knowledge Record
4. Event
5. Budget
6. Permission Policy
7. Worker Run
8. Venue
9. Directive

Every object carries a `schema_version` so constant schema churn stays migratable.

---

# Opportunity

Represents a potential business opportunity.

`signal_venues` = where the pain was observed (evidence context). `target_venues` =
where a solution could ship — a *scoping-time decision*, empty early. The same pain
seen in Shopify forums might best ship as a Chrome extension; binding one venue at
discovery forecloses that choice. `directive_id` = the human intent that spawned this
(null for standing harvest; `source: human` seeds skip discovery entirely).

```json
{
  "id": "opp_123",
  "schema_version": 2,
  "title": "",
  "status": "DISCOVERED",
  "directive_id": null,
  "signal_venues": [],
  "target_venues": [],
  "held_from": null,
  "created_at": "",
  "updated_at": ""
}
```

## Discovery

```json
{
  "method": "",
  "signals": [],
  "sources": [],
  "clusters": []
}
```

`method` names the discovery method that produced this candidate (a key into the
discovery-method registry). Gate verdicts accrue into per-method scorecards — discovery
provenance is mandatory, like evidence on scores.

## Scores

One object per dimension. A score, its confidence, and its evidence travel together —
parallel score/confidence blocks drift apart, and a score with no evidence refs is an
opinion pretending to be a fact.

```json
{
  "pain":         { "value": null, "confidence": null, "estimate": "", "rationale": "", "evidence": [] },
  "market":       { "value": null, "confidence": null, "estimate": "", "rationale": "", "evidence": [] },
  "distribution": { "value": null, "confidence": null, "estimate": "", "rationale": "", "evidence": [] },
  "cost":         { "value": null, "confidence": null, "estimate": "", "rationale": "", "evidence": [] },
  "risk":         { "value": null, "confidence": null, "estimate": "", "rationale": "", "evidence": [] }
}
```

`estimate` is the grounded quantity in the dimension's native units ("~5 session-days,
<$100"; "ceiling ~$1k/mo"). The estimate is the real forecast — the score is its
projection onto 0–10. Never store a score without its estimate; estimates are what
forecast accuracy is later measured against.

`evidence` holds Knowledge Record ids. `confidence` is 0–1.

## Score Anchors (canonical rubric — a number without an anchor is a vibe)

All dimensions 0–10, **higher = better odds for us**. Bands are calibrated to a
solo-operator portfolio; revisit at v2 scale.

**Pain** — severity × prevalence:
- 0–2 minor annoyance, rare, trivial workarounds
- 3–4 regular friction for a niche; workarounds cost time
- 5–6 recurring workflow blocker for a definable segment; people actively seek fixes
- 7–8 structural pain hit weekly+; people pay or build hacks around it today
- 9–10 acute and unavoidable; public complaints, no acceptable workaround

**Market** — realistic revenue ceiling at maturity, this product on this venue:
- 0–2 < $100/mo · 3–4 $100–500/mo · 5–6 $500–2k/mo · 7–8 $2k–10k/mo · 9–10 $10k+/mo

**Distribution** — odds of reaching buyers:
- 0–2 saturated, entrenched incumbents, no wedge
- 3–4 contested; incumbent exists; wedge is hypothetical
- 5–6 discoverable via venue search, moderate competition, clear differentiator
- 7–8 underserved niche; demand searches exist; weak or no incumbents
- 9–10 unmet demand with a built-in channel (waiting audience, likely venue featuring)

**Cost** — investment favorability (higher = cheaper), effort in session-days + real dollars:
- 0–2 >30 days or >$500; infra + accounts + operating burn
- 3–4 10–30 days; server backend; $100–500
- 5–6 5–10 days; minimal infra; <$100
- 7–8 2–5 days; serverless; near-zero dollars
- 9–10 1–2 days; pure client-side; zero dollars

**Risk** — safety from platform/technical/business shocks (higher = safer):
- 0–2 existential dependency on a policy that could flip; ToS-gray; fragile single point
- 3–4 meaningful platform risk (venue could ship the feature); incumbent retaliation likely
- 5–6 normal risk; venue stable; no roadmap-collision signals
- 7–8 low coupling to platform whims; defensible workflow or data
- 9–10 nearly risk-free; venue-independent fallback exists

**Confidence** (0–1, applies to any score): 0.3 single source or hunch · 0.5 a couple of
consistent sources · 0.7 multiple independent sources · 0.9 directly verified/quantified.

## Scoring Discipline (what keeps a ranked list credible)

Ranking collapses if scoring flip-flops. Four rules make scores repeatable:

1. **Estimate first, band second.** Write the grounded estimate from evidence, then
   read the score off the rubric band — never vibe the float directly. Decimals only
   express position *within* a band.
2. **Precedent ladder.** Score relative to already-scored candidates — the registry is
   case law. "Is this pain worse than the last candidate I scored an 8.0?" beats absolute
   judgment every time.
3. **Never rank across scoring regimes.** Every verdict carries `system_version`;
   before ranking old candidates against new ones, re-score the old under the current
   rubric. Cross-regime comparison is meaningless.
4. **Blind re-score audits.** Periodically re-score a sample without looking at prior
   scores; drift beyond ±1 band reveals rubric ambiguity. Fix the anchor, not the score.

(Composite-ranking weights across dimensions: deliberately undecided
until the EVALUATED queue is deep enough to need them.)

## Validation

The validation phase is one state with a checklist — sub-results are data, can run in
parallel, and never become states:

```json
{
  "problem": null,
  "market": null,
  "distribution": null
}
```

## Decisions

```json
{
  "approval_status": null,
  "portfolio_priority": null,
  "decision_history": []
}
```

## Execution

```json
{
  "scope": {},
  "plan": {},
  "design": {},
  "build_outputs": [],
  "qa_outputs": []
}
```

---

# Product

Represents a launched asset.

```json
{
  "id": "prod_123",
  "schema_version": 2,
  "name": "",
  "status": "ACTIVE",
  "launch_date": "",
  "opportunity_id": null,
  "target_venue": null
}
```

`opportunity_id` is permanent provenance: a product is born at launch from exactly one
opportunity, whose story ends at LAUNCHED. Operations, metrics, and portfolio decisions
(retire, invest, merge) live here — never on the opportunity. One reality, one owner.

## Metrics

```json
{
  "revenue": 0,
  "profit": 0,
  "users": 0,
  "churn": 0
}
```

## Operations

```json
{
  "issues": [],
  "feature_requests": [],
  "maintenance_history": []
}
```

---

# Knowledge Record

Atomic fact stored in the knowledge base.

```json
{
  "id": "know_123",
  "schema_version": 2,
  "type": "",
  "source": "",
  "content": "",
  "tags": [],
  "entities": [],
  "venue_id": null,
  "confidence": null,
  "observed_at": "",
  "created_at": "",
  "superseded_by": null
}
```

Examples:

- Competitor observation
- Marketplace research
- Customer feedback
- Pricing information

Facts go stale (pricing changes, competitors ship). A stale fact is superseded, never
edited or deleted — `observed_at` says when it was true, `superseded_by` points forward.

---

# Event

Everything important should become an event.

```json
{
  "id": "evt_123",
  "type": "",
  "timestamp": "",
  "actor": "",
  "target_id": "",
  "payload": {}
}
```

Examples:

- Opportunity created
- Score changed
- Approval granted
- Product launched

---

# Budget

```json
{
  "id": "budget_123",
  "schema_version": 1,
  "scope": "",
  "allocated": 0
}
```

`consumed` and `remaining` are never stored — they are derived by folding budget events.
Stored derived values drift; the event log cannot ("never rely on current state alone").

Spending is two-phase: `BUDGET_RESERVED(estimate)` gates the work *before* it runs;
`BUDGET_SETTLED(actual)` records what it really cost on completion. Consumed = settled
+ outstanding reserves. Books that record estimates forever can't compute "forecast
accuracy" — a stated success metric.

---

# Permission Policy

```json
{
  "worker_type": "",
  "tier": 0,
  "allowed_actions": []
}
```

Keyed by worker *type*, never a worker instance — workers are replaceable implementation
details (the litmus test), so an instance-keyed policy would die with its worker.

---

# Worker Run

One record per worker invocation. This is where cost tracking, observability, and
worker replaceability become real — without it, "every decision has a cost" has no home.

```json
{
  "id": "run_123",
  "schema_version": 1,
  "worker_type": "",
  "model": "",
  "opportunity_id": null,
  "input_summary": "",
  "output": null,
  "cost_usd": 0,
  "tokens_in": 0,
  "tokens_out": 0,
  "status": "STARTED",
  "started_at": "",
  "finished_at": null
}
```

---

# Venue

A channel through which a product reaches users. Marketplace, app store, npm,
direct web — and in v2, anything: a client pipeline, a content channel.

```json
{
  "id": "venue_123",
  "schema_version": 1,
  "name": "",
  "kind": "",
  "profile": {
    "distribution": {},
    "monetization": {},
    "gatekeeping": {},
    "cost_benchmarks": {}
  }
}
```

Profiles feed scoring: gatekeeping/policy risk → Risk Score, rev share and pricing
norms → Market Score. Core concepts (lifecycle, scores, governance) never name a
venue — venue-specific behavior lives in profiles (data) and venue-parameterized
workers (plugins). That rule is what keeps v2 a config change instead of a rewrite.

---

# Directive

A human intent that parameterizes discovery: *"explore productivity gaps on the
iOS App Store, research budget $15."*

```json
{
  "id": "dir_123",
  "schema_version": 1,
  "prompt": "",
  "venues": [],
  "budget_id": null,
  "cadence": "one_shot",
  "status": "ACTIVE",
  "created_at": ""
}
```

Three entry modes converge on one lifecycle:

1. **Directive-driven scan** — venue-first intent ("scan Figma Community for X").
2. **Standing harvest** — always-on background discovery.
3. **Manual seed** — "I already have this idea": an opportunity created directly,
   entering at DISCOVERED with `source: human`.

Directives also give budgets their natural scope.

---

# Lifecycle States (canonical — architecture doc points here)

States are **decision phases**. Worker progress lives in artifact data, never in new
states — adding a worker must never require state-machine surgery (the litmus test).

## Opportunity

- DISCOVERED — raw candidate, from any of the three entry modes
- TRIAGED — classified and vetted; triage policy may auto-archive here
- EVALUATED — scored with evidence; awaiting the human decision
- APPROVED — human committed resources
- VALIDATED — validation checklist passed (problem / market / distribution are
  parallel sub-results in artifact data, not states)
- BUILDING — in the build pipeline (scope, plan, design, build, qa as execution data)
- READY — passed the target venue's release bar
- LAUNCHED — shipped; a Product is born with this opportunity as provenance.
  The opportunity's story ends here. Operations belong to the Product.
- ON_HOLD — shelved by the portfolio; remembers and returns to the state it left

## Opportunity Terminal

- REJECTED_SATURATED
- REJECTED_LOW_DEMAND
- REJECTED_LOW_ROI
- REJECTED_HIGH_RISK
- REJECTED_STRATEGIC_MISALIGNMENT
- ARCHIVED

REJECTED_* is dormant, not dead: an explicit REOPEN (human or portfolio manager only)
re-enters at TRIAGED with full history retained — markets shift, and "never deleted"
means revivable. ARCHIVED is truly frozen.

## Product Terminal

- RETIRED
- DEPRECATED
- MERGED
- SOLD

## Transition Rules

The state list alone is not a state machine. Current policy (the table lives as data
in `core/state_machine.py`):

- Forward: each phase advances only to the next.
- Reject: allowed from TRIAGED through VALIDATED (the decision window).
- Archive: allowed from any active state.
- ON_HOLD: from any active state; exits back to the state it left.
- REOPEN: REJECTED_* → TRIAGED, human/portfolio actors only.
- "Re-evaluate" is a re-score in place at EVALUATED, not a state change.
- Every blocked transition attempt is also an event — failed attempts are evidence too.

v0.1 → v0.3 mapping: CLASSIFIED/VETTED → TRIAGED (+ discovery data) · the three
*_VALIDATED states → VALIDATED (+ checklist) · SCOPED/PLANNED/DESIGNED/BUILDING/QA →
BUILDING (+ execution data) · OPERATING → the Product.

---

# Audit Trail Requirements

Every state transition should generate an event.

Every approval should generate an event.

Every budget change should generate an event.

Every external action should generate an event.

Never rely on current state alone.

History should always be reconstructable.
