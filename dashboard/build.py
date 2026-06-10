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


def grouped_opportunities(opps):
    """Group opportunity rows by status, sections in canonical order; unknown
    statuses follow, alphabetically. An unknown status must never crash."""
    by_status = {}
    for o in opps:
        by_status.setdefault(o["status"], []).append(o)
    known = [s for s in CANONICAL_STATUS_ORDER if s in by_status]
    unknown = sorted(s for s in by_status if s not in CANONICAL_STATUS_ORDER)
    return [
        (status, sorted(by_status[status], key=lambda o: o["id"]))
        for status in known + unknown
    ]


def funnel_context(conn):
    groups = []
    for status, opps in grouped_opportunities(db.opportunities(conn)):
        rows = [
            {
                "id": o["id"],
                "title": o["doc"].get("title", "—"),
                "updated_at": o["updated_at"],
                "scored": score_summary(o["doc"].get("scores")),
            }
            for o in opps
        ]
        groups.append((status, rows))
    return {"groups": groups}


def score_summary(scores):
    """Compact funnel summary: dimension count, or ``unscored``."""
    return f"{len(scores)} dims scored" if scores else "unscored"


def scorecard_rows(scores, known_knowledge_ids):
    """Scorecard table rows from an opp doc's ``scores`` map. A score is
    never a bare float: value and confidence render together as a pair.
    Defensive: a missing value/confidence renders as a dash, never an
    exception; an unknown evidence id is marked unresolved, never a crash."""
    rows = []
    for dimension, score in (scores or {}).items():
        if not isinstance(score, dict):
            score = {}
        value = score.get("value")
        confidence = score.get("confidence")
        evidence = score.get("evidence") or []
        rows.append(
            {
                "dimension": dimension,
                "pair": (
                    f"{'—' if value is None else value}"
                    f" @ conf {'—' if confidence is None else confidence}"
                ),
                "rationale": score.get("rationale") or "—",
                "evidence": [
                    {"id": e, "resolved": e in known_knowledge_ids}
                    for e in evidence
                ],
                "no_evidence": not evidence,
            }
        )
    return rows


def event_summary(event):
    """A readable one-line summary of an event payload. Defensive: a missing
    key renders as a dash, never an exception."""
    payload = event["payload"]
    if not isinstance(payload, dict):
        return str(payload)
    if event["type"] == "OPPORTUNITY_STATE_CHANGED":
        text = f"{payload.get('from', '—')} → {payload.get('to', '—')}"
        reason = payload.get("reason")
        return f"{text} — {reason}" if reason else text
    if event["type"] == "GATE_RECOMMENDATION":
        text = f"recommendation: {payload.get('recommendation', '—')}"
        reason = payload.get("reason")
        return f"{text} — {reason}" if reason else text
    parts = []
    for key, value in payload.items():
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        parts.append(f"{key}: {value}")
    return "; ".join(parts) if parts else "—"


def detail_contexts(conn):
    """One render context per opportunity for the detail page."""
    venue_names = {v["id"]: v["name"] for v in db.venues(conn)}
    directives_by_id = {d["id"]: d for d in db.directives(conn)}
    known_knowledge_ids = {k["id"] for k in db.knowledge(conn)}
    events_by_target = {}
    for e in db.events(conn):  # already ordered by seq (chronology)
        events_by_target.setdefault(e["target_id"], []).append(e)

    contexts = []
    for o in db.opportunities(conn):
        doc = o["doc"]
        directive = None
        directive_id = doc.get("directive_id")
        if directive_id:
            d = directives_by_id.get(directive_id)
            directive = {
                "id": directive_id,
                "prompt": d["doc"].get("prompt", "—") if d else "—",
            }
        events = []
        for e in events_by_target.get(o["id"], []):
            payload = e["payload"] if isinstance(e["payload"], dict) else {}
            events.append(
                {
                    "timestamp": e["timestamp"],
                    "type": e["type"],
                    "actor": e["actor"],
                    "summary": event_summary(e),
                    "is_gate_recommendation": e["type"] == "GATE_RECOMMENDATION",
                    "recommendation": payload.get("recommendation", "—"),
                    "reason": payload.get("reason", "—"),
                }
            )
        contexts.append(
            {
                "root": "../",  # detail pages live one level down, in out/opp/
                "opp": {
                    "id": o["id"],
                    "title": doc.get("title", "—"),
                    "status": o["status"],
                    "created_at": doc.get("created_at", "—"),
                    "updated_at": o["updated_at"],
                },
                "directive": directive,
                # Unknown venue ids fall back to the raw id — never a crash.
                "signal_venues": [
                    venue_names.get(v, v) for v in doc.get("signal_venues") or []
                ],
                "target_venues": [
                    venue_names.get(v, v) for v in doc.get("target_venues") or []
                ],
                "scores": scorecard_rows(doc.get("scores"), known_knowledge_ids),
                "events": events,
            }
        )
    return contexts


# Content longer than this renders inside a collapsed <details> element.
LONG_CONTENT_CHARS = 400


