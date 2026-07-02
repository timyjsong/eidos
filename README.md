# EIDOS

*Evidence-Integrated Decision & Opportunity System*

**A pipeline that generates its own software-product ideas, vets them through a governed lifecycle, and builds on what each run learned. Discovery is an agentic workflow; underneath it sits a model-agnostic, event-sourced engine that scores every candidate, gates every commitment behind a human, and keeps a replayable record of every run.**

Static painpoint detection — scrape forums for complaints, rank by volume, build the loudest one — is crowded, and its winners are already taken. EIDOS is built for the opposite: a discovery process that compounds weak signals across domains, surfaces latent demand nobody has named yet, and reasons toward products people would use but nobody has built. The raw material is faint and scattered — a workaround template shared in one place, the same chore outsourced in another, separate traces pointing at one unbuilt product. It aims to *invent* opportunities, not harvest the obvious.

Two things keep that from being just a clever prompt. It is **governed**: every candidate moves through an append-only, event-sourced lifecycle, scored against cited evidence, and gated by a human before any resources are committed. And it is **cumulative**: each run records what it explored, which methods produced what, and what survived scrutiny, so the next run starts from everything the last one learned instead of a blank slate.

## How it runs

The engine in this repo is the coded, tested backbone: a lifecycle state machine, an append-only event store, a CLI that is the only write path, two-phase budgeting, and a read-only dashboard. It is **model-agnostic** — it calls no LLM and binds to no provider; each unit of work simply records the model it used.

Discovery is an **agentic workflow** on top of that engine, and it runs as **two loops with different jobs**:

- **The discovery loop hunts for ideas.** The human kicks off a run; an LLM agent works a ratified discovery method — capturing signals, proposing candidates, attaching evidence, scoring, red-teaming — and writes every result through the CLI, so all of it lands in the governed, replayable log. The human reviews what comes back and decides at every gate.
- **The improvement loop upgrades the hunter.** Discovery methods are instruments, and changing one is its own governed event: one bounded, adversarially-reviewed change per iteration, ratified deliberately. A hunt can never quietly rewrite its own instruments — anything a run learns that would change how future runs judge ideas lands as a proposal for this second loop.

The agent proposes, the human gates, the engine remembers.

> **Scope, stated plainly.** This repository is the engine and the methodology — portable, standalone, model-agnostic, with a deterministic demo and a full test suite. The discovery agents that run on it, and the opportunities and research they produce, live outside it; the research stays private. What's here is the substrate that makes a creative, agent-run discovery process auditable and cumulative — not the ideas it has produced.

## The discovery approach

EIDOS treats discovery as a *generative* problem, not a detection one:

- **Compound, don't just collect.** Weak signals from different domains are combined into candidates no single source would suggest.
- **Create demand, don't only detect it.** The process targets tolerated, un-automated routines — work people endure without complaining loudly — rather than the obvious, already-served pain everyone else is mining.
- **Methods are measured, not trusted.** Each discovery method is scored on the candidates it produces; method performance is tracked in the store, so weak methods get retired and strong ones sharpened, one deliberate change at a time.

Every candidate still has to survive evidence-based scoring and adversarial review before the operator acts on it — creativity earns a hearing, rigor decides. Full detail in [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## The discipline

Five constraints keep the process honest:

- **The CLI is the only write path.** All state lives in a SQLite document store and is written exclusively through `python -m core.cli`. Nothing bypasses the state machine, budgets, or permission policies.
- **Human gates are real.** Approve, reject, launch, and budget creation happen only on explicit human action. The agent can recommend; it cannot commit.
- **Evidence discipline.** A score carries the ids of the knowledge records that justify it. A score without evidence is an opinion, and the linter flags it.
- **Budget before work.** Costed work is reserved against a budget before it runs and settled with actuals after. Spend is derived by replaying events, never stored — stored totals drift; the log cannot.
- **Nothing is deleted.** Facts are superseded, opportunities are rejected or archived, the event log is append-only. History stays revivable — markets shift, and a rejected candidate can be reopened with its full record intact.

## Architecture

Nine durable object types — opportunity, product, knowledge record, event, budget, permission policy, worker run, venue, directive — plus a state machine and a thin orchestrator over pluggable workers. The engine, by module:

| Layer | What it does |
|---|---|
| `core/state_machine.py` | Canonical lifecycle states + transition policy (as data) |
| `core/store.py` | Append-only event store + document persistence (SQLite) |
| `core/schemas.py` | The nine object schemas, each versioned for migratability |
| `core/cli.py` | The only write path — every command is an auditable action |
| `core/budget.py` | Two-phase reserve/settle budgeting, derived from events |
| `core/permissions.py` | Worker-*type* permission policies (workers are plugins) |
| `core/orchestrator.py` | Runs workers, records a run per invocation |
| `dashboard/` | A read-only static-site view over the store (Python generator) |

A **worker** is any object that declares its type, model, and cost and returns a result — an LLM agent, a script, or a deterministic stub. Workers never touch the store; the engine merges their output and owns all state, so swapping or adding a worker never means touching the state machine.

Opportunities move through **decision phases**, not worker-progress states:

```
DISCOVERED → TRIAGED → EVALUATED → APPROVED → VALIDATED → BUILDING → READY → LAUNCHED
```

plus `ON_HOLD` (remembers and returns to the state it left) and terminal `REJECTED_*` / `ARCHIVED` (rejected is dormant, not dead — reopenable). See [`data-model.md`](data-model.md) for the full object and lifecycle model.

## Quickstart

```bash
# Run the end-to-end demo (deterministic stub workers, no network)
python demo.py

# Run the test suite
python -m pytest            # 77 tests

# Operate the engine
python -m core.cli status
python -m core.cli --help
```

`demo.py` runs sample opportunities through the full governed lifecycle — scoring, human gates, reserve/settle budgets, the launch step, hold / resume / reopen, and full history reconstruction from events — with deterministic stub workers standing in for live agents, so it needs no API keys or network.

## How this was built

EIDOS was built by an autonomous agent operating under the same governance contract it enforces on opportunities — it shows its evidence and stops at every human gate, and a human reviews and commits each change. A few commits retain the "EIDOS Operator" author the agent ran as.

## License

MIT — see [LICENSE](LICENSE).
