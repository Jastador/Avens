from __future__ import annotations

from datetime import datetime, timezone
import unittest

from skills.local_reminders import (
    LocalReminder,
    LocalRemindersError,
    REMINDER_KIND_REMINDER,
    REMINDER_KIND_TIMER,
    REMINDER_STATUS_PENDING,
)
from skills.reminder_cancel_confirmation import (
    ReminderCancelConfirmationStore,
)
from skills.reminder_schedule import (
    ReminderSchedule,
    ReminderScheduleError,
)
from skills.router import route_local_skill


def make_reminder(
    reminder_id: int,
    text: str,
    *,
    kind: str = REMINDER_KIND_REMINDER,
    due_at_utc: str = "2026-07-07T09:00:00Z",
) -> LocalReminder:
    """Build one stable reminder for router tests."""
    return LocalReminder(
        reminder_id=reminder_id,
        text=text,
        kind=kind,
        due_at_utc=due_at_utc,
        created_at_utc="2026-07-07T08:30:00Z",
        status=REMINDER_STATUS_PENDING,
    )


class LocalRemindersRouterTests(unittest.TestCase):
    def setUp(self):
        self.relative_schedule = ReminderSchedule(
            due_at_utc=datetime(
                2026,
                7,
                7,
                9,
                0,
                tzinfo=timezone.utc,
            ),
            description="in 30 minutes",
        )

        self.tomorrow_schedule = ReminderSchedule(
            due_at_utc=datetime(
                2026,
                7,
                7,
                14,
                30,
                tzinfo=timezone.utc,
            ),
            description="tomorrow at 8:00 PM",
        )

    def test_timer_saves_a_fixed_timer_record(self):
        saved = []
        schedule_calls = []
        output = []

        def save_local_reminder(text, *, kind, due_at):
            saved.append((text, kind, due_at))
            return make_reminder(
                1,
                text,
                kind=kind,
                due_at_utc="2026-07-07T09:00:00Z",
            )

        def schedule_after(**kwargs):
            schedule_calls.append(kwargs)
            return ReminderSchedule(
                due_at_utc=self.relative_schedule.due_at_utc,
                description="in 5 minutes",
            )

        result = route_local_skill(
            "Start a timer for 5 minutes",
            parse_reminder_duration=lambda value: (0, 5, 0),
            schedule_reminder_after=schedule_after,
            save_local_reminder=save_local_reminder,
            console_output=output.append,
        )

        self.assertEqual(
            saved,
            [
                (
                    "Timer",
                    REMINDER_KIND_TIMER,
                    self.relative_schedule.due_at_utc,
                )
            ],
        )
        self.assertEqual(
            schedule_calls,
            [
                {
                    "hours": 0,
                    "minutes": 5,
                    "seconds": 0,
                }
            ],
        )
        self.assertEqual(
            result.skill_name,
            "create_local_timer",
        )
        self.assertEqual(
            result.message,
            "Set local timer 1 for 5 minutes, sir.",
        )
        self.assertIn(
            "Saved local timer 1: Timer",
            "\n".join(output),
        )

    def test_relative_reminder_preserves_exact_task_text(self):
        saved = []
        parsed_durations = []

        def save_local_reminder(text, *, kind, due_at):
            saved.append((text, kind, due_at))
            return make_reminder(
                2,
                text,
                kind=kind,
            )

        def parse_duration(value):
            parsed_durations.append(value)
            return (0, 30, 0)

        result = route_local_skill(
            "Remind me to drink water in 30 minutes",
            parse_reminder_duration=parse_duration,
            schedule_reminder_after=lambda **kwargs: (
                self.relative_schedule
            ),
            save_local_reminder=save_local_reminder,
        )

        self.assertEqual(parsed_durations, ["30 minutes"])
        self.assertEqual(
            saved,
            [
                (
                    "drink water",
                    REMINDER_KIND_REMINDER,
                    self.relative_schedule.due_at_utc,
                )
            ],
        )
        self.assertEqual(
            result.skill_name,
            "create_local_reminder",
        )
        self.assertEqual(
            result.message,
            (
                "Saved local reminder 2. I will remind you to "
                "drink water in 30 minutes, sir."
            ),
        )

    def test_tomorrow_reminder_uses_explicit_clock_time(self):
        saved = []
        schedule_calls = []

        def save_local_reminder(text, *, kind, due_at):
            saved.append((text, kind, due_at))
            return make_reminder(
                3,
                text,
                kind=kind,
            )

        def schedule_tomorrow(**kwargs):
            schedule_calls.append(kwargs)
            return self.tomorrow_schedule

        result = route_local_skill(
            "Remind me tomorrow at 8 PM to call Dad",
            schedule_reminder_tomorrow=schedule_tomorrow,
            save_local_reminder=save_local_reminder,
        )

        self.assertEqual(
            schedule_calls,
            [
                {
                    "hour": 8,
                    "minute": 0,
                    "meridiem": "PM",
                }
            ],
        )
        self.assertEqual(
            saved,
            [
                (
                    "call Dad",
                    REMINDER_KIND_REMINDER,
                    self.tomorrow_schedule.due_at_utc,
                )
            ],
        )
        self.assertEqual(
            result.message,
            (
                "Saved local reminder 3. I will remind you to "
                "call Dad tomorrow at 8:00 PM, sir."
            ),
        )

    def test_invalid_duration_does_not_save_a_reminder(self):
        saved = []

        def parse_duration(value):
            raise ReminderScheduleError("test failure")

        result = route_local_skill(
            "Remind me to drink water in five minutes",
            parse_reminder_duration=parse_duration,
            save_local_reminder=lambda *args, **kwargs: (
                saved.append((args, kwargs))
            ),
        )

        self.assertEqual(saved, [])
        self.assertEqual(
            result.message,
            (
                "I need a numeric reminder duration, such as "
                "30 minutes, sir."
            ),
        )

    def test_list_reminders_prints_stable_details(self):
        output = []
        reminder = make_reminder(1, "Drink water")

        result = route_local_skill(
            "List reminders",
            load_local_reminders=lambda: (reminder,),
            format_local_reminders=lambda reminders: (
                "Local reminders:\n"
                "1. [PENDING | due 2026-07-07T09:00:00Z] "
                "Drink water"
            ),
            console_output=output.append,
        )

        self.assertEqual(
            result.skill_name,
            "list_local_reminders",
        )
        self.assertEqual(
            result.message,
            "I printed 1 local reminders, sir.",
        )
        self.assertIn(
            "1. [PENDING | due",
            "\n".join(output),
        )

    def test_cancel_reminder_requires_confirmation(self):
        reminder = make_reminder(2, "Drink water")
        store = ReminderCancelConfirmationStore(
            clock=lambda: 100.0,
            timeout_seconds=15.0,
        )
        cancel_calls = []

        result = route_local_skill(
            "Cancel reminder 2",
            load_local_reminders=lambda: (reminder,),
            cancel_local_reminder=lambda *args, **kwargs: (
                cancel_calls.append((args, kwargs))
            ),
            reminder_cancel_confirmations=store,
        )

        self.assertEqual(cancel_calls, [])
        self.assertTrue(result.requires_confirmation)
        self.assertIn(
            "Confirm cancel reminder 2",
            result.message,
        )

    def test_confirm_cancel_uses_exact_reminder_snapshot(self):
        reminder = make_reminder(2, "Drink water")
        store = ReminderCancelConfirmationStore(
            clock=lambda: 100.0,
            timeout_seconds=15.0,
        )
        store.begin(reminder)
        cancelled = []

        def cancel_local_reminder(
            reminder_id: int,
            *,
            expected_reminder: LocalReminder,
        ) -> LocalReminder:
            cancelled.append((reminder_id, expected_reminder))
            return expected_reminder

        result = route_local_skill(
            "Confirm cancel reminder 2",
            cancel_local_reminder=cancel_local_reminder,
            reminder_cancel_confirmations=store,
        )

        self.assertEqual(cancelled, [(2, reminder)])
        self.assertEqual(
            result.message,
            "Cancelled local reminder 2, sir.",
        )

    def test_mismatched_cancel_confirmation_clears_request(self):
        reminder = make_reminder(2, "Drink water")
        store = ReminderCancelConfirmationStore(
            clock=lambda: 100.0,
            timeout_seconds=15.0,
        )

        store.begin(reminder)

        result = route_local_skill(
            "Confirm cancel reminder 1",
            reminder_cancel_confirmations=store,
        )

        self.assertIn("did not match", result.message)
        self.assertEqual(store.confirm(2).status, "none")

    def test_cancel_reminder_cancellation_clears_request(self):
        reminder = make_reminder(2, "Drink water")
        store = ReminderCancelConfirmationStore(
            clock=lambda: 100.0,
            timeout_seconds=15.0,
        )
        store.begin(reminder)

        result = route_local_skill(
            "Cancel reminder cancellation",
            reminder_cancel_confirmations=store,
        )

        self.assertEqual(
            result.message,
            "Pending cancellation of local reminder 2 cancelled, sir.",
        )
        self.assertEqual(store.confirm(2).status, "none")

    def test_storage_errors_are_reported_safely(self):
        result = route_local_skill(
            "List reminders",
            load_local_reminders=lambda: (
                (_ for _ in ()).throw(
                    LocalRemindersError("storage test failure")
                )
            ),
        )

        self.assertEqual(
            result.message,
            "I could not read local reminders safely, sir.",
        )