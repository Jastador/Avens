from __future__ import annotations

from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReminderLegacyRetirementTests(unittest.TestCase):
    def test_legacy_butler_module_is_removed(self):
        self.assertFalse(
            (PROJECT_ROOT / "core" / "butler.py").exists()
        )

    def test_brain_no_longer_advertises_legacy_reminder_tags(self):
        brain_source = (
            PROJECT_ROOT / "core" / "brain.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("<REMIND:", brain_source)

    def test_legacy_command_dispatch_no_longer_has_reminder_code(self):
        commands_source = (
            PROJECT_ROOT / "automation" / "commands.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn(
            "from core.butler import",
            commands_source,
        )
        self.assertNotIn("set_reminder(", commands_source)
        self.assertNotIn(
            "GHOST THREAD REMINDERS",
            commands_source,
        )

    def test_app_blocks_retired_legacy_reminder_tags(self):
        app_source = (
            PROJECT_ROOT / "app.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "retired_reminder_prefixes",
            app_source,
        )
        self.assertIn(
            "Retired legacy reminder tag blocked",
            app_source,
        )
        self.assertIn('"<remind:"', app_source)
        self.assertNotIn(
            "Reminders only if user asks",
            app_source,
        )