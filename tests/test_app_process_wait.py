from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from skills.app_catalog import APP_PATHS_SOURCE, CatalogApp
from skills.app_process_wait import wait_for_app_process


def make_app(name: str = "Steam") -> CatalogApp:
    return CatalogApp(
        display_name=name,
        normalized_name=name.casefold(),
        launch_path=Path(r"C:\Fake\App.lnk"),
        source=APP_PATHS_SOURCE,
    )


class AppProcessWaitTests(unittest.TestCase):
    def test_waits_until_exact_process_appears(self):
        app = make_app()
        polls = []
        process_snapshots = iter(
            (
                (),
                (r"G:\Games\Launchers\Steam\steam.exe",),
            )
        )

        result = wait_for_app_process(
            "Steam",
            resolve_app=lambda _: (app,),
            resolve_launch_target=lambda _: SimpleNamespace(
                target_path=r"G:\Games\Launchers\Steam\Steam.exe"
            ),
            list_process_paths=lambda: next(process_snapshots),
            sleep=lambda seconds: polls.append(seconds),
            monotonic=iter((0.0, 0.0, 0.25, 0.25)).__next__,
            timeout_seconds=5.0,
            poll_interval_seconds=0.25,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.display_name, "Steam")
        self.assertEqual(result.process_count, 1)
        self.assertEqual(
            result.message,
            "Steam is running with 1 verified process, sir.",
        )
        self.assertEqual(polls, [0.25])

    def test_rejects_wrong_process_path(self):
        app = make_app()
        now = 0.0

        def monotonic() -> float:
            return now

        def sleep(_: float) -> None:
            nonlocal now
            now += 0.25

        result = wait_for_app_process(
            "Steam",
            resolve_app=lambda _: (app,),
            resolve_launch_target=lambda _: SimpleNamespace(
                target_path=r"G:\Games\Launchers\Steam\Steam.exe"
            ),
            list_process_paths=lambda: (
                r"C:\Other\Steam.exe",
            ),
            sleep=sleep,
            monotonic=monotonic,
            timeout_seconds=0.5,
            poll_interval_seconds=0.25,
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "Steam did not start a verified process within 0.5 "
            "seconds, sir.",
        )

    def test_rejects_missing_exact_app(self):
        result = wait_for_app_process(
            "Steam",
            resolve_app=lambda _: (),
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "I could not find an exact local app named Steam, sir.",
        )

    def test_rejects_ambiguous_exact_apps(self):
        result = wait_for_app_process(
            "Steam",
            resolve_app=lambda _: (make_app(), make_app()),
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "I found 2 exact local apps named Steam. I will not "
            "guess which one to verify, sir.",
        )

    def test_rejects_missing_launch_target(self):
        app = make_app()

        result = wait_for_app_process(
            "Steam",
            resolve_app=lambda _: (app,),
            resolve_launch_target=lambda _: None,
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "I could not safely identify the process target for "
            "Steam, sir.",
        )

    def test_rejects_invalid_timeouts(self):
        with self.assertRaises(ValueError):
            wait_for_app_process("Steam", timeout_seconds=-0.1)

        with self.assertRaises(ValueError):
            wait_for_app_process("Steam", poll_interval_seconds=0.0)


if __name__ == "__main__":
    unittest.main()