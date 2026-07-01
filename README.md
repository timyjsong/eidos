# EIDOS

*Evidence-Integrated Decision & Opportunity System*

**An end-to-end pipeline that takes a software product from zero — no idea yet — through discovery and evaluation to a build-ready decision. The moat is the discovery step: it *invents* opportunities through creative discovery rather than scraping for known painpoints.**

Most idea-sourcing is static painpoint detection: scrape forums for complaints, rank by
volume, build the loudest one. That space is crowded and its winners are already taken.
EIDOS does creative discovery instead — it compounds weak signals across domains, surfaces
latent demand nobody has named yet, and reasons toward products for tolerated, un-automated
routines. It **invents** opportunities rather than harvesting the obvious. That discovery
loop is the moat; everything downstream is the discipline that keeps it honest.

A candidate enters a state machine, accumulates evidence-backed scores, passes adversarial
review, and stops at human gates before any resources are committed. Every state change,
score, and decision is an append-only event, so the whole history is reconstructable from
the log alone. An autonomous operator drives discover → evaluate → red-team → recommend,
and never crosses a gate on its own.

> **Where it stands, stated plainly.** The pipeline runs from discovery through a
> build-ready decision. The build and launch stages exist in the lifecycle but have not
> been exercised in a real run — no candidate has reached the build stage. That is the system
> working as designed: it exists to decide *well and cheaply* before committing to a build,
> so a conservative funnel is the feature and zero products launched is on purpose. This
> repository is the engine and the methodology, with a deterministic demo and a full test
> suite; the specific opportunities and research produced by operating it are kept private.

---

## The core: a creative discovery loop

EIDOS treats discovery as a *generative* problem, not a detection one:

- **Compound, don't just collect.** Weak signals from different domains are combined into
  candidates that no single source would suggest.
- **Create demand, don't only detect it.** The loop targets tolerated, un-automated
  routines — work people endure without complaining loudly — rather than the obvious,
  already-served pain everyone else is mining.
- **Methods are instruments that improve.** Each discovery method is scored on the
  candidates it produces; the loop evolves its own methods over time, one measured change
  at a time, with a standing tripwire against sliding back into lazy detection.

Every candidate this produces still has to survive evidence-based scoring and adversarial
review before a human sees it — creativity earns a hearing, rigor decides. Full detail in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## The discipline around it

Five constraints keep the creative loop honest:

- **The CLI is the only write path.** All state lives in a SQLite doc-blob store and is
  written exclusively through `python -m core.cli`. Nothing bypasses the state machine,
  budgets, or permission policies.
- **Human gates are real.** Approve, reject, launch, and budget creation happen only on
  explicit human action. The operator can recommend; it cannot commit.
- **Evidence discipline.** A score carries the ids of the knowledge records that justify
  it. A score without evidence is an opinion, and the linter flags it.
- **Budget before work.** Costed work is *reserved* against a budget before it runs and
  *settled* with actuals after (two-phase). Consumed cost is derived by folding events,
  never stored — stored derived values drift; the log cannot.
- **Nothing is deleted.** Facts are superseded, opportunities are rejected or archived,
  the event log is append-only. History stays revivable — markets shift, and a rejected
  candidate can be reopened with its full record intact.

## Architecture

Nine durable objects, a state machine, and a thin orchestrator over replaceable workers:

| Layer | What it does |
|---|---|
| `core/state_machine.py` | Canonical lifecycle states + transition policy (as data) |
| `core/store.py` | Append-only event store + doc-blob persistence (SQLite) |
| `core/schemas.py` | The nine object schemas, each versioned for migratability |
| `core/cli.py` | The only write path — every command is an auditable action |
| `core/budget.py` | Two-phase reserve/settle budgeting, derived from events |
| `core/permissions.py` | Worker-*type* permission policies (workers are plugins) |
| `core/orchestrator.py` | Runs workers, records a run per invocation |
| `dashboard/` | A read-only static-site view over the store (Python generator) |

Opportunities move through **decision phases**, not worker-progress states:

```
DISCOVERED → TRIAGED → EVALUATED → APPROVED → VALIDATED → BUILDING → READY → LAUNCHED
```

plus `ON_HOLD` (remembers and returns to the state it left) and terminal
`REJECTED_*` / `ARCHIVED` (rejected is dormant, not dead — reopenable). Adding a new
worker must never require touching the state machine — worker progress lives in artifact
data, never in new states. See [`data-model.md`](data-model.md) for the full object and
lifecycle model.

## Quickstart

```bash
# Run the end-to-end demo (deterministic stub workers, fake data)
python demo.py

# Run the test suite
python -m pytest            # 139 tests

# Operate the platform
python -m core.cli status
python -m core.cli --help
```

`demo.py` runs fake opportunities through the full governed lifecycle — venue and
directive entry, scoring, human gates, reserve/settle budgets, the launch seam, hold /
resume / reopen, and full history reconstruction from events — with deterministic stub
workers, so it needs no API keys or network.

## How this was built

EIDOS was built by an autonomous agent operating under the same governance contract it
enforces on opportunities — it shows its evidence and stops at every human gate, and a
human reviews and commits each change. A few commits retain the "EIDOS Operator" author
the agent ran as.

## License

MIT — see [LICENSE](LICENSE).
