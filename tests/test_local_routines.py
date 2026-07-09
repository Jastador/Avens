from __future__ import annotations

import unittest

from skills.local_routines import (
    LocalRoutineError,
    format_routine_list,
    format_routine_preview,
    get_routine_definition,
    list_local_routines,
)


class LocalRoutinesTests(unittest.TestCase):
    def test_lists_four_initial_routines(self):
        routines = list_local_routines()

        self.assertEqual(
            [routine.routine_id for routine in routines],
            [
                "study",
                "project_dev",
                "gaming",
                "market_prep",
            ],
        )

    def test_resolves_spoken_aliases_exactly(self):
        self.assertEqual(
            get_routine_definition("study mode").routine_id,
            "study",
        )
        self.assertEqual(
            get_routine_definition("dev mode").routine_id,
            "project_dev",
        )
        self.assertEqual(
            get_routine_definition("gaming mode").routine_id,
            "gaming",
        )
        self.assertEqual(
            get_routine_definition("market-prep mode").routine_id,
            "market_prep",
        )

    def test_unknown_routine_is_rejected(self):
        with self.assertRaises(LocalRoutineError):
            get_routine_definition("chaos mode")

    def test_routine_list_mentions_preview_commands(self):
        formatted = format_routine_list()

        self.assertIn("Available local routines:", formatted)
        self.assertIn("Study Mode", formatted)
        self.assertIn("Project/Dev Mode", formatted)
        self.assertIn("Gaming Mode", formatted)
        self.assertIn("Market-Prep Mode", formatted)
        self.assertIn("What does study mode do?", formatted)

    def test_study_preview_is_preview_only(self):
        routine = get_routine_definition("study mode")
        formatted = format_routine_preview(routine)

        self.assertIn("Study Mode", formatted)
        self.assertIn("Google Chrome", formatted)
        self.assertIn("study URLs, configured privately later", formatted)
        self.assertIn("50 minutes", formatted)
        self.assertIn(
            "Preview only: no apps, URLs, settings, timers, or "
            "hardware controls were changed.",
            formatted,
        )

    def test_gaming_preview_marks_nitrosense_confirmation(self):
        routine = get_routine_definition("gaming mode")
        formatted = format_routine_preview(routine)

        self.assertIn("Steam", formatted)
        self.assertIn("Discord", formatted)
        self.assertIn("Performance mode and Fan Max", formatted)
        self.assertIn("[requires confirmation]", formatted)


if __name__ == "__main__":
    unittest.main()