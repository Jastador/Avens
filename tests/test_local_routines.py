from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
import unittest

from skills.app_launcher import LaunchResult
from skills.local_routine_settings import RoutineSettings
from skills.local_reminders import REMINDER_KIND_TIMER
from skills.local_routines import (
    ROUTINE_STEP_DONE,
    ROUTINE_STEP_NEEDS_CONFIRMATION,
    ROUTINE_STEP_SKIPPED,
    LocalRoutineError,
    format_routine_list,
    format_routine_preview,
    format_routine_run_report,
    get_routine_definition,
    list_local_routines,
    run_local_routine,
)
from skills.local_routine_urls import (
    LocalRoutineUrlNotConfiguredError,
    UrlGroupOpenReport,
)
from skills.system_controls import BrightnessState, VolumeState


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

    def test_routine_list_mentions_preview_and_run_commands(self):
        formatted = format_routine_list()

        self.assertIn("Available local routines:", formatted)
        self.assertIn("Study Mode", formatted)
        self.assertIn("Project/Dev Mode", formatted)
        self.assertIn("Gaming Mode", formatted)
        self.assertIn("Market-Prep Mode", formatted)
        self.assertIn("What does study mode do?", formatted)
        self.assertIn("Start study mode", formatted)
        self.assertIn("Start gaming mode", formatted)

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

    def test_study_runner_skips_missing_private_url_group(self):
        routine = get_routine_definition("study mode")

        def open_url_group(group_name: str) -> UrlGroupOpenReport:
            raise LocalRoutineUrlNotConfiguredError(
                f"Approved URL group '{group_name}' is not configured."
            )

        report = run_local_routine(
            routine,
            launch_app=lambda name: LaunchResult(
                success=True,
                display_name=name,
                message=f"Launched {name}",
            ),
            set_brightness=lambda level: BrightnessState(level=level),
            set_volume=lambda level: VolumeState(
                level=level,
                muted=False,
            ),
            schedule_timer_after=lambda **_: SimpleNamespace(
                due_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
                description="in 50 minutes",
            ),
            save_timer=lambda *_args, **_kwargs: SimpleNamespace(
                reminder_id=7
            ),
            open_night_light=lambda: None,
            open_url_group=open_url_group,
        )

        self.assertFalse(report.has_failed_steps)
        self.assertIn(
            ROUTINE_STEP_SKIPPED,
            [step.status for step in report.steps],
        )
        self.assertIn(
            "not configured",
            format_routine_run_report(report),
        )

    def test_gaming_preview_marks_nitrosense_confirmation(self):
        routine = get_routine_definition("gaming mode")
        formatted = format_routine_preview(routine)

        self.assertIn("Steam", formatted)
        self.assertIn("Discord", formatted)
        self.assertIn("Performance mode and Fan Max", formatted)
        self.assertIn("[requires confirmation]", formatted)

    def test_project_preview_includes_android_studio(self):
        routine = get_routine_definition("project mode")
        formatted = format_routine_preview(routine)

        self.assertIn("Visual Studio Code", formatted)
        self.assertIn("Android Studio", formatted)
        self.assertIn("Google Chrome", formatted)

    def test_runner_applies_private_brightness_volume_settings(self):
        routine = get_routine_definition("project mode")
        calls = []

        def launch_app(name: str) -> LaunchResult:
            calls.append(("launch", name))
            return LaunchResult(
                success=True,
                display_name=name,
                message=f"Launched {name}",
            )

        def open_url_group(group_name: str) -> UrlGroupOpenReport:
            calls.append(("urls", group_name))
            return UrlGroupOpenReport(
                group_name=group_name,
                opened_urls=("https://example.com/project",),
            )

        report = run_local_routine(
            routine,
            launch_app=launch_app,
            set_brightness=lambda level: calls.append(
                ("brightness", level)
            ) or BrightnessState(level=level),
            set_volume=lambda level: calls.append(
                ("volume", level)
            ) or VolumeState(level=level, muted=False),
            open_url_group=open_url_group,
            routine_settings=RoutineSettings(
                brightness=80,
                volume=35,
            ),
        )

        self.assertFalse(report.has_failed_steps)
        self.assertIn(("launch", "Visual Studio Code"), calls)
        self.assertIn(("launch", "Android Studio"), calls)
        self.assertIn(("launch", "Google Chrome"), calls)
        self.assertIn(("urls", "project"), calls)
        self.assertIn(("brightness", 80), calls)
        self.assertIn(("volume", 35), calls)

    def test_study_runner_executes_safe_actions_and_opens_urls(self):
        routine = get_routine_definition("study mode")
        calls = []
        due_at = datetime(2026, 1, 1, tzinfo=UTC)

        def launch_app(name: str) -> LaunchResult:
            calls.append(("launch", name))
            return LaunchResult(
                success=True,
                display_name=name,
                message=f"Launched {name}",
            )

        def set_brightness(level: int) -> BrightnessState:
            calls.append(("brightness", level))
            return BrightnessState(level=level)

        def set_volume(level: int) -> VolumeState:
            calls.append(("volume", level))
            return VolumeState(level=level, muted=False)

        def schedule_timer_after(**kwargs):
            calls.append(("schedule", kwargs))
            return SimpleNamespace(
                due_at_utc=due_at,
                description="in 50 minutes",
            )

        def save_timer(text: str, **kwargs):
            calls.append(
                (
                    "timer",
                    text,
                    kwargs["kind"],
                    kwargs["due_at"],
                )
            )
            return SimpleNamespace(reminder_id=7)

        def open_url_group(group_name: str) -> UrlGroupOpenReport:
            calls.append(("urls", group_name))
            return UrlGroupOpenReport(
                group_name=group_name,
                opened_urls=("https://example.com/study",),
            )

        def open_night_light() -> None:
            calls.append(("night_light", None))

        report = run_local_routine(
            routine,
            launch_app=launch_app,
            set_brightness=set_brightness,
            set_volume=set_volume,
            schedule_timer_after=schedule_timer_after,
            save_timer=save_timer,
            open_night_light=open_night_light,
            open_url_group=open_url_group,
        )

        statuses = [step.status for step in report.steps]

        self.assertFalse(report.has_failed_steps)
        self.assertFalse(report.requires_followup_confirmation)
        self.assertIn(ROUTINE_STEP_DONE, statuses)
        self.assertNotIn(ROUTINE_STEP_SKIPPED, statuses)
        self.assertIn(("launch", "Google Chrome"), calls)
        self.assertIn(("brightness", 100), calls)
        self.assertIn(("volume", 50), calls)
        self.assertIn(("urls", "study"), calls)
        self.assertIn(
            (
                "timer",
                "Timer",
                REMINDER_KIND_TIMER,
                due_at,
            ),
            calls,
        )
        self.assertIn(("night_light", None), calls)

    def test_gaming_runner_requests_nitrosense_confirmation(self):
        routine = get_routine_definition("gaming mode")
        calls = []

        def launch_app(name: str) -> LaunchResult:
            calls.append(("launch", name))
            return LaunchResult(
                success=True,
                display_name=name,
                message=f"Launched {name}",
            )

        def set_brightness(level: int) -> BrightnessState:
            calls.append(("brightness", level))
            return BrightnessState(level=level)

        def set_volume(level: int) -> VolumeState:
            calls.append(("volume", level))
            return VolumeState(level=level, muted=False)

        def begin_nitrosense_confirmation() -> None:
            calls.append(("nitrosense", "begin"))

        report = run_local_routine(
            routine,
            launch_app=launch_app,
            set_brightness=set_brightness,
            set_volume=set_volume,
            begin_nitrosense_confirmation=(
                begin_nitrosense_confirmation
            ),
        )

        self.assertFalse(report.has_failed_steps)
        self.assertTrue(report.requires_followup_confirmation)
        self.assertIn(("launch", "Steam"), calls)
        self.assertIn(("launch", "Discord"), calls)
        self.assertIn(("nitrosense", "begin"), calls)
        self.assertIn(
            ROUTINE_STEP_NEEDS_CONFIRMATION,
            [step.status for step in report.steps],
        )

    def test_runner_reports_launch_failures_without_stopping(self):
        routine = get_routine_definition("project mode")

        def launch_app(name: str) -> LaunchResult:
            return LaunchResult(
                success=False,
                display_name=name,
                message=f"Could not launch {name}",
            )

        report = run_local_routine(
            routine,
            launch_app=launch_app,
            set_brightness=lambda level: BrightnessState(level=level),
            set_volume=lambda level: VolumeState(
                level=level,
                muted=False,
            ),
            open_url_group=lambda group_name: UrlGroupOpenReport(
                group_name=group_name,
                opened_urls=("https://example.com/project",),
            ),
        )

        self.assertTrue(report.has_failed_steps)
        self.assertIn(
            "Could not launch",
            format_routine_run_report(report),
        )


if __name__ == "__main__":
    unittest.main()