def knowledge_context(conn):
    """Render context for the knowledge browser: records grouped by type
    (alphabetical), plus a tag index. Defensive: a missing doc key renders
    as a dash, never an exception."""
    venue_names = {v["id"]: v["name"] for v in db.venues(conn)}
    records = db.knowledge(conn)
    known_ids = {k["id"] for k in records}

    by_type = {}
    tag_index = {}
    for k in sorted(records, key=lambda k: k["id"]):
        doc = k["doc"]
        content = doc.get("content") or ""
        tags = doc.get("tags") or []
        venue_id = doc.get("venue_id")
        confidence = doc.get("confidence")
        superseded_by = doc.get("superseded_by")
        record = {
            "id": k["id"],
            "source": doc.get("source") or "—",
            # observed_at can be missing OR an empty string in real docs.
            "observed_at": doc.get("observed_at") or doc.get("created_at") or "—",
            "confidence": "—" if confidence is None else confidence,
            "tags": tags,
            # Unknown venue ids fall back to the raw id — never a crash.
            "venue": venue_names.get(venue_id, venue_id) if venue_id else "—",
            "content": content,
            "long": len(content) > LONG_CONTENT_CHARS,
            "first_line": content.splitlines()[0] if content else "—",
            "superseded_by": superseded_by,
            # The superseding record is not required to exist (AC3.2).
            "superseder_known": superseded_by in known_ids,
        }
        by_type.setdefault(k["type"], []).append(record)
        for tag in tags:
            tag_index.setdefault(tag, []).append(k["id"])

    return {
        "groups": [(t, by_type[t]) for t in sorted(by_type)],
        "tags": [(t, tag_index[t]) for t in sorted(tag_index)],
    }


def is_method_tag(tag):
    """A tag carries method knowledge if it starts with ``method-`` or is
    one of the standing method tags (AC5.2)."""
    return isinstance(tag, str) and (
        tag.startswith("method-") or tag in ("discovery-method", "method-verdict")
    )


def methods_context(conn):
    """Render context for the method performance page: per-directive sections
    (the directive's opportunities and where they ended up), a manual /
    unattributed section, and method-tagged knowledge grouped by tag. No
    invented metrics — directive lineage and tag groupings only."""
    budgets_by_id = {b["id"]: b for b in db.budgets(conn)}

    opps_by_directive = {}
    unattributed = []
    for o in sorted(db.opportunities(conn), key=lambda o: o["id"]):
        row = {
            "id": o["id"],
            "title": o["doc"].get("title", "—"),
            "status": o["status"],
        }
        directive_id = o["doc"].get("directive_id")
        if directive_id:
            opps_by_directive.setdefault(directive_id, []).append(row)
        else:
            unattributed.append(row)

    directive_rows = []
    for d in sorted(db.directives(conn), key=lambda d: d["id"]):
        # A missing budget renders as a dash — never a crash.
        budget = budgets_by_id.get(d["doc"].get("budget_id"))
        directive_rows.append(
            {
                "id": d["id"],
                "prompt": d["doc"].get("prompt", "—"),
                "status": d["status"],
                "allocated": budget["doc"].get("allocated") if budget else None,
                "opps": opps_by_directive.get(d["id"], []),
            }
        )

    method_groups = {}
    for k in sorted(db.knowledge(conn), key=lambda k: k["id"]):
        content = k["doc"].get("content") or ""
        for tag in k["doc"].get("tags") or []:
            if is_method_tag(tag):
                method_groups.setdefault(tag, []).append(
                    {
                        "id": k["id"],
                        "first_line": content.splitlines()[0] if content else "—",
                    }
                )

    return {
        "directives": directive_rows,
        "unattributed": unattributed,
        "method_groups": [(t, method_groups[t]) for t in sorted(method_groups)],
    }


def events_context(conn):
    """Render context for the full audit trail: every event, latest first.
    A target_id that matches an opportunity links to its detail page; one
    that matches a knowledge record links to its knowledge anchor; anything
    else renders as plain text."""
    opp_ids = {o["id"] for o in db.opportunities(conn)}
    knowledge_ids = {k["id"] for k in db.knowledge(conn)}

    rows = []
    for e in db.events(conn):  # ordered by seq ascending
        target_id = e["target_id"]
        if target_id in opp_ids:
            target_kind = "opp"
        elif target_id in knowledge_ids:
            target_kind = "knowledge"
        else:
            target_kind = "plain"
        rows.append(
            {
                "seq": e["seq"],
                "timestamp": e["timestamp"],
                "type": e["type"],
                "actor": e["actor"],
                "target_id": target_id,
                "target_kind": target_kind,
                "summary": event_summary(e),
            }
        )
    rows.reverse()  # latest first (seq desc)
    return {"events": rows}


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
        index_html = env.get_template("index.html").render(overview_context(conn))
        funnel_html = env.get_template("opportunities.html").render(
            funnel_context(conn)
        )
        knowledge_html = env.get_template("knowledge.html").render(
            knowledge_context(conn)
        )
        methods_html = env.get_template("methods.html").render(methods_context(conn))
        events_html = env.get_template("events.html").render(events_context(conn))
        details = detail_contexts(conn)
    finally:
        conn.close()

    (out_dir / "index.html").write_text(index_html, encoding="utf-8")
    (out_dir / "opportunities.html").write_text(funnel_html, encoding="utf-8")
    (out_dir / "knowledge.html").write_text(knowledge_html, encoding="utf-8")
    (out_dir / "methods.html").write_text(methods_html, encoding="utf-8")
    (out_dir / "events.html").write_text(events_html, encoding="utf-8")

    opp_dir = out_dir / "opp"
    opp_dir.mkdir(parents=True, exist_ok=True)
    detail_template = env.get_template("opp_detail.html")
    for context in details:
        (opp_dir / f"{context['opp']['id']}.html").write_text(
            detail_template.render(context), encoding="utf-8"
        )


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
