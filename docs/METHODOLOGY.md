# Methodology

EIDOS is built around one wager: the hard part of software isn't building — it's *choosing
what to build* — and the best things to build are the ones you have to **create the case
for**, not the ones already screaming for attention.

Most idea-sourcing *detects*: scrape complaints, rank by volume, ship the loudest. That
space is crowded and its winners are already taken. EIDOS is designed to *generate*
instead — to compound weak signals across domains, surface latent demand nobody has named,
and reason toward products for tolerated, un-automated routines.

## Two loops

The system is two loops, and keeping them apart is most of the governance.

- **The discovery loop hunts.** It takes a ratified discovery method and runs it against
  the world: capturing signals, inventing candidates, attaching evidence, scoring,
  stopping at every human gate. This is the loop that produces ideas.
- **The improvement loop builds the hunter.** It designs, calibrates, and ratifies the
  discovery methods themselves — the instruments the first loop runs with. One bounded,
  adversarially-reviewed change at a time. This is the loop that makes the ideas get
  better.

They are governed differently on purpose. A hunt runs autonomously up to the human gates —
but it can never change its own instruments. Anything instrument-shaped that a run learns
lands as a *proposal*, and only a deliberately kicked improvement iteration can ratify it.
The boundary is drawn on **output, not activity**: if the output would change how future
hunts judge ideas, it waits for the second loop.

Everything else in this document — evidence, scoring, adversarial review, human gates —
exists to keep a creative process honest rather than let it hallucinate.

This document is deliberately generic. The specific markets and candidates an operator
runs through the loops are theirs — not part of this repo.

## The pipeline (the discovery loop's spine)

Every candidate opportunity is an artifact that moves through decision phases:

```
discover → triage → evaluate (score + evidence) → [human gate: approve]
        → validate → build → [human gate: launch]
```

Approval and launch are both human gates — passing the first never buys the second.
Phases are *decisions*, not activity. A worker's progress lives in the artifact's data,
never in a new state — so adding capability never means re-plumbing the state machine.
Each phase transition is an append-only event; the whole trajectory is reconstructable
from the log. The canonical state names — including holds, rejections, and reopening —
live in [`../data-model.md`](../data-model.md); this diagram is the plain-English view.

## Evidence discipline

The rule that keeps the pipeline honest: **research first, score second, cite always.**

1. A knowledge record is added for each observed fact — with a source, a timestamp, and a
   confidence. Facts go stale, so they are *superseded* (never edited or deleted); the
   record points forward to whatever replaced it.
2. A dimension score is written only with the ids of the knowledge records that justify
   it. Score, confidence, and evidence travel together as one object — parallel score and
   confidence blocks drift apart, and a score without evidence is an opinion wearing a
   number.
3. An evidence linter flags any score standing without support.

## Scoring that stays comparable

A ranked list is worthless if the ranking flip-flops. Four rules make scores repeatable
across time and across candidates:

- **Estimate first, band second.** Write the grounded estimate in native units (effort in
  days, a revenue ceiling, a dollar cost), then read the score off a fixed rubric band.
  Never vibe the number directly; decimals only express position *within* a band. The
  estimate — not the score — is what forecast accuracy is later measured against.
- **Precedent ladder.** Score relative to already-scored candidates. The registry is case
  law: "is this pain worse than the last thing I called an 8?" beats absolute judgment.
- **Never rank across scoring regimes.** Every verdict is stamped with the rubric version
  that produced it (recorded as `system_version` in the store). Before comparing old
  candidates to new, re-score the old under the current rubric — cross-regime comparison
  is meaningless.
- **Blind re-score audits.** Periodically re-score a sample without looking at prior
  scores. Drift beyond one band reveals rubric ambiguity — the fix is a sharper anchor,
  not a nudged number.

Dimensions are scored 0–10, higher = better odds, against explicit anchors (see
[`../data-model.md`](../data-model.md) for the full rubric). The composite weighting is
left undecided on purpose until the evaluated queue is deep enough to earn it.

