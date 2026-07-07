from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skills.local_reminders import (
    LocalRemindersError,
    REMINDER_KIND_REMINDER,
    REMINDER_KIND_TIMER,
    REMINDER_STATUS_CANCELLED,
    REMINDER_STATUS_DELIVERED,
    REMINDER_STATUS_PENDING,
    cancel_reminder,
    claim_due_reminders,
    format_reminders,
    load_reminders,
    save_reminder,
    LocalReminder,
    format_due_reminder_alert,
)


class LocalRemindersTests(unittest.TestCase):
    def setUp(self):
        self.created_at = datetime(
            2026,
            7,
            7,
            8,
            30,
            tzinfo=timezone.utc,
        )

    def test_save_reminder_creates_a_numbered_json_record(self):
        with TemporaryDirectory() as temporary_directory:
            reminder_file = (
                Path(temporary_directory)
                / "reminders.json"
            )

            reminder = save_reminder(
                "  Drink   water  ",
                kind=REMINDER_KIND_REMINDER,
                due_at=self.created_at + timedelta(minutes=30),
                reminder_file=reminder_file,
                now=lambda: self.created_at,
            )

            payload = json.loads(
                reminder_file.read_text(encoding="utf-8")
            )

        self.assertEqual(reminder.reminder_id, 1)
        self.assertEqual(reminder.text, "Drink water")
        self.assertEqual(reminder.kind, REMINDER_KIND_REMINDER)
        self.assertEqual(
            reminder.due_at_utc,
            "2026-07-07T09:00:00Z",
        )
        self.assertEqual(
            reminder.status,
            REMINDER_STATUS_PENDING,
        )
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["next_id"], 2)
        self.assertEqual(payload["reminders"][0]["id"], 1)

    def test_due_time_must_be_in_the_future(self):
        with TemporaryDirectory() as temporary_directory:
            reminder_file = (
                Path(temporary_directory)
                / "reminders.json"
            )

            with self.assertRaisesRegex(
                LocalRemindersError,
                "must be in the future",
            ):
                save_reminder(
                    "Too late",
                    kind=REMINDER_KIND_TIMER,
                    due_at=self.created_at,
                    reminder_file=reminder_file,
                    now=lambda: self.created_at,
                )

    def test_cancel_preserves_records_and_future_ids(self):
        with TemporaryDirectory() as temporary_directory:
            reminder_file = (
                Path(temporary_directory)
                / "reminders.json"
            )

            first = save_reminder(
                "First",
                kind=REMINDER_KIND_TIMER,
                due_at=self.created_at + timedelta(minutes=5),
                reminder_file=reminder_file,
                now=lambda: self.created_at,
            )
            second = save_reminder(
                "Second",
                kind=REMINDER_KIND_REMINDER,
                due_at=self.created_at + timedelta(minutes=10),
                reminder_file=reminder_file,
                now=lambda: self.created_at,
            )

            cancelled = cancel_reminder(
                first.reminder_id,
                reminder_file=reminder_file,
                now=lambda: self.created_at + timedelta(minutes=1),
            )

            third = save_reminder(
                "Third",
                kind=REMINDER_KIND_REMINDER,
                due_at=self.created_at + timedelta(minutes=15),
                reminder_file=reminder_file,
                now=lambda: self.created_at,
            )

            reminders = load_reminders(
                reminder_file=reminder_file
            )

        self.assertEqual(
            cancelled.status,
            REMINDER_STATUS_CANCELLED,
        )
        self.assertEqual(second.reminder_id, 2)
        self.assertEqual(third.reminder_id, 3)
        self.assertEqual(
            [reminder.reminder_id for reminder in reminders],
            [1, 2, 3],
        )

    def test_cancel_unknown_reminder_keeps_storage_unchanged(self):
        with TemporaryDirectory() as temporary_directory:
            reminder_file = (
                Path(temporary_directory)
                / "reminders.json"
            )

            save_reminder(
                "Keep this",
                kind=REMINDER_KIND_REMINDER,
                due_at=self.created_at + timedelta(minutes=5),
                reminder_file=reminder_file,
                now=lambda: self.created_at,
            )
            original_text = reminder_file.read_text(
                encoding="utf-8"
            )

            with self.assertRaisesRegex(
                LocalRemindersError,
                "does not exist",
            ):
                cancel_reminder(
                    99,
                    reminder_file=reminder_file,
                )

            self.assertEqual(
                reminder_file.read_text(encoding="utf-8"),
                original_text,
            )

    def test_cancel_refuses_a_changed_pending_snapshot(self):
        with TemporaryDirectory() as temporary_directory:
            reminder_file = (
                Path(temporary_directory)
                / "reminders.json"
            )

            reminder = save_reminder(
                "Original text",
                kind=REMINDER_KIND_REMINDER,
                due_at=self.created_at + timedelta(minutes=5),
                reminder_file=reminder_file,
                now=lambda: self.created_at,
            )

            payload = json.loads(
                reminder_file.read_text(encoding="utf-8")
            )
            payload["reminders"][0]["text"] = "Changed text"

            reminder_file.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                LocalRemindersError,
                "changed since",
            ):
                cancel_reminder(
                    reminder.reminder_id,
                    expected_reminder=reminder,
                    reminder_file=reminder_file,
                )

    def test_claim_due_reminders_marks_them_delivered_once(self):
        with TemporaryDirectory() as temporary_directory:
            reminder_file = (
                Path(temporary_directory)
                / "reminders.json"
            )

            due = save_reminder(
                "Drink water",
                kind=REMINDER_KIND_REMINDER,
                due_at=self.created_at + timedelta(minutes=5),
                reminder_file=reminder_file,
                now=lambda: self.created_at,
            )
            future = save_reminder(
                "Later task",
                kind=REMINDER_KIND_REMINDER,
                due_at=self.created_at + timedelta(minutes=20),
                reminder_file=reminder_file,
                now=lambda: self.created_at,
            )

            claimed = claim_due_reminders(
                reminder_file=reminder_file,
                now=lambda: self.created_at + timedelta(minutes=5),
            )
            claimed_again = claim_due_reminders(
                reminder_file=reminder_file,
                now=lambda: self.created_at + timedelta(minutes=5),
            )
            reminders = load_reminders(
                reminder_file=reminder_file
            )

        self.assertEqual(
            [reminder.reminder_id for reminder in claimed],
            [due.reminder_id],
        )
        self.assertEqual(
            claimed[0].status,
            REMINDER_STATUS_DELIVERED,
        )
        self.assertEqual(claimed_again, ())
        self.assertEqual(
            reminders[0].status,
            REMINDER_STATUS_DELIVERED,
        )
        self.assertEqual(
            reminders[1].reminder_id,
            future.reminder_id,
        )
        self.assertEqual(
            reminders[1].status,
            REMINDER_STATUS_PENDING,
        )

    def test_delivered_reminder_cannot_be_cancelled(self):
        with TemporaryDirectory() as temporary_directory:
            reminder_file = (
                Path(temporary_directory)
                / "reminders.json"
            )

            reminder = save_reminder(
                "Already due",
                kind=REMINDER_KIND_TIMER,
                due_at=self.created_at + timedelta(minutes=1),
                reminder_file=reminder_file,
                now=lambda: self.created_at,
            )

            claim_due_reminders(
                reminder_file=reminder_file,
                now=lambda: self.created_at + timedelta(minutes=1),
            )

            with self.assertRaisesRegex(
                LocalRemindersError,
                "already delivered",
            ):
                cancel_reminder(
                    reminder.reminder_id,
                    reminder_file=reminder_file,
                )

    def test_corrupt_reminders_are_not_overwritten(self):
        with TemporaryDirectory() as temporary_directory:
            reminder_file = (
                Path(temporary_directory)
                / "reminders.json"
            )
            original_text = "{not valid json"

            reminder_file.write_text(
                original_text,
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                LocalRemindersError,
                "not valid JSON",
            ):
                save_reminder(
                    "Do not overwrite",
                    kind=REMINDER_KIND_REMINDER,
                    due_at=self.created_at + timedelta(minutes=5),
                    reminder_file=reminder_file,
                    now=lambda: self.created_at,
                )

            self.assertEqual(
                reminder_file.read_text(encoding="utf-8"),
                original_text,
            )

    def test_format_reminders_shows_status_and_empty_store(self):
        with TemporaryDirectory() as temporary_directory:
            reminder_file = (
                Path(temporary_directory)
                / "reminders.json"
            )

            reminder = save_reminder(
                "Drink water",
                kind=REMINDER_KIND_REMINDER,
                due_at=self.created_at + timedelta(minutes=5),
                reminder_file=reminder_file,
                now=lambda: self.created_at,
            )

        self.assertIn(
            "1. [PENDING | due 2026-07-07T08:35:00Z] "
            "Drink water",
            format_reminders((reminder,)),
        )
        self.assertIn(
            "- No local reminders saved.",
            format_reminders(()),
        )

    def test_format_due_reminder_alert_uses_kind_and_status(self):
        timer = LocalReminder(
            reminder_id=1,
            text="Timer",
            kind=REMINDER_KIND_TIMER,
            due_at_utc="2026-07-07T08:35:00Z",
            created_at_utc="2026-07-07T08:30:00Z",
            status=REMINDER_STATUS_DELIVERED,
            delivered_at_utc="2026-07-07T08:35:00Z",
        )
        reminder = LocalReminder(
            reminder_id=2,
            text="Drink water",
            kind=REMINDER_KIND_REMINDER,
            due_at_utc="2026-07-07T09:00:00Z",
            created_at_utc="2026-07-07T08:30:00Z",
            status=REMINDER_STATUS_DELIVERED,
            delivered_at_utc="2026-07-07T09:00:00Z",
        )
        pending = LocalReminder(
            reminder_id=3,
            text="Call Dad",
            kind=REMINDER_KIND_REMINDER,
            due_at_utc="2026-07-07T10:00:00Z",
            created_at_utc="2026-07-07T08:30:00Z",
            status=REMINDER_STATUS_PENDING,
        )

        self.assertEqual(
            format_due_reminder_alert(timer),
            "Timer 1 is complete, sir.",
        )
        self.assertEqual(
            format_due_reminder_alert(reminder),
            "Reminder 2: Drink water, sir.",
        )

        with self.assertRaisesRegex(
            LocalRemindersError,
            "Only a delivered reminder",
        ):
            format_due_reminder_alert(pending)