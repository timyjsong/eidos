"""Core framework: schemas, store, state machine, governance, orchestrator shell.

Stdlib-only by decision (decisions/0001). Workers live outside this package —
core/ must never know about any specific worker.
"""
