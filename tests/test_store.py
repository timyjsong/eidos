import sqlite3
import unittest

from core.schemas import (
    Budget,
    Directive,
    KnowledgeRecord,
    Opportunity,
    PermissionPolicy,
    Venue,
    WorkerRun,
)
from core.store import Store


class TestStore(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def test_opportunity_round_trip_and_upsert(self):
        opp = Opportunity(title="t")
        self.store.save_opportunity(opp)
        self.assertEqual(self.store.get_opportunity(opp.id).title, "t")
        opp.title = "t2"
        self.store.save_opportunity(opp)
        self.assertEqual(self.store.get_opportunity(opp.id).title, "t2")
        self.assertEqual(len(self.store.list_opportunities()), 1)

    def test_list_opportunities_by_status(self):
        self.store.save_opportunity(Opportunity(title="a"))
        self.store.save_opportunity(Opportunity(title="b", status="TRIAGED"))
        self.assertEqual(len(self.store.list_opportunities(status="TRIAGED")), 1)

    def test_other_registries_round_trip(self):
        know = KnowledgeRecord(type="t", source="s", content="c")
        self.store.save_knowledge(know)
        self.assertEqual(self.store.get_knowledge(know.id).content, "c")

        budget = Budget(scope="research", allocated=5)
        self.store.save_budget(budget)
        self.assertEqual(self.store.get_budget(budget.id).allocated, 5)

        policy = PermissionPolicy(worker_type="w", tier=2, allowed_actions=["a"])
        self.store.save_policy(policy)
        self.assertEqual(self.store.get_policy("w").tier, 2)

        run = WorkerRun(worker_type="w", opportunity_id="opp_x")
        self.store.save_run(run)
        self.assertEqual(self.store.get_run(run.id).opportunity_id, "opp_x")
        self.assertEqual(len(self.store.list_runs(opportunity_id="opp_x")), 1)

        venue = Venue(name="Shopify App Store", kind="marketplace")
        self.store.save_venue(venue)
        self.assertEqual(self.store.get_venue(venue.id).name, "Shopify App Store")
        self.assertEqual(len(self.store.list_venues()), 1)

        directive = Directive(prompt="explore X", venues=[venue.id])
        self.store.save_directive(directive)
        self.assertEqual(self.store.get_directive(directive.id).venues, [venue.id])
        self.assertEqual(len(self.store.list_directives()), 1)

    def test_events_ordered_and_filtered(self):
        self.store.emit("A", "actor", "target_1", {"n": 1})
        self.store.emit("B", "actor", "target_1", {"n": 2})
        self.store.emit("A", "actor", "target_2", {"n": 3})
        events = self.store.events_for("target_1")
        self.assertEqual([e.payload["n"] for e in events], [1, 2])
        self.assertEqual(len(self.store.events_of_type("A")), 2)
        self.assertEqual(len(self.store.events_of_type("A", "target_2")), 1)
        self.assertEqual(len(self.store.all_events()), 3)

    def test_events_append_only(self):
        event = self.store.emit("A", "actor", "target", {})
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.conn.execute("UPDATE events SET actor='tampered' WHERE id=?", (event.id,))
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.conn.execute("DELETE FROM events WHERE id=?", (event.id,))

    def test_no_delete_api(self):
        deleters = [m for m in dir(self.store) if "delete" in m.lower() or "remove" in m.lower()]
        self.assertEqual(deleters, [])


if __name__ == "__main__":
    unittest.main()
