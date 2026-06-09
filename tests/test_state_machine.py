import unittest

from core import state_machine as sm
from core.schemas import Opportunity
from core.store import Store


class TestStateMachine(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def _opp(self, status="DISCOVERED", **kwargs):
        opp = Opportunity(title="t", status=status, **kwargs)
        self.store.save_opportunity(opp)
        return opp

    def test_forward_chain_allowed(self):
        for current, nxt in zip(sm.LIFECYCLE, sm.LIFECYCLE[1:]):
            self.assertIn(nxt, sm.TRANSITIONS[current], f"{current} -> {nxt}")

    def test_skipping_ahead_blocked(self):
        opp = self._opp()
        with self.assertRaises(sm.InvalidTransition):
            sm.transition(self.store, opp, "LAUNCHED", actor="test")
        blocked = self.store.events_of_type("OPPORTUNITY_TRANSITION_BLOCKED", opp.id)
        self.assertEqual(len(blocked), 1)
        self.assertEqual(self.store.get_opportunity(opp.id).status, "DISCOVERED")

    def test_rejection_window(self):
        self.assertNotIn("REJECTED_LOW_ROI", sm.TRANSITIONS["DISCOVERED"])
        for state in ("TRIAGED", "EVALUATED", "APPROVED", "VALIDATED"):
            self.assertIn("REJECTED_LOW_ROI", sm.TRANSITIONS[state], state)
        self.assertNotIn("REJECTED_LOW_ROI", sm.TRANSITIONS["BUILDING"])

    def test_archive_from_any_active(self):
        for state in sm.LIFECYCLE:
            self.assertIn("ARCHIVED", sm.TRANSITIONS[state], state)

    def test_launched_is_end_of_story(self):
        self.assertEqual(sm.TRANSITIONS["LAUNCHED"], {"ARCHIVED"})

    def test_archived_frozen(self):
        self.assertEqual(sm.TRANSITIONS["ARCHIVED"], set())
        opp = self._opp(status="ARCHIVED")
        with self.assertRaises(sm.InvalidTransition):
            sm.transition(self.store, opp, "TRIAGED", actor="human:tim")

    def test_hold_and_resume(self):
        opp = self._opp(status="EVALUATED")
        sm.transition(self.store, opp, "ON_HOLD", actor="portfolio_manager")
        self.assertEqual(opp.held_from, "EVALUATED")
        # may only return to where it was held from (or be archived)
        with self.assertRaises(sm.InvalidTransition):
            sm.transition(self.store, opp, "BUILDING", actor="portfolio_manager")
        sm.transition(self.store, opp, "EVALUATED", actor="portfolio_manager")
        self.assertIsNone(opp.held_from)
        self.assertEqual(self.store.get_opportunity(opp.id).status, "EVALUATED")

    def test_hold_then_archive(self):
        opp = self._opp(status="TRIAGED")
        sm.transition(self.store, opp, "ON_HOLD", actor="portfolio_manager")
        sm.transition(self.store, opp, "ARCHIVED", actor="portfolio_manager")
        self.assertEqual(opp.status, "ARCHIVED")

    def test_reopen_guard(self):
        opp = self._opp(status="REJECTED_SATURATED")
        with self.assertRaises(sm.InvalidTransition):
            sm.transition(self.store, opp, "TRIAGED", actor="overeager_worker")
        self.assertEqual(self.store.get_opportunity(opp.id).status, "REJECTED_SATURATED")
        sm.transition(self.store, opp, "TRIAGED", actor="human:tim", reason="market shifted")
        self.assertEqual(self.store.get_opportunity(opp.id).status, "TRIAGED")

    def test_reopen_by_portfolio_manager(self):
        opp = self._opp(status="REJECTED_LOW_ROI")
        sm.transition(self.store, opp, "TRIAGED", actor="portfolio_manager")
        self.assertEqual(opp.status, "TRIAGED")

    def test_transition_persists_and_emits(self):
        opp = self._opp()
        sm.transition(self.store, opp, "TRIAGED", actor="test", reason="r")
        self.assertEqual(self.store.get_opportunity(opp.id).status, "TRIAGED")
        changes = self.store.events_of_type("OPPORTUNITY_STATE_CHANGED", opp.id)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].payload, {"from": "DISCOVERED", "to": "TRIAGED", "reason": "r"})


if __name__ == "__main__":
    unittest.main()
