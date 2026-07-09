from __future__ import annotations

import unittest

from skills.local_routines import (
    LocalRoutineError,
    get_routine_definition,
)
from skills.router import route_local_skill


class LocalRoutinesRouterTests(unittest.TestCase):
    def test_lists_local_routines_without_executing_actions(self):
        output = []

        result = route_local_skill(
            "What routines do you have?",
            console_output=output.append,
        )

        self.assertEqual(
            result.skill_name,
            "list_local_routines",
        )
        self.assertEqual(
            result.message,
            "I printed the available local routines, sir.",
        )
        self.assertFalse(result.requires_confirmation)
        self.assertIn("Study Mode", "\n".join(output))
        self.assertIn("Gaming Mode", "\n".join(output))

    def test_previews_study_mode_without_executing_actions(self):
        output = []

        result = route_local_skill(
            "What does study mode do?",
            console_output=output.append,
        )

        joined_output = "\n".join(output)

        self.assertEqual(result.skill_name, "show_local_routine")
        self.assertEqual(
            result.message,
            "I printed the Study Mode preview, sir.",
        )
        self.assertIn("Google Chrome", joined_output)
        self.assertIn("50 minutes", joined_output)
        self.assertIn("Preview only", joined_output)

    def test_previews_gaming_mode_with_confirmation_marker(self):
        output = []

        result = route_local_skill(
            "Preview gaming mode",
            console_output=output.append,
        )

        joined_output = "\n".join(output)

        self.assertEqual(
            result.message,
            "I printed the Gaming Mode preview, sir.",
        )
        self.assertIn("Steam", joined_output)
        self.assertIn("Discord", joined_output)
        self.assertIn("[requires confirmation]", joined_output)

    def test_routine_resolution_failure_is_safe(self):
        output = []

        result = route_local_skill(
            "What does dev mode do?",
            get_local_routine=lambda _: (_ for _ in ()).throw(
                LocalRoutineError("test failure")
            ),
            console_output=output.append,
        )

        self.assertEqual(
            result.message,
            "I could not find a local routine named dev mode, sir.",
        )
        self.assertIn(
            "Local routine error: test failure",
            output,
        )

    def test_preview_dependency_can_be_injected(self):
        output = []

        result = route_local_skill(
            "What does dev mode do?",
            get_local_routine=get_routine_definition,
            format_local_routine_preview=lambda routine: (
                f"preview: {routine.routine_id}"
            ),
            console_output=output.append,
        )

        self.assertEqual(
            result.message,
            "I printed the Project/Dev Mode preview, sir.",
        )
        self.assertEqual(output, ["preview: project_dev"])


if __name__ == "__main__":
    unittest.main()