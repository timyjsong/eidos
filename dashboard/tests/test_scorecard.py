"""Tests for the scorecard on the detail page and the funnel summary
(AC4.1 – AC4.5). The shared fixture's opp_3 carries the scores: a dimension
with resolving evidence, one with empty evidence, one with an unresolvable
evidence id, and one missing value/confidence entirely."""

import pytest

from dashboard import build


@pytest.fixture
def built(fixture_db, tmp_path):
    """Run the build once; return the output directory."""
    out_dir = tmp_path / "out"
    build.build(fixture_db, out_dir)
    return out_dir


@pytest.fixture
def detail(built):
    return (built / "opp" / "opp_3.html").read_text(encoding="utf-8")


# --- AC4.1: value + confidence rendered together, never a bare float ---------


def test_scorecard_rows_pair_value_and_confidence(detail):
    assert (
        "<td>pain</td><td>7.0 @ conf 0.7</td><td>recurring forum demand</td>"
        in detail
    )
    assert "<td>market</td><td>6.0 @ conf 0.6</td>" in detail
    # No score value renders as a bare float in its own cell.
    for bare in ("<td>7.0</td>", "<td>6.0</td>", "<td>4.5</td>"):
        assert bare not in detail


def test_missing_value_or_confidence_renders_dash_never_crash(detail):
    # cost has neither value nor confidence recorded.
    assert "<td>cost</td><td>— @ conf —</td><td>not yet estimated</td>" in detail


# --- AC4.2: evidence ids link to the knowledge browser ------------------------


def test_evidence_ids_link_to_knowledge_anchors(detail, built):
    assert '<a href="../knowledge.html#know_1">know_1</a>' in detail
    assert '<a href="../knowledge.html#know_2">know_2</a>' in detail
    # The link target exists on the built knowledge page.
    knowledge = (built / "knowledge.html").read_text(encoding="utf-8")
    assert 'id="know_1"' in knowledge


def test_unresolved_evidence_id_renders_plain_text(detail):
    assert "know_ghost (unresolved)" in detail
    assert 'href="../knowledge.html#know_ghost"' not in detail


# --- AC4.3: empty or missing evidence flagged as opinion ----------------------


def test_empty_evidence_list_flagged_as_opinion(detail):
    market = detail.index("<td>market</td>")
    moat = detail.index("<td>moat</td>")
    assert "no evidence — opinion" in detail[market:moat]


def test_missing_evidence_key_flagged_as_opinion(detail):
    cost = detail.index("<td>cost</td>")
    assert "no evidence — opinion" in detail[cost:]


# --- AC4.4: funnel summary + unscored empty state ------------------------------


def test_funnel_rows_carry_score_summary(built):
    html = (built / "opportunities.html").read_text(encoding="utf-8")
    assert (
        "<td>opp_3</td><td>Gamma</td><td>2026-06-03T00:00:00Z</td>"
        "<td>4 dims scored</td>" in html
    )
    assert (
        "<td>opp_1</td><td>Alpha</td><td>2026-06-01T00:00:00Z</td>"
        "<td>unscored</td>" in html
    )


def test_unscored_detail_page_shows_empty_state(built):
    html = (built / "opp" / "opp_1.html").read_text(encoding="utf-8")
    assert "No scores recorded for this opportunity." in html
    # The scorecard section survives from story 1-2.
    assert '<section id="scorecard">' in html


# --- scorecard_rows / score_summary units ---------------------------------------


def test_scorecard_rows_unit():
    rows = build.scorecard_rows(
        {
            "pain": {
                "value": 7.0,
                "confidence": 0.7,
                "rationale": "r",
                "evidence": ["know_a", "know_x"],
            },
            "cost": {},
        },
        known_knowledge_ids={"know_a"},
    )
    assert rows[0]["pair"] == "7.0 @ conf 0.7"
    assert rows[0]["evidence"] == [
        {"id": "know_a", "resolved": True},
        {"id": "know_x", "resolved": False},
    ]
    assert rows[0]["no_evidence"] is False
    assert rows[1] == {
        "dimension": "cost",
        "pair": "— @ conf —",
        "rationale": "—",
        "evidence": [],
        "no_evidence": True,
    }
    assert build.scorecard_rows(None, set()) == []
    # A non-dict score entry degrades to dashes, never a crash.
    assert build.scorecard_rows({"odd": 3.0}, set())[0]["pair"] == "— @ conf —"


def test_score_summary_unit():
    assert build.score_summary({"pain": {}, "market": {}}) == "2 dims scored"
    assert build.score_summary({}) == "unscored"
    assert build.score_summary(None) == "unscored"
