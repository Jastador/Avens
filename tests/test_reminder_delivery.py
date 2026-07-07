from __future__ import annotations

import unittest

from skills.local_reminders import (
    LocalReminder,
    REMINDER_KIND_REMINDER,
    REMINDER_KIND_TIMER,
    REMINDER_STATUS_DELIVERED,
    REMINDER_STATUS_PENDING,
)
from skills.reminder_delivery import (
    deliver_due_reminders,
)


def make_reminder(
    reminder_id: int,
    text: str,
    *,
    kind: str,
    status: str,
) -> LocalReminder:
    """Build one stable reminder for delivery tests."""
    delivered_at_utc = None

    if status == REMINDER_STATUS_DELIVERED:
        delivered_at_utc = "2026-07-07T09:00:00Z"

    return LocalReminder(
        reminder_id=reminder_id,
        text=text,
        kind=kind,
        due_at_utc="2026-07-07T09:00:00Z",
        created_at_utc="2026-07-07T08:30:00Z",
        status=status,
        delivered_at_utc=delivered_at_utc,
    )


class ReminderDeliveryTests(unittest.TestCase):
    def test_delivery_plays_and_announces_due_reminders_in_order(self):
        timer = make_reminder(
            1,
            "Timer",
            kind=REMINDER_KIND_TIMER,
            status=REMINDER_STATUS_DELIVERED,
        )
        reminder = make_reminder(
            2,
            "Drink water",
            kind=REMINDER_KIND_REMINDER,
            status=REMINDER_STATUS_DELIVERED,
        )
        alerts = []
        announcements = []

        delivered = deliver_due_reminders(
            (timer, reminder),
            play_alert=lambda: alerts.append("alert"),
            announce=announcements.append,
        )

        self.assertEqual(
            alerts,
            ["alert", "alert"],
        )
        self.assertEqual(
            announcements,
            [
                "Timer 1 is complete, sir.",
                "Reminder 2: Drink water, sir.",
            ],
        )
        self.assertEqual(
            delivered,
            tuple(announcements),
        )

    def test_pending_reminder_is_not_announced(self):
        pending = make_reminder(
            1,
            "Drink water",
            kind=REMINDER_KIND_REMINDER,
            status=REMINDER_STATUS_PENDING,
        )
        alerts = []
        announcements = []
        output = []

        delivered = deliver_due_reminders(
            (pending,),
            play_alert=lambda: alerts.append("alert"),
            announce=announcements.append,
            error_output=output.append,
        )

        self.assertEqual(delivered, ())
        self.assertEqual(alerts, [])
        self.assertEqual(announcements, [])
        self.assertEqual(
            output,
            [
                "Local reminder delivery error: "
                "Only a delivered reminder can be announced."
            ],
        )

    def test_failed_announcement_does_not_block_later_reminders(self):
        timer = make_reminder(
            1,
            "Timer",
            kind=REMINDER_KIND_TIMER,
            status=REMINDER_STATUS_DELIVERED,
        )
        reminder = make_reminder(
            2,
            "Drink water",
            kind=REMINDER_KIND_REMINDER,
            status=REMINDER_STATUS_DELIVERED,
        )
        announcements = []
        output = []

        def announce(message: str) -> None:
            if message.startswith("Timer"):
                raise RuntimeError("TTS test failure")

            announcements.append(message)

        delivered = deliver_due_reminders(
            (timer, reminder),
            play_alert=lambda: None,
            announce=announce,
            error_output=output.append,
        )

        self.assertEqual(
            delivered,
            ("Reminder 2: Drink water, sir.",),
        )
        self.assertEqual(
            announcements,
            ["Reminder 2: Drink water, sir."],
        )
        self.assertIn(
            "Local reminder announcement error: "
            "TTS test failure",
            output,
        )