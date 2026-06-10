"""Tests for the methods page and the audit trail (AC5.1 – AC5.5)."""

import json
import sqlite3

import pytest

from dashboard import build
from dashboard.tests.conftest import SCHEMA

# Fixture per AC5.5: a directive owning two opps with different terminal
# statuses, one unattributed opp, method-tagged knowledge, and a mixed
# event stream.
OPPORTUNITIES = [
    ("opp_won", "LAUNCHED", "2026-06-01T00:00:00Z",
     {"title": "Winner", "directive_id": "dir_1"}),
    ("opp_dead", "REJECTED_LOW_DEMAND", "2026-06-02T00:00:00Z",
     {"title": "Loser", "directive_id": "dir_1"}),
    ("opp_manual", "DISCOVERED", "2026-06-03T00:00:00Z",
     {"title": "Walk-in"}),  # no directive_id: manual / unattributed
]

KNOWLEDGE = [
    ("know_wave", "analysis",
     {"content": "capability wave scan\nsecond line", "tags": ["method-capability-waves"]}),
    ("know_def", "analysis",
     {"content": "method definition", "tags": ["discovery-method"]}),
    ("know_verdict", "analysis",
     {"content": "verdict: keep probing", "tags": ["method-verdict", "method-capability-waves"]}),
    ("know_plain", "signal",
     {"content": "unrelated signal", "tags": ["pricing"]}),  # not a method tag
]

BUDGETS = [
    ("budget_1", "directive", {"allocated": 15.0, "scope": "directive"}),
]

DIRECTIVES = [
    ("dir_1", "active",
     {"prompt": "Hunt capability waves", "venues": [], "budget_id": "budget_1",
      "status": "active", "cadence": None}),
    # No budget_id and no opps: allocated renders as a dash, never a crash.
    ("dir_dry", "active", {"prompt": "Dry directive"}),
]

EVENTS = [
    ("evt_1", "OPP_DISCOVERED", "2026-06-01T00:00:00Z", "scout", "opp_won",
     {"note": "seeded"}),
    ("evt_2", "KNOWLEDGE_ADDED", "2026-06-02T00:00:00Z", "operator", "know_wave",
     {"type": "analysis"}),
    ("evt_3", "OPPORTUNITY_STATE_CHANGED", "2026-06-03T00:00:00Z", "worker:scout",
     "opp_won", {"from": "DISCOVERED", "to": "TRIAGED", "reason": "vetted"}),
    # Target is neither an opportunity nor a knowledge record: plain text.
    ("evt_4", "BUDGET_CREATED", "2026-06-04T00:00:00Z", "human:tim", "budget_1",
     {"allocated": 15.0}),
    ("evt_5", "GATE_RECOMMENDATION", "2026-06-05T00:00:00Z", "worker:mimir",
     "opp_dead", {"recommendation": "reject", "reason": "no demand"}),
]


@pytest.fixture
def methods_db(tmp_path):
    """A fixture database exercising directive lineage, method tags, and a
    mixed event stream."""
    path = tmp_path / "methods.db"
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


@pytest.fixture
def built(methods_db, tmp_path):
    """Run the build once; return the output directory."""
    out_dir = tmp_path / "out"
    build.build(methods_db, out_dir)
    return out_dir


@pytest.fixture
def methods_page(built):
    return (built / "methods.html").read_text(encoding="utf-8")


@pytest.fixture
def events_page(built):
    return (built / "events.html").read_text(encoding="utf-8")


# --- AC5.1: per-directive sections + manual / unattributed -------------------


def test_directive_section_shows_prompt_status_and_budget(methods_page):
    assert '<section id="dir_1">' in methods_page
    assert "Hunt capability waves" in methods_page
    assert "status: active · budget allocated: 15.0" in methods_page


def test_directive_groups_its_opps_with_status_linked_to_detail(methods_page):
    dir_1 = methods_page.index('<section id="dir_1">')
    unattributed = methods_page.index('<section id="unattributed">')
    # Both directive-owned opps sit inside the dir_1 section, terminal
    # statuses linked to their detail pages.
    won = methods_page.index('<a href="opp/opp_won.html">LAUNCHED</a>')
    dead = methods_page.index('<a href="opp/opp_dead.html">REJECTED_LOW_DEMAND</a>')
    assert dir_1 < won < unattributed
    assert dir_1 < dead < unattributed
    assert "<td>Winner</td>" in methods_page
    assert "<td>Loser</td>" in methods_page


def test_unattributed_section_carries_the_manual_opp(methods_page):
    unattributed = methods_page.index('<section id="unattributed">')
    manual = methods_page.index('<a href="opp/opp_manual.html">DISCOVERED</a>')
    assert unattributed < manual
    # The manual opp is not listed under any directive.
    assert manual > methods_page.index("Manual / unattributed")


def test_missing_budget_renders_dash_and_empty_directive_never_crashes(methods_page):
    dir_dry = methods_page.index('<section id="dir_dry">')
    chunk = methods_page[dir_dry : dir_dry + 400]
    assert "budget allocated: —" in chunk
    assert "No opportunities attributed to this directive." in chunk


