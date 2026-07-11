from __future__ import annotations

import unittest
from pathlib import Path

from skills.app_catalog import APP_PATHS_SOURCE, CatalogApp
from skills.app_window_wait import wait_for_app_window
from skills.named_window import NamedWindowMatchResult


def make_app(name: str = "Discord") -> CatalogApp:
    return CatalogApp(
        display_name=name,
        normalized_name=name.casefold(),
        launch_path=Path(r"C:\Fake\App.lnk"),
        source=APP_PATHS_SOURCE,
    )


class AppWindowWaitTests(unittest.TestCase):
    def test_waits_until_verified_window_appears(self):
        app = make_app()
        polls = []

        responses = iter(
            (
                NamedWindowMatchResult(
                    display_name="Discord",
                    window_handles=(),
                    error_message=None,
                ),
                NamedWindowMatchResult(
                    display_name="Discord",
                    window_handles=(700,),
                    error_message=None,
                ),
            )
        )

        result = wait_for_app_window(
            "Discord",
            resolve_app=lambda _: (app,),
            inspect_windows=lambda _: next(responses),
            sleep=lambda seconds: polls.append(seconds),
            monotonic=iter((0.0, 0.0, 0.25, 0.25)).__next__,
            timeout_seconds=5.0,
            poll_interval_seconds=0.25,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.display_name, "Discord")
        self.assertEqual(result.window_count, 1)
        self.assertEqual(
            result.message,
            "Discord is open with 1 verified window, sir.",
        )
        self.assertEqual(polls, [0.25])

    def test_times_out_without_verified_window(self):
        app = make_app()
        now = 0.0

        def monotonic() -> float:
            return now

        def sleep(_: float) -> None:
            nonlocal now
            now += 0.25

        result = wait_for_app_window(
            "Discord",
            resolve_app=lambda _: (app,),
            inspect_windows=lambda _: NamedWindowMatchResult(
                display_name="Discord",
                window_handles=(),
                error_message=None,
            ),
            sleep=sleep,
            monotonic=monotonic,
            timeout_seconds=0.5,
            poll_interval_seconds=0.25,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.window_count, 0)
        self.assertEqual(
            result.message,
            "Discord did not open a verified window within 0.5 "
            "seconds, sir.",
        )

    def test_rejects_missing_exact_app(self):
        result = wait_for_app_window(
            "Discord",
            resolve_app=lambda _: (),
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "I could not find an exact local app named Discord, sir.",
        )

    def test_rejects_ambiguous_exact_apps(self):
        result = wait_for_app_window(
            "Discord",
            resolve_app=lambda _: (make_app(), make_app()),
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "I found 2 exact local apps named Discord. I will not "
            "guess which one to verify, sir.",
        )

    def test_returns_inspection_error_safely(self):
        app = make_app()

        result = wait_for_app_window(
            "Discord",
            resolve_app=lambda _: (app,),
            inspect_windows=lambda _: NamedWindowMatchResult(
                display_name="Discord",
                window_handles=(),
                error_message=(
                    "I could not inspect open windows for Discord, sir."
                ),
            ),
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "I could not inspect open windows for Discord, sir.",
        )

    def test_rejects_invalid_timeouts(self):
        with self.assertRaises(ValueError):
            wait_for_app_window("Discord", timeout_seconds=-0.1)

        with self.assertRaises(ValueError):
            wait_for_app_window("Discord", poll_interval_seconds=0.0)


if __name__ == "__main__":
    unittest.main()