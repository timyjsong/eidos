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

    def test_gate_targets_derived_from_tables(self):
        self.assertEqual(sm.GATE_TARGETS, {"APPROVED", "LAUNCHED"} | set(sm.REJECTED))

    def test_worker_blocked_at_approve_gate(self):
        opp = self._opp(status="EVALUATED")
        with self.assertRaises(sm.InvalidTransition):
            sm.transition(self.store, opp, "APPROVED", actor="worker:rogue")
        self.assertEqual(self.store.get_opportunity(opp.id).status, "EVALUATED")
        blocked = self.store.events_of_type("OPPORTUNITY_TRANSITION_BLOCKED", opp.id)
        self.assertEqual(len(blocked), 1)  # failed attempts are evidence too
        self.assertEqual(blocked[0].payload["to"], "APPROVED")

    def test_worker_blocked_at_reject_and_launch_gates(self):
        opp = self._opp(status="EVALUATED")
        with self.assertRaises(sm.InvalidTransition):
            sm.transition(self.store, opp, "REJECTED_LOW_ROI", actor="evaluator")
        self.assertEqual(self.store.get_opportunity(opp.id).status, "EVALUATED")
        ready = self._opp(status="READY")
        with self.assertRaises(sm.InvalidTransition):
            sm.transition(self.store, ready, "LAUNCHED", actor="launch_worker")
        self.assertEqual(self.store.get_opportunity(ready.id).status, "READY")

    def test_human_and_operator_actors_pass_gates(self):
        opp = self._opp(status="EVALUATED")
        sm.transition(self.store, opp, "APPROVED", actor="operator:autonomous-gate")
        self.assertEqual(self.store.get_opportunity(opp.id).status, "APPROVED")
        other = self._opp(status="EVALUATED")
        sm.transition(self.store, other, "REJECTED_LOW_ROI", actor="human:tim")
        self.assertEqual(self.store.get_opportunity(other.id).status, "REJECTED_LOW_ROI")

    def test_non_gate_transitions_stay_open_to_workers(self):
        opp = self._opp()
        sm.transition(self.store, opp, "TRIAGED", actor="worker:triage")  # forward
        sm.transition(self.store, opp, "ON_HOLD", actor="worker:triage")  # hold
        sm.transition(self.store, opp, "TRIAGED", actor="worker:triage")  # resume
        sm.transition(self.store, opp, "ARCHIVED", actor="worker:triage")  # archive
        self.assertEqual(self.store.get_opportunity(opp.id).status, "ARCHIVED")

    def test_transition_persists_and_emits(self):
        opp = self._opp()
        sm.transition(self.store, opp, "TRIAGED", actor="test", reason="r")
        self.assertEqual(self.store.get_opportunity(opp.id).status, "TRIAGED")
        changes = self.store.events_of_type("OPPORTUNITY_STATE_CHANGED", opp.id)
        self.assertEqual(len(changes), 1)
        payload = changes[0].payload
        self.assertEqual((payload["from"], payload["to"], payload["reason"]),
                         ("DISCOVERED", "TRIAGED", "r"))
        self.assertIn("system_version", payload)  # decisions inherit system maturity


if __name__ == "__main__":
    unittest.main()