# --- AC5.2: method-tagged knowledge grouped by tag ----------------------------


def test_method_knowledge_grouped_by_tag_with_anchor_links(methods_page):
    section = methods_page.index('<section id="method-knowledge">')
    waves = methods_page.index('id="method-capability-waves"')
    disc = methods_page.index('id="discovery-method"')
    verdict = methods_page.index('id="method-verdict"')
    # Groups sorted by tag, all inside the method-knowledge section.
    assert section < disc < waves < verdict
    # Each record links to its knowledge.html anchor.
    assert '<a href="knowledge.html#know_wave">know_wave</a>' in methods_page
    assert '<a href="knowledge.html#know_def">know_def</a>' in methods_page
    assert '<a href="knowledge.html#know_verdict">know_verdict</a>' in methods_page
    # First line only as the summary.
    assert "capability wave scan" in methods_page
    assert "second line" not in methods_page


def test_record_with_two_method_tags_appears_in_both_groups(methods_page):
    assert methods_page.count('<a href="knowledge.html#know_verdict">') == 2


def test_non_method_tags_excluded(methods_page):
    section = methods_page[methods_page.index('<section id="method-knowledge">'):]
    assert "know_plain" not in section
    assert "pricing" not in section


def test_is_method_tag_unit():
    assert build.is_method_tag("method-capability-waves")
    assert build.is_method_tag("discovery-method")
    assert build.is_method_tag("method-verdict")
    assert not build.is_method_tag("pricing")
    assert not build.is_method_tag("methodical")  # no hyphen: not a method tag
    assert not build.is_method_tag(None)  # malformed tag: never a crash


# --- AC5.3: full audit trail, latest first, link resolution -------------------


def test_audit_lists_every_event_latest_first(events_page):
    positions = [
        events_page.index(f"<td>{seq}</td><td>2026-06-0{seq}T00:00:00Z</td>")
        for seq in (5, 4, 3, 2, 1)
    ]
    assert positions == sorted(positions)  # seq 5 first, seq 1 last


def test_audit_row_carries_type_actor_and_summary(events_page):
    assert "<td>OPPORTUNITY_STATE_CHANGED</td>" in events_page
    assert "<td>worker:scout</td>" in events_page
    assert "DISCOVERED → TRIAGED — vetted" in events_page
    assert "recommendation: reject — no demand" in events_page
    assert "note: seeded" in events_page  # generic payload: key/value summary


def test_audit_target_links_resolve_by_kind(events_page):
    # Opportunity target: detail-page link.
    assert '<a href="opp/opp_won.html">opp_won</a>' in events_page
    # Knowledge target: knowledge anchor link.
    assert '<a href="knowledge.html#know_wave">know_wave</a>' in events_page
    # Anything else: plain text, no link.
    assert "<td>budget_1</td>" in events_page
    assert 'href="opp/budget_1' not in events_page
    assert 'href="knowledge.html#budget_1' not in events_page


# --- AC5.4: nav + index links --------------------------------------------------


def test_nav_gains_methods_and_audit_on_all_pages(built):
    for name in (
        "index.html",
        "opportunities.html",
        "knowledge.html",
        "methods.html",
        "events.html",
    ):
        html = (built / name).read_text(encoding="utf-8")
        assert '<a href="methods.html">Methods</a>' in html
        assert '<a href="events.html">Audit</a>' in html
    # Detail pages live one level down.
    detail = (built / "opp" / "opp_won.html").read_text(encoding="utf-8")
    assert '<a href="../methods.html">Methods</a>' in detail
    assert '<a href="../events.html">Audit</a>' in detail


def test_index_links_to_both_pages(built):
    index = (built / "index.html").read_text(encoding="utf-8")
    assert '<a href="methods.html">Method performance</a>' in index
    assert '<a href="events.html">Full audit trail</a>' in index


# --- context units --------------------------------------------------------------


def test_methods_context_unit(methods_db):
    from dashboard import db

    conn = db.connect(methods_db)
    try:
        context = build.methods_context(conn)
    finally:
        conn.close()

    by_id = {d["id"]: d for d in context["directives"]}
    assert [o["id"] for o in by_id["dir_1"]["opps"]] == ["opp_dead", "opp_won"]
    assert by_id["dir_1"]["allocated"] == 15.0
    assert by_id["dir_dry"]["allocated"] is None
    assert by_id["dir_dry"]["opps"] == []
    assert [o["id"] for o in context["unattributed"]] == ["opp_manual"]
    assert [t for t, _ in context["method_groups"]] == [
        "discovery-method",
        "method-capability-waves",
        "method-verdict",
    ]


def test_events_context_unit(methods_db):
    from dashboard import db

    conn = db.connect(methods_db)
    try:
        context = build.events_context(conn)
    finally:
        conn.close()

    assert [e["seq"] for e in context["events"]] == [5, 4, 3, 2, 1]
    by_seq = {e["seq"]: e for e in context["events"]}
    assert by_seq[1]["target_kind"] == "opp"
    assert by_seq[2]["target_kind"] == "knowledge"
    assert by_seq[4]["target_kind"] == "plain"
