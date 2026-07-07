from __future__ import annotations

from datetime import datetime, timezone
from threading import Event
import unittest

from skills.local_reminders import (
    LocalReminder,
    LocalRemindersError,
    REMINDER_KIND_REMINDER,
    REMINDER_STATUS_PENDING,
)
from skills.reminder_scheduler import ReminderScheduler


def make_reminder(
    reminder_id: int,
    text: str,
) -> LocalReminder:
    """Build one stable reminder for scheduler tests."""
    return LocalReminder(
        reminder_id=reminder_id,
        text=text,
        kind=REMINDER_KIND_REMINDER,
        due_at_utc="2026-07-07T09:00:00Z",
        created_at_utc="2026-07-07T08:30:00Z",
        status=REMINDER_STATUS_PENDING,
    )


class ReminderSchedulerTests(unittest.TestCase):
    def test_poll_once_queues_claimed_reminders_in_order(self):
        first = make_reminder(1, "Drink water")
        second = make_reminder(2, "Call Dad")
        claim_calls = []

        def claim_due():
            claim_calls.append(True)
            return (first, second)

        scheduler = ReminderScheduler(
            claim_due=claim_due,
        )

        claimed = scheduler.poll_once()
        deliveries = scheduler.drain_deliveries()

        self.assertEqual(claim_calls, [True])
        self.assertEqual(claimed, (first, second))
        self.assertEqual(deliveries, (first, second))
        self.assertEqual(
            scheduler.drain_deliveries(),
            (),
        )

    def test_delivery_signal_tracks_enqueued_and_drained_reminders(self):
        reminder = make_reminder(1, "Drink water")

        scheduler = ReminderScheduler(
            claim_due=lambda: (reminder,),
        )

        self.assertFalse(
            scheduler.has_queued_deliveries()
        )

        scheduler.poll_once()

        self.assertTrue(
            scheduler.has_queued_deliveries()
        )
        self.assertEqual(
            scheduler.drain_deliveries(),
            (reminder,),
        )
        self.assertFalse(
            scheduler.has_queued_deliveries()
        )

    def test_poll_once_handles_local_storage_errors(self):
        output = []

        def claim_due():
            raise LocalRemindersError("storage test failure")

        scheduler = ReminderScheduler(
            claim_due=claim_due,
            error_output=output.append,
        )

        claimed = scheduler.poll_once()

        self.assertEqual(claimed, ())
        self.assertEqual(
            scheduler.drain_deliveries(),
            (),
        )
        self.assertEqual(
            output,
            [
                "Local reminder scheduler error: "
                "storage test failure"
            ],
        )

    def test_poll_once_rejects_invalid_claim_data(self):
        output = []

        scheduler = ReminderScheduler(
            claim_due=lambda: ("not a reminder",),
            error_output=output.append,
        )

        claimed = scheduler.poll_once()

        self.assertEqual(claimed, ())
        self.assertEqual(
            scheduler.drain_deliveries(),
            (),
        )
        self.assertEqual(
            output,
            [
                "Reminder scheduler returned invalid "
                "reminder data."
            ],
        )

    def test_background_worker_polls_then_stops_cleanly(self):
        reminder = make_reminder(1, "Drink water")
        poll_started = Event()
        calls = []

        def claim_due():
            calls.append(True)
            poll_started.set()

            if len(calls) == 1:
                return (reminder,)

            return ()

        scheduler = ReminderScheduler(
            claim_due=claim_due,
            poll_interval_seconds=60.0,
        )

        self.assertTrue(scheduler.start())
        self.assertTrue(poll_started.wait(timeout=1.0))
        self.assertTrue(scheduler.is_running())
        self.assertFalse(scheduler.start())

        self.assertTrue(
            scheduler.stop(timeout_seconds=1.0)
        )
        self.assertFalse(scheduler.is_running())
        self.assertEqual(
            scheduler.drain_deliveries(),
            (reminder,),
        )

    def test_stop_without_a_running_worker_is_safe(self):
        scheduler = ReminderScheduler()

        self.assertFalse(
            scheduler.stop(timeout_seconds=0.0)
        )

    def test_invalid_scheduler_timing_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "positive number",
        ):
            ReminderScheduler(
                poll_interval_seconds=0
            )

        scheduler = ReminderScheduler()

        with self.assertRaisesRegex(
            ValueError,
            "non-negative",
        ):
            scheduler.stop(timeout_seconds=-1)