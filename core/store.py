"""SQLite persistence: JSON document columns (decisions/0002), append-only events.

There are deliberately no delete methods anywhere. Archive, supersede — never destroy.
"""
import json
import sqlite3

from .schemas import (
    Budget,
    Directive,
    Event,
    KnowledgeRecord,
    Opportunity,
    PermissionPolicy,
    Product,
    Venue,
    WorkerRun,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
  id TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT NOT NULL, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products (
  id TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT NOT NULL, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS knowledge (
  id TEXT PRIMARY KEY, type TEXT NOT NULL, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS budgets (
  id TEXT PRIMARY KEY, scope TEXT NOT NULL, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS permission_policies (
  worker_type TEXT PRIMARY KEY, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS worker_runs (
  id TEXT PRIMARY KEY, worker_type TEXT NOT NULL, opportunity_id TEXT, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS venues (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS directives (
  id TEXT PRIMARY KEY, status TEXT NOT NULL, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  id TEXT NOT NULL UNIQUE,
  type TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  actor TEXT NOT NULL,
  target_id TEXT NOT NULL,
  payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_events_target ON events(target_id);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
  BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
  BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
"""


class Store:
    def __init__(self, path=":memory:"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    # ---- events (append-only) ----

    def emit(self, event_type, actor, target_id, payload=None):
        event = Event(type=event_type, actor=actor, target_id=target_id, payload=payload or {})
        self.conn.execute(
            "INSERT INTO events (id, type, timestamp, actor, target_id, payload)"
            " VALUES (?,?,?,?,?,?)",
            (event.id, event.type, event.timestamp, event.actor, event.target_id,
             json.dumps(event.payload)),
        )
        self.conn.commit()
        return event

    def events_for(self, target_id):
        rows = self.conn.execute(
            "SELECT * FROM events WHERE target_id = ? ORDER BY seq", (target_id,)
        )
        return [self._row_to_event(r) for r in rows]

    def events_of_type(self, event_type, target_id=None):
        if target_id is None:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE type = ? ORDER BY seq", (event_type,)
            )
        else:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE type = ? AND target_id = ? ORDER BY seq",
                (event_type, target_id),
            )
        return [self._row_to_event(r) for r in rows]

    def all_events(self):
        rows = self.conn.execute("SELECT * FROM events ORDER BY seq")
        return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(row):
        return Event(
            id=row["id"], type=row["type"], timestamp=row["timestamp"],
            actor=row["actor"], target_id=row["target_id"],
            payload=json.loads(row["payload"]),
        )

    # ---- registries (upsert only) ----

    def _upsert(self, table, key_cols, key_vals, doc):
        cols = ", ".join(key_cols + ["doc"])
        marks = ", ".join("?" for _ in range(len(key_cols) + 1))
        updates = ", ".join(f"{c}=excluded.{c}" for c in key_cols[1:] + ["doc"])
        self.conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({marks})"
            f" ON CONFLICT({key_cols[0]}) DO UPDATE SET {updates}",
            (*key_vals, json.dumps(doc)),
        )
        self.conn.commit()

    def _get_doc(self, table, key_col, key, cls):
        row = self.conn.execute(
            f"SELECT doc FROM {table} WHERE {key_col} = ?", (key,)
        ).fetchone()
        return cls.from_doc(json.loads(row["doc"])) if row else None

    def save_opportunity(self, opp):
        self._upsert("opportunities", ["id", "status", "updated_at"],
                     [opp.id, opp.status, opp.updated_at], opp.to_doc())

    def get_opportunity(self, opp_id):
        return self._get_doc("opportunities", "id", opp_id, Opportunity)

    def list_opportunities(self, status=None):
        if status is None:
            rows = self.conn.execute("SELECT doc FROM opportunities ORDER BY id")
        else:
            rows = self.conn.execute(
                "SELECT doc FROM opportunities WHERE status = ? ORDER BY id", (status,)
            )
        return [Opportunity.from_doc(json.loads(r["doc"])) for r in rows]

    def save_product(self, product):
        self._upsert("products", ["id", "status", "updated_at"],
                     [product.id, product.status, product.updated_at], product.to_doc())

    def get_product(self, product_id):
        return self._get_doc("products", "id", product_id, Product)

    def save_knowledge(self, record):
        self._upsert("knowledge", ["id", "type"], [record.id, record.type], record.to_doc())

    def get_knowledge(self, record_id):
        return self._get_doc("knowledge", "id", record_id, KnowledgeRecord)

    def save_budget(self, budget):
        self._upsert("budgets", ["id", "scope"], [budget.id, budget.scope], budget.to_doc())

    def get_budget(self, budget_id):
        return self._get_doc("budgets", "id", budget_id, Budget)

    def save_policy(self, policy):
        self._upsert("permission_policies", ["worker_type"],
                     [policy.worker_type], policy.to_doc())

    def get_policy(self, worker_type):
        return self._get_doc("permission_policies", "worker_type", worker_type, PermissionPolicy)

    def save_venue(self, venue):
        self._upsert("venues", ["id", "name"], [venue.id, venue.name], venue.to_doc())

    def get_venue(self, venue_id):
        return self._get_doc("venues", "id", venue_id, Venue)

    def list_venues(self):
        rows = self.conn.execute("SELECT doc FROM venues ORDER BY id")
        return [Venue.from_doc(json.loads(r["doc"])) for r in rows]

    def save_directive(self, directive):
        self._upsert("directives", ["id", "status"],
                     [directive.id, directive.status], directive.to_doc())

    def get_directive(self, directive_id):
        return self._get_doc("directives", "id", directive_id, Directive)

    def list_directives(self):
        rows = self.conn.execute("SELECT doc FROM directives ORDER BY id")
        return [Directive.from_doc(json.loads(r["doc"])) for r in rows]

    def save_run(self, run):
        self._upsert("worker_runs", ["id", "worker_type", "opportunity_id"],
                     [run.id, run.worker_type, run.opportunity_id], run.to_doc())

    def get_run(self, run_id):
        return self._get_doc("worker_runs", "id", run_id, WorkerRun)

    def list_runs(self, opportunity_id=None):
        if opportunity_id is None:
            rows = self.conn.execute("SELECT doc FROM worker_runs ORDER BY id")
        else:
            rows = self.conn.execute(
                "SELECT doc FROM worker_runs WHERE opportunity_id = ? ORDER BY id",
                (opportunity_id,),
            )
        return [WorkerRun.from_doc(json.loads(r["doc"])) for r in rows]
