from __future__ import annotations

import os
import unittest
from pathlib import Path

import win32con

from skills.app_catalog import (
    APP_PATHS_SOURCE,
    PACKAGED_APP_SOURCE,
    CatalogApp,
    LaunchTarget,
    START_MENU_SOURCE,
)
from skills.named_window import (
    build_window_app_identity,
    close_named_app_windows,
    control_named_window,
    AppWindowIdentity,
    find_matching_windows,
)



class NamedWindowControlTests(unittest.TestCase):
    @staticmethod
    def _chrome_app() -> CatalogApp:
        return CatalogApp(
            display_name="Google Chrome",
            normalized_name="google chrome",
            launch_path=Path(
                r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            ),
            source=APP_PATHS_SOURCE,
        )

    @staticmethod
    def _chrome_target() -> LaunchTarget:
        return LaunchTarget(
            target_path=(
                r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            ),
            arguments="",
            working_directory=(
                r"C:\Program Files\Google\Chrome\Application"
            ),
        )

    def _control_chrome(
        self,
        action: str,
        **overrides: object,
    ):
        target = self._chrome_target()
        handles = tuple(
            overrides.pop("handles", (101,))
        )
        valid_handles = set(
            overrides.pop("valid_handles", handles)
        )
        visible_handles = set(
            overrides.pop("visible_handles", handles)
        )
        owned_handles = set(
            overrides.pop("owned_handles", ())
        )
        iconic_handles = set(
            overrides.pop("iconic_handles", ())
        )
        window_processes = dict(
            overrides.pop(
                "window_processes",
                {101: 5001},
            )
        )
        process_paths = dict(
            overrides.pop(
                "process_paths",
                {5001: target.target_path},
            )
        )

        options = {
            "resolve_launch_target": lambda _: target,
            "list_top_level_windows": lambda: handles,
            "is_window": lambda handle: handle in valid_handles,
            "is_window_visible": (
                lambda handle: handle in visible_handles
            ),
            "get_window_owner": (
                lambda handle: 1 if handle in owned_handles else 0
            ),
            "get_window_process_id": (
                lambda handle: window_processes.get(handle, 0)
            ),
            "get_process_image_path": (
                lambda process_id: process_paths.get(process_id)
            ),
            "get_process_aumid": lambda _: None,
            "is_iconic": lambda handle: handle in iconic_handles,
            "show_window": lambda _, __: 1,
            "set_foreground_window": lambda _: True,
        }
        options.update(overrides)

        return control_named_window(
            self._chrome_app(),
            action,
            **options,
        )

    def _close_chrome(
        self,
        close_all: bool,
        **overrides: object,
    ):
        target = self._chrome_target()
        handles = tuple(
            overrides.pop("handles", (101,))
        )
        valid_handles = set(
            overrides.pop("valid_handles", handles)
        )
        visible_handles = set(
            overrides.pop("visible_handles", handles)
        )
        owned_handles = set(
            overrides.pop("owned_handles", ())
        )
        window_processes = dict(
            overrides.pop(
                "window_processes",
                {101: 5001},
            )
        )
        process_paths = dict(
            overrides.pop(
                "process_paths",
                {5001: target.target_path},
            )
        )

        options = {
            "resolve_launch_target": lambda _: target,
            "list_top_level_windows": lambda: handles,
            "is_window": lambda handle: handle in valid_handles,
            "is_window_visible": (
                lambda handle: handle in visible_handles
            ),
            "get_window_owner": (
                lambda handle: 1 if handle in owned_handles else 0
            ),
            "get_window_process_id": (
                lambda handle: window_processes.get(handle, 0)
            ),
            "get_process_image_path": (
                lambda process_id: process_paths.get(process_id)
            ),
            "get_process_aumid": lambda _: None,
            "post_close_message": lambda _: None,
        }
        options.update(overrides)

        return close_named_app_windows(
            self._chrome_app(),
            close_all,
            **options,
        )

    def test_builds_process_start_identity_for_updater_shortcut(self):
        app = CatalogApp(
            display_name="Discord",
            normalized_name="discord",
            launch_path=Path("Discord.lnk"),
            source=START_MENU_SOURCE,
        )
        target = LaunchTarget(
            target_path=(
                r"C:\Users\Jastador\AppData\Local\Discord\Update.exe"
            ),
            arguments="--processStart Discord.exe",
            working_directory=(
                r"C:\Users\Jastador\AppData\Local\Discord"
            ),
        )

        identity = build_window_app_identity(
            app,
            resolve_launch_target=lambda _: target,
        )

        self.assertEqual(identity.display_name, "Discord")
        self.assertIsNone(identity.executable_path)
        self.assertIsNone(identity.app_user_model_id)
        self.assertEqual(identity.executable_name, "discord.exe")
        self.assertEqual(
            identity.executable_root,
            os.path.normcase(
                os.path.normpath(
                    r"C:\Users\Jastador\AppData\Local\Discord"
                )
            ),
        )

    def test_matches_process_start_window_inside_install_root(self):
        identity = AppWindowIdentity(
            display_name="Discord",
            executable_path=None,
            app_user_model_id=None,
            executable_name="discord.exe",
            executable_root=os.path.normcase(
                os.path.normpath(
                    r"C:\Users\Jastador\AppData\Local\Discord"
                )
            ),
        )

        process_paths = {
            5001: (
                r"C:\Users\Jastador\AppData\Local\Discord"
                r"\app-1.0.9245\Discord.exe"
            ),
            5002: r"C:\Other\Discord.exe",
            5003: (
                r"C:\Users\Jastador\AppData\Local\Discord"
                r"\Update.exe"
            ),
        }

        windows = find_matching_windows(
            identity,
            list_top_level_windows=lambda: (101, 102, 103),
            is_window=lambda _: True,
            is_window_visible=lambda _: True,
            get_window_owner=lambda _: 0,
            get_window_process_id=lambda handle: {
                101: 5001,
                102: 5002,
                103: 5003,
            }[handle],
            get_process_image_path=lambda process_id: process_paths[
                process_id
            ],
            get_process_aumid=lambda _: None,
        )

        self.assertEqual(windows, (101,))

    def test_builds_exact_executable_identity(self):
        identity = build_window_app_identity(
            self._chrome_app(),
            resolve_launch_target=lambda _: self._chrome_target(),
        )

        self.assertIsNotNone(identity)
        self.assertEqual(
            identity.display_name,
            "Google Chrome",
        )
        self.assertEqual(
            identity.executable_path,
            (
                r"c:\program files\google\chrome\application"
                r"\chrome.exe"
            ),
        )
        self.assertIsNone(identity.app_user_model_id)

    def test_builds_exact_packaged_aumid_identity(self):
        calculator = CatalogApp(
            display_name="Calculator",
            normalized_name="calculator",
            launch_path=None,
            source=PACKAGED_APP_SOURCE,
            app_user_model_id=(
                "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"
            ),
        )

        identity = build_window_app_identity(calculator)

        self.assertIsNotNone(identity)
        self.assertIsNone(identity.executable_path)
        self.assertEqual(
            identity.app_user_model_id,
            "microsoft.windowscalculator_8wekyb3d8bbwe!app",
        )

    def test_performs_each_allowlisted_state_action(self):
        cases = {
            "minimize": (
                win32con.SW_MINIMIZE,
                "Minimized Google Chrome, sir.",
            ),
            "maximize": (
                win32con.SW_MAXIMIZE,
                "Maximized Google Chrome, sir.",
            ),
            "restore": (
                win32con.SW_RESTORE,
                "Restored Google Chrome, sir.",
            ),
        }

        for action, (command, expected_message) in cases.items():
            with self.subTest(action=action):
                show_calls: list[tuple[int, int]] = []

                result = self._control_chrome(
                    action,
                    show_window=lambda handle, show_command: (
                        show_calls.append(
                            (handle, show_command)
                        )
                        or 1
                    ),
                )

                self.assertTrue(result.success)
                self.assertEqual(
                    result.message,
                    expected_message,
                )
                self.assertEqual(
                    show_calls,
                    [(101, command)],
                )

    def test_ignores_invalid_invisible_and_owned_windows(self):
        show_calls: list[tuple[int, int]] = []

        result = self._control_chrome(
            "minimize",
            handles=(10, 20, 30, 40),
            valid_handles={20, 30, 40},
            visible_handles={30, 40},
            owned_handles={30},
            window_processes={40: 9004},
            process_paths={
                9004: self._chrome_target().target_path,
            },
            show_window=lambda handle, command: (
                show_calls.append((handle, command))
                or 1
            ),
        )

        self.assertTrue(result.success)
        self.assertEqual(
            show_calls,
            [(40, win32con.SW_MINIMIZE)],
        )

    def test_refuses_to_guess_when_multiple_windows_match(self):
        def forbidden_show_window(_: int, __: int) -> int:
            self.fail(
                "Ambiguous windows must not reach ShowWindow."
            )

        result = self._control_chrome(
            "maximize",
            handles=(101, 102),
            window_processes={
                101: 5001,
                102: 5002,
            },
            process_paths={
                5001: self._chrome_target().target_path,
                5002: self._chrome_target().target_path,
            },
            show_window=forbidden_show_window,
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            (
                "I found 2 Google Chrome windows. I will not "
                "guess which one to maximize, sir."
            ),
        )

    def test_reports_when_app_is_not_open(self):
        result = self._control_chrome(
            "restore",
            handles=(),
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "Google Chrome is not currently open, sir.",
        )

    def test_rejects_unknown_action_before_window_enumeration(self):
        def forbidden_windows() -> tuple[int, ...]:
            self.fail(
                "Unsupported actions must not enumerate windows."
            )

        result = control_named_window(
            self._chrome_app(),
            "close",
            list_top_level_windows=forbidden_windows,
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "I cannot perform that named-window action, sir.",
        )

    def test_matches_packaged_app_by_exact_aumid(self):
        calculator = CatalogApp(
            display_name="Calculator",
            normalized_name="calculator",
            launch_path=None,
            source=PACKAGED_APP_SOURCE,
            app_user_model_id=(
                "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"
            ),
        )
        show_calls: list[tuple[int, int]] = []

        result = control_named_window(
            calculator,
            "maximize",
            list_top_level_windows=lambda: (700,),
            is_window=lambda _: True,
            is_window_visible=lambda _: True,
            get_window_owner=lambda _: 0,
            get_window_process_id=lambda _: 42,
            get_process_image_path=lambda _: None,
            get_process_aumid=lambda _: (
                "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"
            ),
            show_window=lambda handle, command: (
                show_calls.append((handle, command))
                or 1
            ),
        )

        self.assertTrue(result.success)
        self.assertEqual(
            show_calls,
            [(700, win32con.SW_MAXIMIZE)],
        )

    def test_brings_minimized_window_to_foreground(self):
        show_calls: list[tuple[int, int]] = []
        foreground_calls: list[int] = []

        result = self._control_chrome(
            "bring_up",
            iconic_handles={101},
            show_window=lambda handle, command: (
                show_calls.append((handle, command))
                or 1
            ),
            set_foreground_window=lambda handle: (
                foreground_calls.append(handle)
                or True
            ),
        )

        self.assertTrue(result.success)
        self.assertEqual(
            result.message,
            "Brought Google Chrome to the foreground, sir.",
        )
        self.assertEqual(
            show_calls,
            [(101, win32con.SW_RESTORE)],
        )
        self.assertEqual(foreground_calls, [101])

    def test_reports_foreground_denial_without_simulating_input(self):
        foreground_calls: list[int] = []

        result = self._control_chrome(
            "bring_up",
            set_foreground_window=lambda handle: (
                foreground_calls.append(handle)
                or False
            ),
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            (
                "Windows would not bring Google Chrome to the "
                "foreground, sir."
            ),
        )
        self.assertEqual(foreground_calls, [101])

    def test_sends_close_request_to_one_exact_window(self):
        close_calls: list[int] = []

        result = self._close_chrome(
            False,
            post_close_message=lambda handle: (
                close_calls.append(handle)
            ),
        )

        self.assertTrue(result.success)
        self.assertEqual(
            result.message,
            "Sent a close request to Google Chrome, sir.",
        )
        self.assertEqual(close_calls, [101])

    def test_refuses_single_close_when_multiple_windows_match(self):
        def forbidden_close(_: int) -> None:
            self.fail(
                "Ambiguous single-window close must not send WM_CLOSE."
            )

        result = self._close_chrome(
            False,
            handles=(101, 102),
            window_processes={
                101: 5001,
                102: 5002,
            },
            process_paths={
                5001: self._chrome_target().target_path,
                5002: self._chrome_target().target_path,
            },
            post_close_message=forbidden_close,
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            (
                "I found 2 Google Chrome windows. I will not "
                "guess which one to close, sir."
            ),
        )

    def test_sends_close_requests_to_all_exact_windows(self):
        close_calls: list[int] = []

        result = self._close_chrome(
            True,
            handles=(101, 102),
            window_processes={
                101: 5001,
                102: 5002,
            },
            process_paths={
                5001: self._chrome_target().target_path,
                5002: self._chrome_target().target_path,
            },
            post_close_message=lambda handle: (
                close_calls.append(handle)
            ),
        )

        self.assertTrue(result.success)
        self.assertEqual(
            result.message,
            (
                "Sent close requests to 2 Google Chrome windows, sir."
            ),
        )
        self.assertEqual(close_calls, [101, 102])

    def test_reports_partial_close_request_failure(self):
        close_calls: list[int] = []

        def fail_on_second_window(window_handle: int) -> None:
            close_calls.append(window_handle)

            if window_handle == 102:
                raise OSError("Windows rejected the request.")

        result = self._close_chrome(
            True,
            handles=(101, 102),
            window_processes={
                101: 5001,
                102: 5002,
            },
            process_paths={
                5001: self._chrome_target().target_path,
                5002: self._chrome_target().target_path,
            },
            post_close_message=fail_on_second_window,
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            (
                "I sent close requests to 1 of 2 Google Chrome "
                "windows before Windows rejected the rest, sir."
            ),
        )
        self.assertEqual(close_calls, [101, 102])

    def test_handles_windows_api_failure_safely(self):
        def failing_show_window(_: int, __: int) -> int:
            raise OSError("Windows rejected the request.")

        result = self._control_chrome(
            "minimize",
            show_window=failing_show_window,
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "I could not minimize Google Chrome, sir.",
        )