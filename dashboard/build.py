"""Build entrypoint: render the static dashboard from the database.

Run as ``.venv/bin/python -m dashboard.build`` from the repo root. Reads the
database strictly read-only (via :mod:`dashboard.db`) and writes HTML pages to
the output directory.
"""

import argparse
from collections import Counter
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from dashboard import db

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "platform.db"
DEFAULT_OUT = REPO_ROOT / "dashboard" / "out"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# Canonical opportunity status order (hard-coded here on purpose: the
# dashboard never imports core — ADR-0016).
CANONICAL_STATUS_ORDER = [
    "DISCOVERED",
    "TRIAGED",
    "EVALUATED",
    "APPROVED",
    "VALIDATED",
    "BUILDING",
    "READY",
    "LAUNCHED",
    "ON_HOLD",
    "REJECTED_SATURATED",
    "REJECTED_LOW_DEMAND",
    "REJECTED_LOW_ROI",
    "REJECTED_HIGH_RISK",
    "REJECTED_STRATEGIC_MISALIGNMENT",
    "ARCHIVED",
]


def ordered_status_counts(counts):
    """Order (status, count) pairs canonically; unknown statuses follow,
    alphabetically. An unknown status must never crash the build."""
    known = [(s, counts[s]) for s in CANONICAL_STATUS_ORDER if s in counts]
    unknown = sorted(
        (s, c) for s, c in counts.items() if s not in CANONICAL_STATUS_ORDER
    )
    return known + unknown


def overview_context(conn):
    opps = db.opportunities(conn)
    status_counts = Counter(o["status"] for o in opps)
    type_counts = Counter(k["type"] for k in db.knowledge(conn))
    budgets_by_id = {b["id"]: b for b in db.budgets(conn)}

    directive_rows = []
    for d in db.directives(conn):
        budget = budgets_by_id.get(d["doc"].get("budget_id"))
        directive_rows.append(
            {
                "id": d["id"],
                "prompt": d["doc"].get("prompt", ""),
                "status": d["status"],
                "allocated": budget["doc"].get("allocated") if budget else None,
            }
        )

    return {
        "status_counts": ordered_status_counts(status_counts),
        "knowledge_counts": sorted(type_counts.items()),
        "directives": directive_rows,
        "evaluated_count": status_counts.get("EVALUATED", 0),
    }


def build(db_path, out_dir):
    """Render all pages from *db_path* into *out_dir*."""
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = db.connect(db_path)
    try:
        html = env.get_template("index.html").render(overview_context(conn))
    finally:
        conn.close()
    (out_dir / "index.html").write_text(html, encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="dashboard.build", description="Build the static EIDOS dashboard."
    )
    parser.add_argument("--db", default=str(DEFAULT_DB), help="path to the database")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output directory")
    args = parser.parse_args(argv)
    build(Path(args.db), Path(args.out))


if __name__ == "__main__":
    main()
