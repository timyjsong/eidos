"""Read-only data layer for the dashboard.

All database access goes through this module. Connections are opened with
SQLite's read-only URI mode, so any write attempt raises
``sqlite3.OperationalError``. The dashboard never imports ``core`` (ADR-0016).
"""

import json
import sqlite3


def connect(path):
    """Open *path* strictly read-only. Returns a sqlite3.Connection."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn, sql, json_column="doc"):
    out = []
    for row in conn.execute(sql):
        record = dict(row)
        record[json_column] = json.loads(record[json_column])
        out.append(record)
    return out


def opportunities(conn):
    return _rows(conn, "SELECT id, status, updated_at, doc FROM opportunities")


def knowledge(conn):
    return _rows(conn, "SELECT id, type, doc FROM knowledge")


def budgets(conn):
    return _rows(conn, "SELECT id, scope, doc FROM budgets")


def directives(conn):
    return _rows(conn, "SELECT id, status, doc FROM directives")


def venues(conn):
    return _rows(conn, "SELECT id, name, doc FROM venues")


def events(conn):
    out = []
    for row in conn.execute(
        "SELECT seq, id, type, timestamp, actor, target_id, payload"
        " FROM events ORDER BY seq"
    ):
        record = dict(row)
        try:
            record["payload"] = json.loads(record["payload"])
        except (json.JSONDecodeError, TypeError):
            pass  # malformed payload: keep the raw value, never an exception
        out.append(record)
    return out
