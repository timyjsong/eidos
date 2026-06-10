"""The platform CLI — the ONLY write path to platform state (ADR-0010).

Interactive sessions operate the platform through these commands; nothing writes to
the database any other way. Human-only actions (approve/reject/reopen/launch/budget)
default the actor to the human running the session.
"""
import argparse
import getpass
import json
import os

from . import budget as budgets
from . import event_types as ev
from . import state_machine
from .orchestrator import launch_product
from .schemas import Directive, KnowledgeRecord, Opportunity, Score, Venue
from .store import Store

DEFAULT_DB = os.environ.get("PLATFORM_DB", "platform.db")


def _human():
    return f"human:{getpass.getuser()}"


def _store(args):
    return Store(args.db)


def cmd_status(store, args):
    by_status = {}
    for opp in store.list_opportunities():
        by_status.setdefault(opp.status, []).append(opp.id)
    print("Opportunities:")
    for status in state_machine.ALL_OPPORTUNITY_STATES:
        if status in by_status:
            print(f"  {status:<32} {len(by_status[status])}")
    print(f"Venues: {len(store.list_venues())} · Directives: {len(store.list_directives())}")
    for budget in [store.get_budget(b) for b in _budget_ids(store)]:
        print(f"Budget {budget.id} [{budget.scope}] allocated={budget.allocated:.2f} "
              f"consumed={budgets.consumed(store, budget.id):.2f} "
              f"remaining={budgets.remaining(store, budget.id):.2f}")


def _budget_ids(store):
    rows = store.conn.execute("SELECT id FROM budgets ORDER BY id")
    return [r["id"] for r in rows]


def cmd_venue_add(store, args):
    profile = json.loads(args.profile) if args.profile else None
    venue = Venue(name=args.name, kind=args.kind, **({"profile": profile} if profile else {}))
    store.save_venue(venue)
    store.emit(ev.VENUE_ADDED, _human(), venue.id, {"name": venue.name, "kind": venue.kind})
    print(venue.id)


def cmd_venue_list(store, args):
    for venue in store.list_venues():
        print(f"{venue.id}  {venue.name} ({venue.kind})")


def cmd_directive_add(store, args):
    budget_id = None
    if args.budget is not None:
        budget_id = budgets.create_budget(store, f"directive:{args.prompt[:40]}",
                                          args.budget, actor=_human()).id
    directive = Directive(prompt=args.prompt,
                          venues=args.venues.split(",") if args.venues else [],
                          budget_id=budget_id, cadence=args.cadence)
    store.save_directive(directive)
    store.emit(ev.DIRECTIVE_CREATED, _human(), directive.id,
               {"prompt": directive.prompt, "venues": directive.venues,
                "budget_id": budget_id})
    print(directive.id)


def cmd_directive_list(store, args):
    for d in store.list_directives():
        print(f"{d.id}  [{d.status}] {d.prompt} venues={d.venues} budget={d.budget_id}")


def cmd_directive_close(store, args):
    directive = store.get_directive(args.id)
    if directive is None:
        raise SystemExit(f"no such directive: {args.id}")
    directive.status = "CLOSED"
    store.save_directive(directive)
    store.emit(ev.DIRECTIVE_CLOSED, args.actor or _human(), directive.id,
               {"reason": args.reason})
    print(f"{directive.id} -> CLOSED")


def cmd_seed(store, args):
    actor = args.actor or _human()
    source = "human" if actor.startswith("human:") else "discovery"
    opp = Opportunity(title=args.title,
                      directive_id=args.directive,
                      signal_venues=args.signal_venues.split(",") if args.signal_venues else [])
    if args.method:
        opp.discovery["method"] = args.method
    store.save_opportunity(opp)
    store.emit(ev.OPPORTUNITY_CREATED, actor, opp.id,
               {"title": opp.title, "source": source, "directive_id": args.directive,
                "method": args.method})
    print(opp.id)


def cmd_opp_list(store, args):
    for opp in store.list_opportunities(status=args.status):
        print(f"{opp.id}  {opp.status:<28} {opp.title}")


def cmd_opp_show(store, args):
    opp = store.get_opportunity(args.id)
    if opp is None:
        raise SystemExit(f"no such opportunity: {args.id}")
    print(json.dumps(opp.to_doc(), indent=2))


def cmd_opp_history(store, args):
    for e in store.events_for(args.id):
        print(f"{e.timestamp}  {e.type:<32} actor={e.actor} {json.dumps(e.payload)}")


