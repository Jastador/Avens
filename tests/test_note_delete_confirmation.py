from __future__ import annotations

import unittest

from skills.local_notes import LocalNote
from skills.note_delete_confirmation import (
    NoteDeleteConfirmationStore,
)


class NoteDeleteConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.store = NoteDeleteConfirmationStore(
            clock=lambda: self.now,
            timeout_seconds=15.0,
        )
        self.note = LocalNote(
            note_id=2,
            text="Finish Avens tests",
            created_at_utc="2026-07-07T12:21:21Z",
        )

    def test_exact_confirmation_returns_the_pending_note(self):
        self.store.begin(self.note)

        decision = self.store.confirm(2)

        self.assertEqual(decision.status, "confirmed")
        self.assertIsNotNone(decision.request)
        self.assertEqual(decision.request.note_id, 2)

    def test_mismatched_confirmation_cancels_the_pending_request(self):
        self.store.begin(self.note)

        decision = self.store.confirm(1)

        self.assertEqual(decision.status, "mismatch")
        self.assertEqual(
            self.store.confirm(2).status,
            "none",
        )

    def test_expired_confirmation_is_rejected(self):
        self.store.begin(self.note)
        self.now += 15.0

        decision = self.store.confirm(2)

        self.assertEqual(decision.status, "expired")

    def test_cancel_returns_and_clears_the_pending_request(self):
        self.store.begin(self.note)

        cancelled = self.store.cancel()

        self.assertIsNotNone(cancelled)
        self.assertEqual(cancelled.note_id, 2)
        self.assertEqual(
            self.store.confirm(2).status,
            "none",
        )

    def test_confirm_without_a_pending_request_is_safe(self):
        decision = self.store.confirm(2)

        self.assertEqual(decision.status, "none")
        self.assertIsNone(decision.request)