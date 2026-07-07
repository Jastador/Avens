from __future__ import annotations

import unittest

from skills.local_reminders import (
    LocalReminder,
    REMINDER_KIND_REMINDER,
    REMINDER_STATUS_PENDING,
)
from skills.reminder_cancel_confirmation import (
    ReminderCancelConfirmationStore,
)


class ReminderCancelConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.store = ReminderCancelConfirmationStore(
            clock=lambda: self.now,
            timeout_seconds=15.0,
        )
        self.reminder = LocalReminder(
            reminder_id=2,
            text="Drink water",
            kind=REMINDER_KIND_REMINDER,
            due_at_utc="2026-07-07T09:00:00Z",
            created_at_utc="2026-07-07T08:30:00Z",
            status=REMINDER_STATUS_PENDING,
        )

    def test_exact_confirmation_returns_the_pending_reminder(self):
        self.store.begin(self.reminder)

        decision = self.store.confirm(2)

        self.assertEqual(decision.status, "confirmed")
        self.assertIsNotNone(decision.request)
        self.assertEqual(decision.request.reminder_id, 2)

    def test_mismatched_confirmation_cancels_the_request(self):
        self.store.begin(self.reminder)

        decision = self.store.confirm(1)

        self.assertEqual(decision.status, "mismatch")
        self.assertEqual(
            self.store.confirm(2).status,
            "none",
        )

    def test_expired_confirmation_is_rejected(self):
        self.store.begin(self.reminder)
        self.now += 15.0

        decision = self.store.confirm(2)

        self.assertEqual(decision.status, "expired")

    def test_cancel_returns_and_clears_the_pending_request(self):
        self.store.begin(self.reminder)

        cancelled = self.store.cancel()

        self.assertIsNotNone(cancelled)
        self.assertEqual(cancelled.reminder_id, 2)
        self.assertEqual(
            self.store.confirm(2).status,
            "none",
        )

    def test_confirm_without_a_pending_request_is_safe(self):
        decision = self.store.confirm(2)

        self.assertEqual(decision.status, "none")
        self.assertIsNone(decision.request)