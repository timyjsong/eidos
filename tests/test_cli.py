import os
import tempfile
import unittest

from core import cli
from core.store import Store


class TestCli(unittest.TestCase):
    """Smoke tests: the CLI is the operator's only write path — it must actually work."""

    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(self.db)  # let the Store create it fresh

    def tearDown(self):
        if os.path.exists(self.db):
            os.remove(self.db)

    def _run(self, *argv):
        cli.main(["--db", self.db, *argv])

    def test_seed_and_human_flow(self):
        self._run("venue", "add", "--name", "Shopify App Store", "--kind", "marketplace")
        store = Store(self.db)
        venue = store.list_venues()[0]

        self._run("directive", "add", "--prompt", "explore gaps", "--venues", venue.id,
                  "--budget", "5")
        self._run("seed", "--title", "review autoresponder")
        store = Store(self.db)
        opp = store.list_opportunities()[0]
        self.assertEqual(opp.status, "DISCOVERED")

        self._run("know", "add", "--type", "competitor_observation", "--source", "search",
                  "--content", "3 weak competitors", "--venue", venue.id)
        store = Store(self.db)
        know_id = [k for k in [r["id"] for r in
                   store.conn.execute("SELECT id FROM knowledge")]][0]

        self._run("transition", opp.id, "TRIAGED", "--actor", "triage_agent")
        self._run("score", "set", opp.id, "pain", "7.5", "0.8",
                  "--estimate", "weekly blocker", "--evidence", know_id)
        self._run("opp", "scores", opp.id)  # scorecard renders without error
        self._run("transition", opp.id, "EVALUATED", "--actor", "evaluator")
        self._run("approve", opp.id, "--reason", "strong scores")

        store = Store(self.db)
        opp = store.get_opportunity(opp.id)
        self.assertEqual(opp.status, "APPROVED")
        self.assertEqual(opp.scores["pain"].evidence, [know_id])
        history = store.events_for(opp.id)
        self.assertGreaterEqual(len(history), 4)  # created, 2 transitions, score, approve

    def test_hold_resume_round_trip(self):
        self._run("seed", "--title", "x")
        store = Store(self.db)
        opp_id = store.list_opportunities()[0].id
        self._run("hold", opp_id)
        store = Store(self.db)
        self.assertEqual(store.get_opportunity(opp_id).status, "ON_HOLD")
        self._run("resume", opp_id)
        store = Store(self.db)
        self.assertEqual(store.get_opportunity(opp_id).status, "DISCOVERED")

    def test_validate_records_check(self):
        self._run("seed", "--title", "x")
        store = Store(self.db)
        opp_id = store.list_opportunities()[0].id
        self._run("validate", opp_id, "problem", "pass", "--notes", "threads confirm volume")
        store = Store(self.db)
        opp = store.get_opportunity(opp_id)
        self.assertEqual(opp.validation["problem"]["verdict"], "pass")
        self.assertIsNone(opp.validation["market"])
        self.assertEqual(len(store.events_of_type("VALIDATION_RESULT", opp_id)), 1)

    def test_venue_update_merges_profile(self):
        self._run("venue", "add", "--name", "V", "--profile", '{"distribution": {"a": 1}}')
        store = Store(self.db)
        venue_id = store.list_venues()[0].id
        self._run("venue", "update", venue_id, "--profile", '{"change_feeds": ["url1"]}')
        store = Store(self.db)
        profile = store.get_venue(venue_id).profile
        self.assertEqual(profile["change_feeds"], ["url1"])
        self.assertEqual(profile["distribution"], {"a": 1})  # existing keys survive

    def test_recommend_records_event(self):
        self._run("seed", "--title", "x")
        store = Store(self.db)
        opp_id = store.list_opportunities()[0].id
        self._run("recommend", opp_id, "approve", "--reason", "strong wedge")
        store = Store(self.db)
        recs = store.events_of_type("GATE_RECOMMENDATION", opp_id)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].payload["recommendation"], "approve")

    def test_know_supersede(self):
        self._run("know", "add", "--type", "pricing", "--source", "old", "--content", "stale fact")
        self._run("know", "add", "--type", "pricing", "--source", "new", "--content", "fresh fact")
        store = Store(self.db)
        by_source = {store.get_knowledge(r["id"]).source: r["id"]
                     for r in store.conn.execute("SELECT id FROM knowledge")}
        old_id, new_id = by_source["old"], by_source["new"]
        self._run("know", "supersede", old_id, new_id)
        store = Store(self.db)
        self.assertEqual(store.get_knowledge(old_id).superseded_by, new_id)
        self.assertEqual(len(store.events_of_type("KNOWLEDGE_SUPERSEDED", old_id)), 1)

    def test_launch_creates_product(self):
        self._run("venue", "add", "--name", "v")
        self._run("seed", "--title", "launchable")
        store = Store(self.db)
        venue = store.list_venues()[0]
        opp = store.list_opportunities()[0]
        opp.status = "READY"
        store.save_opportunity(opp)

        self._run("launch", opp.id, "--venue", venue.id)
        store = Store(self.db)
        self.assertEqual(store.get_opportunity(opp.id).status, "LAUNCHED")
        products = store.conn.execute("SELECT doc FROM products").fetchall()
        self.assertEqual(len(products), 1)


if __name__ == "__main__":
    unittest.main()
