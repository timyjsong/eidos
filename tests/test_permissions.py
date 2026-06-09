import unittest

from core import permissions
from core.store import Store


class TestPermissions(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        permissions.register_policy(self.store, "researcher", 1, ["search", "summarize"])

    def test_allowed(self):
        self.assertTrue(permissions.check(self.store, "researcher", "search", 1))
        self.assertTrue(permissions.check(self.store, "researcher", "search", 0))

    def test_tier_too_low(self):
        with self.assertRaises(permissions.PermissionDenied):
            permissions.check(self.store, "researcher", "search", 6)

    def test_action_not_allowed(self):
        with self.assertRaises(permissions.PermissionDenied):
            permissions.check(self.store, "researcher", "purchase_domain", 1)

    def test_unknown_worker_type(self):
        with self.assertRaises(permissions.PermissionDenied):
            permissions.check(self.store, "ghost", "search", 0)

    def test_denial_emits_event(self):
        with self.assertRaises(permissions.PermissionDenied):
            permissions.check(self.store, "researcher", "purchase_domain", 5)
        denials = self.store.events_of_type("PERMISSION_DENIED", "researcher")
        self.assertEqual(len(denials), 1)
        self.assertEqual(denials[0].payload["action"], "purchase_domain")


if __name__ == "__main__":
    unittest.main()