def cmd_know_add(store, args):
    record = KnowledgeRecord(type=args.type, source=args.source, content=args.content,
                             tags=args.tags.split(",") if args.tags else [],
                             venue_id=args.venue,
                             confidence=args.confidence)
    store.save_knowledge(record)
    store.emit(ev.KNOWLEDGE_ADDED, args.actor or _human(), record.id,
               {"type": record.type, "source": record.source})
    print(record.id)


def cmd_know_list(store, args):
    rows = store.conn.execute("SELECT id FROM knowledge ORDER BY id")
    for row in rows:
        record = store.get_knowledge(row["id"])
        stale = f" [SUPERSEDED by {record.superseded_by}]" if record.superseded_by else ""
        print(f"{record.id}  {record.type:<24} conf={record.confidence}{stale}  {record.content[:80]}")


def cmd_know_supersede(store, args):
    old = store.get_knowledge(args.old_id)
    new = store.get_knowledge(args.new_id)
    if old is None or new is None:
        raise SystemExit("both knowledge records must exist")
    old.superseded_by = new.id
    store.save_knowledge(old)
    store.emit(ev.KNOWLEDGE_SUPERSEDED, args.actor or _human(), old.id, {"by": new.id})
    print(f"{old.id} superseded by {new.id}")


def cmd_score_set(store, args):
    opp = store.get_opportunity(args.id)
    if opp is None:
        raise SystemExit(f"no such opportunity: {args.id}")
    score = Score(value=args.value, confidence=args.confidence,
                  estimate=args.estimate, rationale=args.rationale,
                  evidence=args.evidence.split(",") if args.evidence else [])
    opp.scores[args.dimension] = score
    store.save_opportunity(opp)
    store.emit(ev.SCORE_SET, args.actor or _human(), opp.id,
               {"dimension": args.dimension, "value": args.value,
                "confidence": args.confidence, "estimate": args.estimate,
                "evidence": score.evidence})
    print(f"{opp.id} {args.dimension} = {args.value} ({args.estimate}; confidence {args.confidence})")


def cmd_transition(store, args):
    opp = store.get_opportunity(args.id)
    if opp is None:
        raise SystemExit(f"no such opportunity: {args.id}")
    state_machine.transition(store, opp, args.state, actor=args.actor, reason=args.reason)
    print(f"{opp.id} -> {opp.status}")


def _human_transition(store, opp_id, state, reason):
    store_opp = store.get_opportunity(opp_id)
    if store_opp is None:
        raise SystemExit(f"no such opportunity: {opp_id}")
    state_machine.transition(store, store_opp, state, actor=_human(), reason=reason)
    print(f"{store_opp.id} -> {store_opp.status}")


def cmd_approve(store, args):
    _human_transition(store, args.id, "APPROVED", args.reason)


def cmd_reject(store, args):
    _human_transition(store, args.id, args.state, args.reason)


def cmd_hold(store, args):
    _human_transition(store, args.id, "ON_HOLD", args.reason)


def cmd_resume(store, args):
    opp = store.get_opportunity(args.id)
    if opp is None or opp.held_from is None:
        raise SystemExit(f"{args.id} is not on hold")
    _human_transition(store, args.id, opp.held_from, args.reason)


def cmd_reopen(store, args):
    _human_transition(store, args.id, "TRIAGED", args.reason)


def cmd_launch(store, args):
    opp = store.get_opportunity(args.id)
    if opp is None:
        raise SystemExit(f"no such opportunity: {args.id}")
    product = launch_product(store, opp, args.venue, actor=_human())
    print(product.id)


def cmd_budget_create(store, args):
    budget = budgets.create_budget(store, args.scope, args.amount, actor=_human())
    print(budget.id)


def cmd_budget_report(store, args):
    for budget_id in _budget_ids(store):
        budget = store.get_budget(budget_id)
        print(f"{budget.id} [{budget.scope}] allocated={budget.allocated:.2f} "
              f"consumed={budgets.consumed(store, budget_id):.2f} "
              f"remaining={budgets.remaining(store, budget_id):.2f}")


def cmd_runs(store, args):
    for run in store.list_runs(opportunity_id=args.opp):
        print(f"{run.id}  {run.worker_type:<20} opp={run.opportunity_id} "
              f"{run.status:<10} ${run.cost_usd:.2f}")


