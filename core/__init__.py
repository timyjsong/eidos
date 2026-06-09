"""Core framework: schemas, store, state machine, governance, orchestrator shell.

Workers live outside this package — core/ must never know about any specific worker.
"""

# Stamped into every state-change event: decisions inherit the maturity of the
# system that made them (decisions/0012). Bump when decision-relevant machinery changes.
PLATFORM_VERSION = "0.4"
