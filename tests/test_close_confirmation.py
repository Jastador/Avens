from __future__ import annotations

import unittest

from skills.close_confirmation import CloseConfirmationStore


class CloseConfirmationStoreTests(unittest.TestCase):
    def test_confirms_one_exact_request_once(self):
        now = [100.0]
        store = CloseConfirmationStore(
            clock=lambda: now[0],
            timeout_seconds=15.0,
        )

        store.begin(
            "Chrome",
            "Google Chrome",
            close_all=False,
        )

        decision = store.confirm(
            "Chrome",
            close_all=False,
        )

        self.assertEqual(decision.status, "confirmed")
        self.assertIsNotNone(decision.request)
        self.assertEqual(
            decision.request.display_name,
            "Google Chrome",
        )

        second_decision = store.confirm(
            "Chrome",
            close_all=False,
        )

        self.assertEqual(second_decision.status, "none")

    def test_rejects_mismatched_confirmation_and_clears_request(self):
        store = CloseConfirmationStore(
            clock=lambda: 100.0,
        )

        store.begin(
            "Chrome",
            "Google Chrome",
            close_all=False,
        )

        decision = store.confirm(
            "Notepad",
            close_all=False,
        )

        self.assertEqual(decision.status, "mismatch")

        second_decision = store.confirm(
            "Chrome",
            close_all=False,
        )

        self.assertEqual(second_decision.status, "none")

    def test_rejects_expired_confirmation_and_clears_request(self):
        now = [100.0]
        store = CloseConfirmationStore(
            clock=lambda: now[0],
            timeout_seconds=15.0,
        )

        store.begin(
            "Chrome",
            "Google Chrome",
            close_all=True,
        )
        now[0] = 115.0

        decision = store.confirm(
            "Chrome",
            close_all=True,
        )

        self.assertEqual(decision.status, "expired")
        self.assertIsNotNone(decision.request)
        self.assertTrue(decision.request.close_all)

        second_decision = store.confirm(
            "Chrome",
            close_all=True,
        )

        self.assertEqual(second_decision.status, "none")

    def test_cancel_forgets_request_without_confirmation(self):
        store = CloseConfirmationStore(
            clock=lambda: 100.0,
        )

        request = store.begin(
            "Chrome",
            "Google Chrome",
            close_all=False,
        )
        cancelled = store.cancel()

        self.assertEqual(cancelled, request)

        decision = store.confirm(
            "Chrome",
            close_all=False,
        )

        self.assertEqual(decision.status, "none")