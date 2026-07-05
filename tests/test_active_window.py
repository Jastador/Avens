from __future__ import annotations

import unittest

import win32con

from skills.active_window import control_active_window


class ActiveWindowControlTests(unittest.TestCase):
    def test_runs_each_allowlisted_action_for_focused_window(self):
        cases = {
            "minimize": (
                win32con.SW_MINIMIZE,
                "Minimized the focused window, sir.",
            ),
            "maximize": (
                win32con.SW_MAXIMIZE,
                "Maximized the focused window, sir.",
            ),
            "restore": (
                win32con.SW_RESTORE,
                "Restored the focused window, sir.",
            ),
        }

        for action, (show_command, expected_message) in cases.items():
            with self.subTest(action=action):
                foreground_calls: list[None] = []
                show_calls: list[tuple[int, int]] = []

                def fake_foreground_window() -> int:
                    foreground_calls.append(None)
                    return 4242

                def fake_is_window(window_handle: int) -> bool:
                    return window_handle == 4242

                def fake_show_window(
                    window_handle: int,
                    command: int,
                ) -> int:
                    show_calls.append((window_handle, command))
                    return 1

                result = control_active_window(
                    action,
                    get_foreground_window=fake_foreground_window,
                    is_window=fake_is_window,
                    show_window=fake_show_window,
                )

                self.assertTrue(result.success)
                self.assertEqual(result.message, expected_message)
                self.assertEqual(foreground_calls, [None])
                self.assertEqual(
                    show_calls,
                    [(4242, show_command)],
                )

    def test_rejects_unknown_action_before_using_windows_api(self):
        def forbidden_foreground_window() -> int:
            self.fail(
                "Unsupported actions must not query the foreground window."
            )

        result = control_active_window(
            "close",
            get_foreground_window=forbidden_foreground_window,
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "I cannot perform that active-window action, sir.",
        )

    def test_handles_missing_focused_window_safely(self):
        def forbidden_is_window(_: int) -> bool:
            self.fail(
                "No foreground handle must not reach window validation."
            )

        result = control_active_window(
            "minimize",
            get_foreground_window=lambda: 0,
            is_window=forbidden_is_window,
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "I could not find a focused window to minimize, sir.",
        )

    def test_handles_invalid_focused_window_without_showing_it(self):
        def forbidden_show_window(_: int, __: int) -> int:
            self.fail(
                "Invalid window handles must not reach ShowWindow."
            )

        result = control_active_window(
            "maximize",
            get_foreground_window=lambda: 4242,
            is_window=lambda _: False,
            show_window=forbidden_show_window,
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "I could not find a focused window to maximize, sir.",
        )

    def test_handles_windows_api_failure_safely(self):
        def failing_show_window(_: int, __: int) -> int:
            raise OSError("Windows rejected the state change.")

        result = control_active_window(
            "restore",
            get_foreground_window=lambda: 4242,
            is_window=lambda _: True,
            show_window=failing_show_window,
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "I could not restore the focused window, sir.",
        )