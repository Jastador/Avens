from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from skills.reminder_schedule import (
    ReminderScheduleError,
    format_duration,
    parse_duration_components,
    schedule_after_duration,
    schedule_tomorrow_at,
)


class ReminderScheduleTests(unittest.TestCase):
    def setUp(self):
        self.india_timezone = timezone(
            timedelta(hours=5, minutes=30)
        )
        self.local_now = datetime(
            2026,
            7,
            7,
            18,
            30,
            tzinfo=self.india_timezone,
        )

    def test_relative_schedule_uses_utc_and_a_clear_description(self):
        schedule = schedule_after_duration(
            hours=1,
            minutes=2,
            seconds=3,
            now=lambda: self.local_now,
        )

        self.assertEqual(
            schedule.due_at_utc,
            datetime(
                2026,
                7,
                7,
                14,
                2,
                3,
                tzinfo=timezone.utc,
            ),
        )
        self.assertEqual(
            schedule.description,
            "in 1 hour, 2 minutes, and 3 seconds",
        )

    def test_relative_schedule_rejects_zero_duration(self):
        with self.assertRaisesRegex(
            ReminderScheduleError,
            "greater than zero",
        ):
            schedule_after_duration(
                now=lambda: self.local_now
            )

    def test_tomorrow_at_uses_local_time_then_converts_to_utc(self):
        schedule = schedule_tomorrow_at(
            hour=8,
            minute=0,
            meridiem="PM",
            now=lambda: self.local_now,
        )

        self.assertEqual(
            schedule.due_at_utc,
            datetime(
                2026,
                7,
                8,
                14,
                30,
                tzinfo=timezone.utc,
            ),
        )
        self.assertEqual(
            schedule.description,
            "tomorrow at 8:00 PM",
        )

    def test_tomorrow_at_handles_midnight_correctly(self):
        schedule = schedule_tomorrow_at(
            hour=12,
            minute=5,
            meridiem="AM",
            now=lambda: self.local_now,
        )

        self.assertEqual(
            schedule.due_at_utc,
            datetime(
                2026,
                7,
                7,
                18,
                35,
                tzinfo=timezone.utc,
            ),
        )

    def test_invalid_clock_values_are_rejected(self):
        with self.assertRaisesRegex(
            ReminderScheduleError,
            "between 1 and 12",
        ):
            schedule_tomorrow_at(
                hour=13,
                minute=0,
                meridiem="PM",
                now=lambda: self.local_now,
            )

        with self.assertRaisesRegex(
            ReminderScheduleError,
            "AM or PM",
        ):
            schedule_tomorrow_at(
                hour=8,
                minute=0,
                meridiem="evening",
                now=lambda: self.local_now,
            )

    def test_parse_duration_components_handles_explicit_units(self):
        self.assertEqual(
            parse_duration_components(
                "1 hour, 2 minutes, and 3 seconds"
            ),
            (1, 2, 3),
        )
        self.assertEqual(
            parse_duration_components("5 minutes"),
            (0, 5, 0),
        )
        self.assertEqual(
            parse_duration_components(
                "1 hour 30 minutes"
            ),
            (1, 30, 0),
        )

    def test_parse_duration_components_rejects_ambiguous_input(self):
        invalid_values = (
            "",
            "five minutes",
            "1 hour and 2 hours",
            "1 hour plus 2 minutes",
            "0 minutes",
        )

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(
                    ReminderScheduleError
                ):
                    parse_duration_components(value)

    def test_format_duration_uses_singular_and_plural_units(self):
        self.assertEqual(
            format_duration(minutes=1),
            "1 minute",
        )
        self.assertEqual(
            format_duration(hours=2, seconds=1),
            "2 hours and 1 second",
        )