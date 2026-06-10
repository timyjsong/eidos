"""Shared fixture: a small database in tmp_path with the platform schema.

Tests never touch the live platform.db.
"""

import json
import sqlite3

import pytest

SCHEMA = """
CREATE TABLE opportunities (
  id TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT NOT NULL, doc TEXT NOT NULL);
CREATE TABLE products (
  id TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT NOT NULL, doc TEXT NOT NULL);
CREATE TABLE knowledge (
  id TEXT PRIMARY KEY, type TEXT NOT NULL, doc TEXT NOT NULL);
CREATE TABLE budgets (
  id TEXT PRIMARY KEY, scope TEXT NOT NULL, doc TEXT NOT NULL);
CREATE TABLE permission_policies (
  worker_type TEXT PRIMARY KEY, doc TEXT NOT NULL);
CREATE TABLE worker_runs (
  id TEXT PRIMARY KEY, worker_type TEXT NOT NULL, opportunity_id TEXT, doc TEXT NOT NULL);
CREATE TABLE venues (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, doc TEXT NOT NULL);
CREATE TABLE directives (
  id TEXT PRIMARY KEY, status TEXT NOT NULL, doc TEXT NOT NULL);
CREATE TABLE events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  id TEXT NOT NULL UNIQUE,
  type TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  actor TEXT NOT NULL,
  target_id TEXT NOT NULL,
  payload TEXT NOT NULL);
"""

OPPORTUNITIES = [
    ("opp_1", "DISCOVERED", "2026-06-01T00:00:00Z", {"title": "Alpha"}),
    ("opp_2", "DISCOVERED", "2026-06-02T00:00:00Z", {"title": "Beta"}),
    (
        "opp_3",
        "EVALUATED",
        "2026-06-03T00:00:00Z",
        {
            "title": "Gamma",
            "directive_id": "dir_1",
            "signal_venues": ["venue_1", "venue_ghost"],  # venue_ghost: unknown
            "target_venues": ["venue_1"],
            "created_at": "2026-06-01T12:00:00Z",
        },
    ),
    ("opp_4", "TRIAGED", "2026-06-04T00:00:00Z", {"title": "Delta"}),
    # Statuses outside the canonical list: must not crash the build and must
    # be appended alphabetically after the canonical ones.
    ("opp_5", "ZZ_FUTURE", "2026-06-05T00:00:00Z", {"title": "Epsilon"}),
    ("opp_6", "AA_FUTURE", "2026-06-06T00:00:00Z", {"title": "Zeta"}),
]

KNOWLEDGE = [
    ("know_1", "signal", {"source": "forum", "content": "pain point"}),
    ("know_2", "signal", {"source": "review", "content": "another"}),
    ("know_3", "analysis", {"source": "operator", "content": "synthesis"}),
]

BUDGETS = [
    ("budget_1", "directive", {"allocated": 15.0, "scope": "directive"}),
]

VENUES = [
    ("venue_1", "Shopify App Store", {"kind": "marketplace"}),
]

DIRECTIVES = [
    (
        "dir_1",
        "active",
        {
            "prompt": "Find capability-wave opportunities",
            "venues": ["venue_1"],
            "budget_id": "budget_1",
            "status": "active",
            "cadence": None,
        },
    ),
]

EVENTS = [
    ("evt_1", "OPP_DISCOVERED", "2026-06-01T00:00:00Z", "scout", "opp_1",
     {"note": "seeded"}),
    ("evt_2", "OPPORTUNITY_STATE_CHANGED", "2026-06-02T00:00:00Z",
     "worker:scout", "opp_3", {"from": "DISCOVERED", "to": "TRIAGED",
                               "reason": "vetted"}),
    ("evt_3", "OPPORTUNITY_STATE_CHANGED", "2026-06-03T00:00:00Z",
     "worker:scout", "opp_3", {"from": "TRIAGED", "to": "EVALUATED"}),
    ("evt_4", "GATE_RECOMMENDATION", "2026-06-04T00:00:00Z",
     "worker:mimir", "opp_3", {"recommendation": "approve",
                               "reason": "strong demand evidence"}),
    # Defensive-parsing case: payload missing the "from" key.
    ("evt_5", "OPPORTUNITY_STATE_CHANGED", "2026-06-05T00:00:00Z",
     "worker:scout", "opp_4", {"to": "TRIAGED"}),
]


@pytest.fixture
def fixture_db(tmp_path):
    """Create a populated fixture database; return its path."""
    path = tmp_path / "fixture.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT INTO opportunities VALUES (?, ?, ?, ?)",
        [(i, s, u, json.dumps(d)) for i, s, u, d in OPPORTUNITIES],
    )
    conn.executemany(
        "INSERT INTO knowledge VALUES (?, ?, ?)",
        [(i, t, json.dumps(d)) for i, t, d in KNOWLEDGE],
    )
    conn.executemany(
        "INSERT INTO budgets VALUES (?, ?, ?)",
        [(i, s, json.dumps(d)) for i, s, d in BUDGETS],
    )
    conn.executemany(
        "INSERT INTO venues VALUES (?, ?, ?)",
        [(i, n, json.dumps(d)) for i, n, d in VENUES],
    )
    conn.executemany(
        "INSERT INTO directives VALUES (?, ?, ?)",
        [(i, s, json.dumps(d)) for i, s, d in DIRECTIVES],
    )
    conn.executemany(
        "INSERT INTO events (id, type, timestamp, actor, target_id, payload)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [(i, t, ts, a, tg, json.dumps(p)) for i, t, ts, a, tg, p in EVENTS],
    )
    conn.commit()
    conn.close()
    return path
