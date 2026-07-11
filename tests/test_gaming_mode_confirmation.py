from __future__ import annotations

import unittest

from skills.gaming_mode_confirmation import GamingModeConfirmationStore


class GamingModeConfirmationStoreTests(unittest.TestCase):
    def test_confirm_without_pending_request_returns_none(self):
        store = GamingModeConfirmationStore(clock=lambda: 100.0)

        decision = store.confirm()

        self.assertEqual(decision.status, "none")
        self.assertIsNone(decision.request)

    def test_confirm_pending_request(self):
        now = 100.0
        store = GamingModeConfirmationStore(clock=lambda: now)

        request = store.begin()
        decision = store.confirm()

        self.assertEqual(decision.status, "confirmed")
        self.assertEqual(decision.request, request)

    def test_confirm_expired_request(self):
        now = 100.0

        def clock() -> float:
            return now

        store = GamingModeConfirmationStore(
            clock=clock,
            timeout_seconds=10.0,
        )
        request = store.begin()

        now = 111.0
        decision = store.confirm()

        self.assertEqual(decision.status, "expired")
        self.assertEqual(decision.request, request)

    def test_cancel_pending_request(self):
        store = GamingModeConfirmationStore(clock=lambda: 100.0)

        request = store.begin()

        self.assertEqual(store.cancel(), request)
        self.assertIsNone(store.cancel())


if __name__ == "__main__":
    unittest.main()