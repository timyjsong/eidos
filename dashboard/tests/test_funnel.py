"""Tests for the opportunity funnel page and the per-opportunity detail pages
(AC2.1 – AC2.6)."""

import pytest

from dashboard import build


@pytest.fixture
def built(fixture_db, tmp_path):
    """Run the build once; return the output directory."""
    out_dir = tmp_path / "out"
    build.build(fixture_db, out_dir)
    return out_dir


# --- AC2.1: funnel page grouped by status, canonical order ------------------


def test_funnel_sections_in_canonical_order_unknown_last(built):
    html = (built / "opportunities.html").read_text(encoding="utf-8")
    positions = [
        html.index(f'<section id="{status}">')
        for status in ("DISCOVERED", "TRIAGED", "EVALUATED", "AA_FUTURE", "ZZ_FUTURE")
    ]
    assert positions == sorted(positions)


def test_funnel_rows_carry_id_title_updated_and_detail_link(built):
    html = (built / "opportunities.html").read_text(encoding="utf-8")
    assert "<td>opp_1</td><td>Alpha</td><td>2026-06-01T00:00:00Z</td>" in html
    assert '<a href="opp/opp_1.html">' in html
    # Both DISCOVERED opportunities are listed under the one section.
    discovered = html.index('<section id="DISCOVERED">')
    triaged = html.index('<section id="TRIAGED">')
    assert discovered < html.index("opp_1</td>") < triaged
    assert discovered < html.index("opp_2</td>") < triaged


def test_grouped_opportunities_unit():
    opps = [
        {"id": "opp_b", "status": "ZZ_FUTURE"},
        {"id": "opp_a", "status": "DISCOVERED"},
        {"id": "opp_c", "status": "AA_FUTURE"},
    ]
    groups = build.grouped_opportunities(opps)
    assert [status for status, _ in groups] == ["DISCOVERED", "AA_FUTURE", "ZZ_FUTURE"]


# --- AC2.2: detail page per opportunity --------------------------------------


def test_every_opportunity_gets_a_detail_page(built):
    for opp_id in ("opp_1", "opp_2", "opp_3", "opp_4", "opp_5", "opp_6"):
        assert (built / "opp" / f"{opp_id}.html").is_file()


def test_detail_metadata_lineage_and_venues(built):
    html = (built / "opp" / "opp_3.html").read_text(encoding="utf-8")
    assert "<h1>Gamma</h1>" in html
    assert "<td>EVALUATED</td>" in html
    assert "2026-06-01T12:00:00Z" in html  # created_at
    assert "<td>2026-06-03T00:00:00Z</td>" in html  # updated_at
    # Directive lineage: id + prompt.
    assert "dir_1 — Find capability-wave opportunities" in html
    # Known venue resolved to its name; unknown id falls back to the raw id.
    assert "Shopify App Store, venue_ghost" in html  # signal_venues
    assert "<td>Shopify App Store</td>" in html  # target_venues


def test_detail_without_directive_or_venues_renders_dashes(built):
    html = (built / "opp" / "opp_1.html").read_text(encoding="utf-8")
    assert "<th>Directive</th><td>—</td>" in html
    assert "<th>Signal venues</th><td>—</td>" in html
    assert "<th>Target venues</th><td>—</td>" in html


def test_detail_has_scorecard_placeholder_section(built):
    html = (built / "opp" / "opp_3.html").read_text(encoding="utf-8")
    assert '<section id="scorecard">' in html
    assert "<h2>Scorecard</h2>" in html


# --- AC2.3: event history, chronological, from → to --------------------------


def test_event_history_chronological_with_from_to(built):
    html = (built / "opp" / "opp_3.html").read_text(encoding="utf-8")
    first = html.index("DISCOVERED → TRIAGED")
    second = html.index("TRIAGED → EVALUATED")
    assert first < second
    # Timestamp, type and actor are shown.
    assert "2026-06-02T00:00:00Z · OPPORTUNITY_STATE_CHANGED · worker:scout" in html
    # The reason rides along when present.
    assert "DISCOVERED → TRIAGED — vetted" in html


def test_events_are_scoped_to_the_opportunity(built):
    html = (built / "opp" / "opp_3.html").read_text(encoding="utf-8")
    assert "OPP_DISCOVERED" not in html  # evt_1 targets opp_1, not opp_3
    html_2 = (built / "opp" / "opp_2.html").read_text(encoding="utf-8")
    assert "No events recorded for this opportunity." in html_2


def test_missing_payload_key_renders_dash(built):
    html = (built / "opp" / "opp_4.html").read_text(encoding="utf-8")
    assert "— → TRIAGED" in html


def test_event_summary_unit():
    assert (
        build.event_summary(
            {"type": "OPPORTUNITY_STATE_CHANGED", "payload": {"to": "TRIAGED"}}
        )
        == "— → TRIAGED"
    )
    assert build.event_summary({"type": "SCORE_SET", "payload": {}}) == "—"
    assert (
        build.event_summary(
            {
                "type": "SCORE_SET",
                "payload": {"dimension": "pain", "evidence": ["know_1", "know_2"]},
            }
        )
        == "dimension: pain; evidence: know_1, know_2"
    )
    assert build.event_summary({"type": "X", "payload": "plain text"}) == "plain text"


# --- AC2.4: gate recommendation block ----------------------------------------


def test_gate_recommendation_renders_as_distinct_block(built):
    html = (built / "opp" / "opp_3.html").read_text(encoding="utf-8")
    assert '<div class="event gate-rec">' in html
    assert "Recommendation: approve" in html
    assert "strong demand evidence" in html


# --- AC2.5: nav + index links ------------------------------------------------


def test_nav_gains_opportunities_everywhere(built):
    index = (built / "index.html").read_text(encoding="utf-8")
    assert '<a href="opportunities.html">Opportunities</a>' in index
    detail = (built / "opp" / "opp_1.html").read_text(encoding="utf-8")
    assert '<a href="../opportunities.html">Opportunities</a>' in detail
    assert '<a href="../index.html">Overview</a>' in detail


def test_index_counts_link_to_funnel_sections(built):
    index = (built / "index.html").read_text(encoding="utf-8")
    assert '<a href="opportunities.html#DISCOVERED">2</a>' in index
    assert '<a href="opportunities.html#EVALUATED">1</a>' in index
