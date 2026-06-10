"""Tests for the knowledge browser page (AC3.1 – AC3.5)."""

import json
import sqlite3

import pytest

from dashboard import build
from dashboard.tests.conftest import SCHEMA

LONG_CONTENT = "First line summary\n" + "x" * 450

# Richer fixture than the shared one: a superseded → superseding chain, a
# supersede pointer to a missing record, multi-tag records, long content,
# an empty doc, and markup in content.
KNOWLEDGE = [
    (
        "know_old",
        "signal",
        {
            "source": "forum",
            "content": "old observation",
            "tags": ["churn", "pricing"],
            "venue_id": "venue_1",
            "confidence": 0.4,
            "observed_at": "2026-05-01T00:00:00Z",
            "created_at": "2026-05-01T01:00:00Z",
            "superseded_by": "know_new",
        },
    ),
    (
        "know_new",
        "signal",
        {
            "source": "forum",
            "content": "fresh observation",
            "tags": ["pricing"],
            "venue_id": "venue_ghost",  # unknown venue: raw id fallback
            "confidence": 0.8,
            "observed_at": "",  # empty string (real docs do this): fall back
            "created_at": "2026-05-02T00:00:00Z",
            "superseded_by": None,
        },
    ),
    (
        "know_stale",
        "signal",
        {
            "source": "review",
            "content": "points at a record that does not exist",
            "superseded_by": "know_missing",
        },
    ),
    (
        "know_markup",
        "signal",
        {"content": "<script>alert('x')</script>"},
    ),
    (
        "know_long",
        "analysis",
        {
            "source": "operator",
            "content": LONG_CONTENT,
            "tags": ["pricing"],
            "created_at": "2026-05-03T00:00:00Z",
        },
    ),
    ("know_bare", "analysis", {}),  # every key missing: dashes, never a crash
]

VENUES = [("venue_1", "Shopify App Store", {"kind": "marketplace"})]


@pytest.fixture
def knowledge_db(tmp_path):
    """A fixture database exercising the knowledge edge cases."""
    path = tmp_path / "knowledge.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT INTO knowledge VALUES (?, ?, ?)",
        [(i, t, json.dumps(d)) for i, t, d in KNOWLEDGE],
    )
    conn.executemany(
        "INSERT INTO venues VALUES (?, ?, ?)",
        [(i, n, json.dumps(d)) for i, n, d in VENUES],
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def built(knowledge_db, tmp_path):
    """Run the build once; return the output directory."""
    out_dir = tmp_path / "out"
    build.build(knowledge_db, out_dir)
    return out_dir


@pytest.fixture
def page(built):
    return (built / "knowledge.html").read_text(encoding="utf-8")


# --- AC3.1: grouped by type, every field, long content collapsed -------------


def test_records_grouped_by_type_alphabetically(page):
    analysis = page.index('<section id="analysis">')
    signal = page.index('<section id="signal">')
    assert analysis < signal
    # Records sit inside their type section.
    assert analysis < page.index('id="know_long"') < signal
    assert signal < page.index('id="know_old"')
    assert "<h2>signal (4)</h2>" in page
    assert "<h2>analysis (2)</h2>" in page


def test_record_shows_all_fields(page):
    # id · source · observed_at · confidence · venue
    assert (
        "know_old · forum · 2026-05-01T00:00:00Z · confidence: 0.4"
        " · venue: Shopify App Store" in page
    )
    assert '<span class="tag">churn</span> <span class="tag">pricing</span>' in page
    assert "old observation" in page


def test_observed_at_falls_back_to_created_at(page):
    # know_new has observed_at == "" — created_at must show instead.
    assert "know_new · forum · 2026-05-02T00:00:00Z" in page


def test_unknown_venue_falls_back_to_raw_id(page):
    assert "venue: venue_ghost" in page


def test_missing_keys_render_dashes_never_crash(page):
    # know_bare has an empty doc: every field is a dash.
    assert "know_bare · — · — · confidence: — · venue: —" in page
    assert "Tags: —" in page


def test_long_content_collapses_with_first_line_summary(page):
    assert "<details><summary>First line summary</summary>" in page
    # Full text present in the page — never truncated away.
    assert "x" * 450 in page


def test_short_content_renders_plain_not_collapsed(page):
    assert '<p class="content">fresh observation</p>' in page


def test_content_markup_is_escaped(page):
    assert "<script>" not in page
    assert "&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;" in page


# --- AC3.2: supersede chain ---------------------------------------------------


def test_superseded_record_marked_and_links_to_superseder(page):
    know_old = page.index('id="know_old"')
    know_new = page.index('id="know_new"')
    assert 'class="know superseded"' in page[know_old : know_old + 60]
    assert 'Superseded by <a href="#know_new">know_new</a>' in page
    # The superseding record itself is not marked.
    assert "superseded" not in page[know_new : know_new + 60]


def test_missing_superseder_renders_raw_id_without_link(page):
    assert "Superseded by know_missing" in page
    assert 'href="#know_missing"' not in page


# --- AC3.3: tag index ----------------------------------------------------------


def test_tag_index_lists_every_tag_with_record_anchors(page):
    assert '<section id="tag-index">' in page
    assert (
        '<td>churn</td><td><a href="#know_old">know_old</a></td>' in page
    )
    assert (
        '<td>pricing</td><td><a href="#know_long">know_long</a>, '
        '<a href="#know_new">know_new</a>, '
        '<a href="#know_old">know_old</a></td>' in page
    )


# --- AC3.4: stable per-record anchors ------------------------------------------


def test_every_record_has_an_anchor_equal_to_its_id(page):
    for record_id, _, _ in KNOWLEDGE:
        assert f'id="{record_id}"' in page


# --- AC3.5: nav + index links --------------------------------------------------


def test_nav_gains_knowledge(built, fixture_db, tmp_path):
    for name in ("index.html", "opportunities.html", "knowledge.html"):
        html = (built / name).read_text(encoding="utf-8")
        assert '<a href="knowledge.html">Knowledge</a>' in html
    # Detail pages live one level down: the shared fixture has opportunities.
    detail_out = tmp_path / "detail-out"
    build.build(fixture_db, detail_out)
    detail = (detail_out / "opp" / "opp_1.html").read_text(encoding="utf-8")
    assert '<a href="../knowledge.html">Knowledge</a>' in detail


def test_index_knowledge_counts_link_to_type_sections(built):
    index = (built / "index.html").read_text(encoding="utf-8")
    assert '<td>signal</td><td><a href="knowledge.html#signal">4</a></td>' in index
    assert '<td>analysis</td><td><a href="knowledge.html#analysis">2</a></td>' in index


# --- knowledge_context unit ----------------------------------------------------


def test_knowledge_context_unit(knowledge_db):
    from dashboard import db

    conn = db.connect(knowledge_db)
    try:
        context = build.knowledge_context(conn)
    finally:
        conn.close()

    assert [t for t, _ in context["groups"]] == ["analysis", "signal"]
    by_id = {r["id"]: r for _, records in context["groups"] for r in records}
    assert by_id["know_old"]["superseded_by"] == "know_new"
    assert by_id["know_old"]["superseder_known"] is True
    assert by_id["know_stale"]["superseder_known"] is False
    assert by_id["know_long"]["long"] is True
    assert by_id["know_new"]["long"] is False
    assert by_id["know_bare"]["confidence"] == "—"
    assert dict(context["tags"]) == {
        "churn": ["know_old"],
        "pricing": ["know_long", "know_new", "know_old"],
    }
