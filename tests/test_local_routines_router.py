from __future__ import annotations

import unittest

from skills.local_routines import (
    ROUTINE_STEP_DONE,
    ROUTINE_STEP_FAILED,
    ROUTINE_STEP_NEEDS_CONFIRMATION,
    LocalRoutineError,
    LocalRoutineRunReport,
    RoutineStepResult,
    get_routine_definition,
)
from skills.router import route_local_skill


def _make_report(
    routine_name: str,
    *,
    status: str = ROUTINE_STEP_DONE,
) -> LocalRoutineRunReport:
    routine = get_routine_definition(routine_name)

    return LocalRoutineRunReport(
        routine=routine,
        steps=(
            RoutineStepResult(
                action=routine.actions[0],
                status=status,
                message="stub step",
            ),
        ),
    )


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

    def test_starts_study_mode_and_prints_run_report(self):
        output = []

        result = route_local_skill(
            "Start study mode",
            run_local_routine_plan=lambda routine, **_: _make_report(
                routine.display_name
            ),
            format_local_routine_run_report=lambda _: "run report",
            console_output=output.append,
        )

        self.assertEqual(result.skill_name, "start_local_routine")
        self.assertEqual(
            result.message,
            "I started Study Mode, sir.",
        )
        self.assertEqual(output, ["run report"])

    def test_starts_gaming_mode_with_confirmation_followup(self):
        output = []

        result = route_local_skill(
            "Start gaming mode",
            run_local_routine_plan=lambda routine, **_: _make_report(
                routine.display_name,
                status=ROUTINE_STEP_NEEDS_CONFIRMATION,
            ),
            format_local_routine_run_report=lambda _: "gaming report",
            console_output=output.append,
        )

        self.assertEqual(result.skill_name, "start_local_routine")
        self.assertEqual(
            result.message,
            "I started Gaming Mode. NitroSense still needs "
            "confirmation, sir.",
        )
        self.assertEqual(output, ["gaming report"])

    def test_start_routine_reports_failures(self):
        output = []

        result = route_local_skill(
            "Start project mode",
            run_local_routine_plan=lambda routine, **_: _make_report(
                routine.display_name,
                status=ROUTINE_STEP_FAILED,
            ),
            format_local_routine_run_report=lambda _: "failure report",
            console_output=output.append,
        )

        self.assertEqual(result.skill_name, "start_local_routine")
        self.assertEqual(
            result.message,
            "I ran Project/Dev Mode with some failures, sir.",
        )
        self.assertEqual(output, ["failure report"])


if __name__ == "__main__":
    unittest.main()