def build_parser():
    parser = argparse.ArgumentParser(prog="platform", description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status").set_defaults(func=cmd_status)

    venue = sub.add_parser("venue").add_subparsers(dest="sub", required=True)
    p = venue.add_parser("add")
    p.add_argument("--name", required=True)
    p.add_argument("--kind", default="")
    p.add_argument("--profile", help="JSON venue profile")
    p.set_defaults(func=cmd_venue_add)
    venue.add_parser("list").set_defaults(func=cmd_venue_list)

    directive = sub.add_parser("directive").add_subparsers(dest="sub", required=True)
    p = directive.add_parser("add")
    p.add_argument("--prompt", required=True)
    p.add_argument("--venues", help="comma-separated venue ids")
    p.add_argument("--budget", type=float, help="create a budget of this amount")
    p.add_argument("--cadence", default="one_shot")
    p.set_defaults(func=cmd_directive_add)
    directive.add_parser("list").set_defaults(func=cmd_directive_list)
    p = directive.add_parser("close")
    p.add_argument("id")
    p.add_argument("--reason", default="")
    p.add_argument("--actor")
    p.set_defaults(func=cmd_directive_close)

    p = sub.add_parser("seed")
    p.add_argument("--title", required=True)
    p.add_argument("--directive")
    p.add_argument("--signal-venues", dest="signal_venues")
    p.add_argument("--method", help="discovery method key (discovery-methods.md)")
    p.add_argument("--actor")
    p.set_defaults(func=cmd_seed)

    opp = sub.add_parser("opp").add_subparsers(dest="sub", required=True)
    p = opp.add_parser("list")
    p.add_argument("--status")
    p.set_defaults(func=cmd_opp_list)
    p = opp.add_parser("show")
    p.add_argument("id")
    p.set_defaults(func=cmd_opp_show)
    p = opp.add_parser("history")
    p.add_argument("id")
    p.set_defaults(func=cmd_opp_history)

    know = sub.add_parser("know").add_subparsers(dest="sub", required=True)
    p = know.add_parser("add")
    p.add_argument("--type", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--content", required=True)
    p.add_argument("--tags")
    p.add_argument("--venue")
    p.add_argument("--confidence", type=float)
    p.add_argument("--actor")
    p.set_defaults(func=cmd_know_add)
    know.add_parser("list").set_defaults(func=cmd_know_list)
    p = know.add_parser("supersede")
    p.add_argument("old_id")
    p.add_argument("new_id")
    p.add_argument("--actor")
    p.set_defaults(func=cmd_know_supersede)

    score = sub.add_parser("score").add_subparsers(dest="sub", required=True)
    p = score.add_parser("set")
    p.add_argument("id")
    p.add_argument("dimension")
    p.add_argument("value", type=float)
    p.add_argument("confidence", type=float)
    p.add_argument("--estimate", required=True,
                   help="grounded quantity in native units, e.g. '~5 session-days, <$100'")
    p.add_argument("--rationale", default="")
    p.add_argument("--evidence", help="comma-separated knowledge ids")
    p.add_argument("--actor")
    p.set_defaults(func=cmd_score_set)

    p = sub.add_parser("transition")
    p.add_argument("id")
    p.add_argument("state")
    p.add_argument("--actor", required=True)
    p.add_argument("--reason", default="")
    p.set_defaults(func=cmd_transition)

    for name, func, extra in [
        ("approve", cmd_approve, []),
        ("reject", cmd_reject, ["state"]),
        ("hold", cmd_hold, []),
        ("resume", cmd_resume, []),
        ("reopen", cmd_reopen, []),
    ]:
        p = sub.add_parser(name)
        p.add_argument("id")
        for arg in extra:
            p.add_argument(arg)
        p.add_argument("--reason", default="")
        p.set_defaults(func=func)

    p = sub.add_parser("launch")
    p.add_argument("id")
    p.add_argument("--venue", required=True)
    p.set_defaults(func=cmd_launch)

    budget = sub.add_parser("budget").add_subparsers(dest="sub", required=True)
    p = budget.add_parser("create")
    p.add_argument("scope")
    p.add_argument("amount", type=float)
    p.set_defaults(func=cmd_budget_create)
    budget.add_parser("report").set_defaults(func=cmd_budget_report)

    p = sub.add_parser("runs")
    p.add_argument("--opp")
    p.set_defaults(func=cmd_runs)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    store = _store(args)
    args.func(store, args)


if __name__ == "__main__":
    main()
