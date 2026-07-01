# Methodology

EIDOS is built around one wager: the hard part of software isn't building — it's *choosing
what to build* — and the best things to build are the ones you have to **create the case
for**, not the ones already screaming for attention.

Most idea-sourcing *detects*: scrape complaints, rank by volume, ship the loudest. That
space is crowded and its winners are already taken. EIDOS is designed to *generate*
instead — to compound weak signals across domains, surface latent demand nobody has named,
and reason toward products for tolerated, un-automated routines. The discovery loop is the
heart of the system; the governance around it (evidence, scoring, adversarial review,
human gates) exists to keep a creative process honest rather than let it hallucinate.

This document is deliberately generic. The specific markets and candidates an operator
runs through the loop are theirs — not part of this repo.

## The pipeline

Every candidate opportunity is an artifact that moves through decision phases:

```
discover → triage → evaluate (score + evidence) → [human gate] → validate → build → launch
```

Phases are *decisions*, not activity. A worker's progress lives in the artifact's data,
never in a new state — so adding capability never means re-plumbing the state machine.
Each phase transition is an append-only event; the whole trajectory is reconstructable
from the log.

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
  that produced it. Before comparing old candidates to new, re-score the old under the
  current rubric — cross-regime comparison is meaningless.
- **Blind re-score audits.** Periodically re-score a sample without looking at prior
  scores. Drift beyond one band reveals rubric ambiguity — the fix is a sharper anchor,
  not a nudged number.

Dimensions are scored 0–10, higher = better odds, against explicit anchors (see
[`../data-model.md`](../data-model.md) for the full rubric). The composite weighting is
left undecided on purpose until the evaluated queue is deep enough to earn it.

## Adversarial review

High-stakes verdicts don't get to pass on their author's confidence. Before a candidate is
recommended for resources, its central claims are handed to independent, fresh-context
reviewers whose *only* job is to refute them — hunt disconfirming evidence, attack the
weakest link, default to skepticism. Reviewers don't see each other's work or the original
reasoning beyond the claim and its evidence. A refuted claim reverses its verdict;
convergent refutation across independent reviewers carries extra weight.

This catches the failure mode that kills naive scoring: a plausible, well-argued, *wrong*
conclusion that sails through because nobody was assigned to break it.

## The improvement loop

The discovery *methods* themselves are instruments, and instruments need calibration. The
system treats method quality as a first-class, measured thing:

- Each candidate records the method that produced it. Gate verdicts accrue into per-method
  scorecards — a method that keeps producing candidates that die at triage is a method
  under review, not a neutral tool.
- Improvement runs as **single, bounded iterations**: one change to one instrument
  (a screen, a rubric anchor, a method, a metric) at a time, so the effect is legible.
  Changes land as proposals and are ratified deliberately, not drifted into.
- A standing tripwire watches for *mode drift* — the tendency of any discovery system to
  slide back toward passively detecting existing demand instead of doing the harder,
  higher-value work of inventing products for tolerated, un-automated routines. The
  tripwire is an early warning, not a gate.

## Governance and autonomy

The operator is autonomous up to the gates and never past them. It may discover, research,
score, red-team, and record a recommendation without asking. It may **not** approve,
reject, launch, or commit real money — those are human actions by construction, and the
CLI is the only path that can perform them. Costed work is reserved against a budget
before it runs; if the reserve is refused, the work does not happen. The result is a
system that can run a rigorous funnel unattended and still leave every irreversible
decision, and every dollar, under human control.
