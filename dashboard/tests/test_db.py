"""Tests for the read-only data layer (AC1.2, AC1.3)."""

import re
import sqlite3
from pathlib import Path

import pytest

from dashboard import db

DASHBOARD_DIR = Path(db.__file__).resolve().parent


def test_write_attempt_raises_operational_error(fixture_db):
    conn = db.connect(fixture_db)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute(
                "INSERT INTO venues VALUES ('venue_x', 'Sneaky', '{}')"
            )
    finally:
        conn.close()


def test_query_functions_return_dicts_with_parsed_doc(fixture_db):
    conn = db.connect(fixture_db)
    try:
        opps = db.opportunities(conn)
        assert len(opps) == 6
        opp = next(o for o in opps if o["id"] == "opp_1")
        assert opp["status"] == "DISCOVERED"
        assert opp["doc"] == {"title": "Alpha"}

        know = db.knowledge(conn)
        assert len(know) == 3
        assert know[0]["doc"]["source"] in ("forum", "review", "operator")

        budgets = db.budgets(conn)
        assert budgets[0]["doc"]["allocated"] == 15.0

        directives = db.directives(conn)
        assert directives[0]["doc"]["budget_id"] == "budget_1"

        venues = db.venues(conn)
        assert venues[0]["name"] == "Shopify App Store"
        assert venues[0]["doc"] == {"kind": "marketplace"}

        events = db.events(conn)
        assert events[0]["payload"] == {"note": "seeded"}
        assert events[0]["seq"] == 1
    finally:
        conn.close()


def test_no_dashboard_module_imports_core():
    """ADR-0016 isolation: nothing under dashboard/ may import core."""
    pattern = re.compile(r"^\s*(import|from)\s+core(\.|\s|$)")
    offenders = []
    for py in DASHBOARD_DIR.rglob("*.py"):
        for lineno, line in enumerate(
            py.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if pattern.match(line):
                offenders.append(f"{py}:{lineno}: {line.strip()}")
    assert not offenders, "\n".join(offenders)