## Adversarial review

This is the red-teaming the README mentions. High-stakes verdicts don't get to pass on
their author's confidence. Before a candidate is
recommended for resources, its central claims are handed to independent, fresh-context
reviewers whose *only* job is to refute them — hunt disconfirming evidence, attack the
weakest link, default to skepticism. Reviewers don't see each other's work or the original
reasoning beyond the claim and its evidence. A refuted claim reverses its verdict;
convergent refutation across independent reviewers carries extra weight.

This catches the failure mode that kills naive scoring: a plausible, well-argued, *wrong*
conclusion that sails through because nobody was assigned to break it.

## Validating invented demand

A candidate detected from complaints can be validated by measuring the complaints. An
*invented* candidate — a product proposed for a routine people tolerate without
complaining — can't be: there is no complaint volume to count, by design. So validation
flips to a forward-looking question: **does the exact person who does this chore already
pay real money — a tool they buy, a human they hire — to remove this exact chore or its
core step?**

Three disciplines keep that question from becoming a rationalization engine:

- **Transactions, not testimonials.** Prices with adoption proof, purchase counts, hired
  labor. Upvotes, stars, and waitlists are not willingness-to-pay.
- **The buyer must be the doer, and the job must be the job.** A paid product bought by a
  different buyer, or solving a neighboring-but-different chore, doesn't transfer —
  however big its market. Almost every routine has *someone* paying for *something*
  nearby; the discipline is what separates signal from wishful proximity.
- **Kills are dated predictions, not verdicts.** A rejected candidate stays reopenable,
  and if reality later contradicts a kill — someone builds a paid product where the test
  said nobody would pay — that's logged as the method's mistake, and the bar recalibrates
  on data instead of argument.

One limitation is accepted on purpose: this bar rejects ideas where nobody pays anything
yet. Creating willingness-to-pay from zero is a venture-scale game — it takes years and
marketing budgets to teach a market a new habit. This system's wager is smaller and
sharper: demand that is one repackaging away from money already moving.

## The improvement loop

The discovery *methods* themselves are instruments, and instruments need calibration. The
system treats method quality as a first-class, measured thing:

- Each candidate records the method that produced it. Gate verdicts accrue into per-method
  scorecards — a method that keeps producing candidates that die at triage is a method
  under review, not a neutral tool.
- Improvement runs as **single, bounded iterations**: one change to one instrument
  (a screen, a rubric anchor, a method, a metric) at a time, so the effect is legible.
  Changes land as proposals and are ratified deliberately, not drifted into.
- **New instruments earn their way in.** A proposed method is exercised on real cases
  *and* on negative controls — inputs it should reject — before ratification. An
  instrument that can't say no doesn't ship; and the controls themselves must be
  verified, because "surely nobody pays for that" is exactly the kind of claim that
  turns out to be wrong when checked.
- **Runs cannot rewrite their own rules.** A discovery run may hunt, kill, park, and
  record freely — but it has no authority to adopt changes to any instrument. Whatever a
  run learns about its own instruments lands as a proposal; a separate, deliberately
  kicked improvement iteration, with its own adversarial review, is the only path to
  ratification.
- A standing tripwire watches for *mode drift* — the tendency of any discovery system to
  slide back toward passively detecting existing demand instead of doing the harder,
  higher-value work of inventing products for tolerated, un-automated routines. The
  tripwire is an early warning, not a gate.

## Governance and autonomy

The agent is autonomous up to the gates and never past them. It may discover, research,
score, red-team, and record a recommendation without asking. It may **not** approve,
reject, launch, or commit real money — those are human actions by construction, and the
CLI is the only path that can perform them. Costed work is reserved against a budget
before it runs; if the reserve is refused, the work does not happen. The result is a
system that can run a rigorous funnel unattended and still leave every irreversible
decision, and every dollar, under human control.
