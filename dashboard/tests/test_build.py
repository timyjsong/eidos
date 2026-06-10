"""Tests for the build entrypoint and the overview page (AC1.1, AC1.4, AC1.5)."""

import subprocess
import sys
from pathlib import Path

from dashboard import build

REPO_ROOT = Path(build.__file__).resolve().parent.parent


def test_build_writes_index_html(fixture_db, tmp_path):
    out_dir = tmp_path / "out"  # does not exist yet: build must create it
    build.build(fixture_db, out_dir)
    assert (out_dir / "index.html").is_file()


def test_index_carries_expected_counts(fixture_db, tmp_path):
    out_dir = tmp_path / "out"
    build.build(fixture_db, out_dir)
    html = (out_dir / "index.html").read_text(encoding="utf-8")

    # Opportunity counts by status (counts link to the funnel sections, AC2.5).
    assert '<td>DISCOVERED</td><td><a href="opportunities.html#DISCOVERED">2</a></td>' in html
    assert '<td>TRIAGED</td><td><a href="opportunities.html#TRIAGED">1</a></td>' in html
    assert '<td>EVALUATED</td><td><a href="opportunities.html#EVALUATED">1</a></td>' in html
    # Knowledge counts by type (counts link to the type sections, AC3.5).
    assert '<td>signal</td><td><a href="knowledge.html#signal">2</a></td>' in html
    assert '<td>analysis</td><td><a href="knowledge.html#analysis">1</a></td>' in html
    # Directive with status and budget allocated.
    assert "dir_1" in html
    assert "<td>active</td>" in html
    assert "<td>15.0</td>" in html
    # EVALUATED count labeled as awaiting the human gate.
    assert "Awaiting the human gate (EVALUATED): <strong>1</strong>" in html


def test_unknown_statuses_appended_alphabetically(fixture_db, tmp_path):
    out_dir = tmp_path / "out"
    build.build(fixture_db, out_dir)  # unknown statuses must not crash
    html = (out_dir / "index.html").read_text(encoding="utf-8")

    canonical_pos = html.index("<td>EVALUATED</td>")
    aa_pos = html.index("<td>AA_FUTURE</td>")
    zz_pos = html.index("<td>ZZ_FUTURE</td>")
    assert canonical_pos < aa_pos < zz_pos


def test_ordered_status_counts_unit():
    counts = {"ZZ_FUTURE": 1, "DISCOVERED": 2, "AA_FUTURE": 3, "ARCHIVED": 4}
    assert build.ordered_status_counts(counts) == [
        ("DISCOVERED", 2),
        ("ARCHIVED", 4),
        ("AA_FUTURE", 3),
        ("ZZ_FUTURE", 1),
    ]


def test_cli_flags_db_and_out(fixture_db, tmp_path):
    out_dir = tmp_path / "cli-out"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dashboard.build",
            "--db",
            str(fixture_db),
            "--out",
            str(out_dir),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (out_dir / "index.html").is_file()
