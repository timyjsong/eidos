import unittest

from core import state_machine as sm
from core.schemas import Opportunity
from core.store import Store


class TestStateMachine(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def _opp(self, status="DISCOVERED"):
        opp = Opportunity(title="t", status=status)
        self.store.save_opportunity(opp)
        return opp

    def test_forward_chain_allowed(self):
        for current, nxt in zip(sm.LIFECYCLE, sm.LIFECYCLE[1:]):
            self.assertTrue(sm.can_transition(current, nxt), f"{current} -> {nxt}")

    def test_skipping_ahead_blocked(self):
        opp = self._opp()
        with self.assertRaises(sm.InvalidTransition):
            sm.transition(self.store, opp, "LAUNCHED", actor="test")
        blocked = self.store.events_of_type("OPPORTUNITY_TRANSITION_BLOCKED", opp.id)
        self.assertEqual(len(blocked), 1)
        self.assertEqual(self.store.get_opportunity(opp.id).status, "DISCOVERED")

    def test_rejection_window(self):
        self.assertFalse(sm.can_transition("DISCOVERED", "REJECTED_LOW_ROI"))
        self.assertFalse(sm.can_transition("CLASSIFIED", "REJECTED_LOW_ROI"))
        for state in ("VETTED", "EVALUATED", "DISTRIBUTION_VALIDATED"):
            self.assertTrue(sm.can_transition(state, "REJECTED_LOW_ROI"), state)
        self.assertFalse(sm.can_transition("SCOPED", "REJECTED_LOW_ROI"))

    def test_archive_from_any_active(self):
        for state in sm.LIFECYCLE:
            self.assertTrue(sm.can_transition(state, "ARCHIVED"), state)

    def test_terminal_states_frozen(self):
        for terminal in sm.OPPORTUNITY_TERMINAL:
            self.assertEqual(sm.TRANSITIONS[terminal], set())
        opp = self._opp(status="ARCHIVED")
        with self.assertRaises(sm.InvalidTransition):
            sm.transition(self.store, opp, "DISCOVERED", actor="test")

    def test_transition_persists_and_emits(self):
        opp = self._opp()
        sm.transition(self.store, opp, "CLASSIFIED", actor="test", reason="r")
        self.assertEqual(self.store.get_opportunity(opp.id).status, "CLASSIFIED")
        changes = self.store.events_of_type("OPPORTUNITY_STATE_CHANGED", opp.id)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].payload, {"from": "DISCOVERED", "to": "CLASSIFIED", "reason": "r"})


if __name__ == "__main__":
    unittest.main()
