from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from skills.active_window import ActiveWindowResult
from skills.close_confirmation import CloseConfirmationStore
from skills.named_window import (
    NamedWindowMatchResult,
    NamedWindowResult,
)
from skills.app_catalog import (
    APP_PATHS_SOURCE,
    START_MENU_SOURCE,
    AppPathRegistration,
    CatalogApp,
    LaunchTarget,
    collapse_equivalent_catalog_apps,
    find_exact_matches,
    normalise_name,
    resolve_catalog_launch_target,
    scan_app_paths,
    scan_local_app_catalog,
    scan_start_menu_shortcuts,
)

from skills.app_launcher import (
    LaunchResult,
    launch_catalog_app,
    resolve_catalog_matches,
)
from skills.router import (
    ACTIVE_WINDOW_CONTROL_SKILL,
    NAMED_WINDOW_CLOSE_SKILL,
    NAMED_WINDOW_CONTROL_SKILL,
    OPEN_APP_SKILL,
    REFRESH_APP_CATALOG_SKILL,
    route_local_skill,
)

class AppCatalogTests(unittest.TestCase):
    def test_normalises_names_without_fuzzy_matching(self):
        self.assertEqual(
            normalise_name("Visual-Studio Code!"),
            "visual studio code",
        )
        self.assertEqual(
            normalise_name("  Google   Chrome  "),
            "google chrome",
        )

    def test_scans_only_shortcuts_and_keeps_display_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested_folder = root / "Tools"
            nested_folder.mkdir()

            (root / "ignore-me.txt").touch()
            shortcut = nested_folder / "OBS Studio.lnk"
            shortcut.touch()

            catalog = scan_start_menu_shortcuts(
                shortcut_roots=(root,),
            )

        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0].display_name, "OBS Studio")
        self.assertEqual(catalog[0].normalized_name, "obs studio")
        self.assertEqual(catalog[0].launch_path, shortcut)

    def test_preserves_duplicate_shortcut_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_folder = root / "First"
            second_folder = root / "Second"
            first_folder.mkdir()
            second_folder.mkdir()

            first_shortcut = first_folder / "Steam.lnk"
            second_shortcut = second_folder / "Steam.lnk"
            first_shortcut.touch()
            second_shortcut.touch()

            catalog = scan_start_menu_shortcuts(
                shortcut_roots=(root,),
            )
            matches = find_exact_matches("Steam", catalog)

        self.assertEqual(len(matches), 2)
        self.assertEqual(
            {match.launch_path.name for match in matches},
            {"Steam.lnk"},
        )

    def test_returns_only_exact_normalised_matches(self):
        app = CatalogApp(
            display_name="Visual Studio Code",
            normalized_name="visual studio code",
            launch_path=Path("Visual Studio Code.lnk"),
        )

        self.assertEqual(
            find_exact_matches("visual studio code", (app,)),
            (app,),
        )
        self.assertEqual(
            find_exact_matches("visual studio", (app,)),
            (),
        )

    def test_collapses_shortcuts_with_same_launch_target(self):
        first_app = CatalogApp(
            display_name="Steam",
            normalized_name="steam",
            launch_path=Path("ProgramData Steam.lnk"),
        )
        second_app = CatalogApp(
            display_name="Steam",
            normalized_name="steam",
            launch_path=Path("AppData Steam.lnk"),
        )

        targets = {
            first_app.launch_path: LaunchTarget(
                target_path=r"G:\Games\Launchers\Steam\Steam.exe",
                arguments="",
                working_directory=r"G:\Games\Launchers\Steam",
            ),
            second_app.launch_path: LaunchTarget(
                target_path=r"g:\games\launchers\steam\steam.exe",
                arguments="",
                working_directory=r"g:\games\launchers\steam",
            ),
        }

        collapsed = collapse_equivalent_catalog_apps(
            (first_app, second_app),
            resolve_target=lambda app: targets.get(app.launch_path),
        )

        self.assertEqual(collapsed, (first_app,))

    def test_keeps_shortcuts_separate_when_arguments_differ(self):
        first_app = CatalogApp(
            display_name="Launcher",
            normalized_name="launcher",
            launch_path=Path("Normal Launcher.lnk"),
        )
        second_app = CatalogApp(
            display_name="Launcher",
            normalized_name="launcher",
            launch_path=Path("Safe Mode Launcher.lnk"),
        )

        targets = {
            first_app.launch_path: LaunchTarget(
                target_path=r"C:\Tools\Launcher.exe",
                arguments="",
                working_directory=r"C:\Tools",
            ),
            second_app.launch_path: LaunchTarget(
                target_path=r"C:\Tools\Launcher.exe",
                arguments="--safe-mode",
                working_directory=r"C:\Tools",
            ),
        }

        collapsed = collapse_equivalent_catalog_apps(
            (first_app, second_app),
            resolve_target=lambda app: targets.get(app.launch_path),
        )

        self.assertEqual(
            collapsed,
            (first_app, second_app),
        )

    def test_scans_valid_app_paths_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "Player.exe"
            executable.touch()

            catalog = scan_app_paths(
                registrations=(
                    AppPathRegistration(
                        executable_name="Player.exe",
                        raw_target=str(executable),
                    ),
                )
            )

        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0].display_name, "Player")
        self.assertEqual(catalog[0].source, APP_PATHS_SOURCE)
        self.assertEqual(
            catalog[0].launch_path,
            executable.resolve(),
        )

    def test_ignores_unsafe_or_invalid_app_paths_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "Player.exe"
            executable.touch()
            missing_executable = Path(temp_dir) / "Missing.exe"

            catalog = scan_app_paths(
                registrations=(
                    AppPathRegistration(
                        executable_name="Player.exe",
                        raw_target=f'"{executable}" --safe-mode',
                    ),
                    AppPathRegistration(
                        executable_name="Readme.txt",
                        raw_target=str(executable),
                    ),
                    AppPathRegistration(
                        executable_name="Missing.exe",
                        raw_target=str(missing_executable),
                    ),
                )
            )

        self.assertEqual(catalog, ())

    def test_combines_start_menu_and_app_paths_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shortcut = root / "OBS Studio.lnk"
            executable = root / "Player.exe"

            shortcut.touch()
            executable.touch()

            catalog = scan_local_app_catalog(
                shortcut_roots=(root,),
                app_path_registrations=(
                    AppPathRegistration(
                        executable_name="Player.exe",
                        raw_target=str(executable),
                    ),
                ),
                include_packaged=False,
            )

        self.assertEqual(
            {app.display_name for app in catalog},
            {"OBS Studio", "Player"},
        )
        self.assertEqual(
            {app.source for app in catalog},
            {START_MENU_SOURCE, APP_PATHS_SOURCE},
        )

    def test_resolves_app_paths_entry_as_direct_launch_target(self):
        executable = Path(r"C:\Tools\Player.exe")

        app = CatalogApp(
            display_name="Player",
            normalized_name="player",
            launch_path=executable,
            source=APP_PATHS_SOURCE,
        )

        target = resolve_catalog_launch_target(app)

        self.assertEqual(
            target,
            LaunchTarget(
                target_path=str(executable),
                arguments="",
                working_directory="",
            ),
        )

    def test_collapses_app_paths_and_shortcut_with_same_launch_action(
        self,
    ):
        executable = Path(r"C:\Tools\Player.exe")

        app_paths_app = CatalogApp(
            display_name="Player",
            normalized_name="player",
            launch_path=executable,
            source=APP_PATHS_SOURCE,
        )
        shortcut_app = CatalogApp(
            display_name="Player",
            normalized_name="player",
            launch_path=Path("Player.lnk"),
            source=START_MENU_SOURCE,
        )

        targets = {
            app_paths_app: LaunchTarget(
                target_path=str(executable),
                arguments="",
                working_directory="",
            ),
            shortcut_app: LaunchTarget(
                target_path=str(executable),
                arguments="",
                working_directory="",
            ),
        }

        collapsed = collapse_equivalent_catalog_apps(
            (app_paths_app, shortcut_app),
            resolve_target=targets.get,
        )

        self.assertEqual(collapsed, (app_paths_app,))

class AppLauncherTests(unittest.TestCase):
    @staticmethod
    def _catalog_app(
        display_name: str,
        launch_path: Path,
        *,
        source: str = START_MENU_SOURCE,
    ) -> CatalogApp:
        return CatalogApp(
            display_name=display_name,
            normalized_name=normalise_name(display_name),
            launch_path=launch_path,
            source=source,
        )

    def test_resolves_known_alias_to_exact_catalog_entry(self):
        app = self._catalog_app(
            "Visual Studio Code",
            Path("Visual Studio Code.lnk"),
        )

        self.assertEqual(
            resolve_catalog_matches("VS Code", catalog=(app,)),
            (app,),
        )
        self.assertEqual(
            resolve_catalog_matches("vscode", catalog=(app,)),
            (app,),
        )

    def test_exact_catalog_match_beats_alias_fallback(self):
        app_paths_chrome = self._catalog_app(
            "Chrome",
            Path("chrome.exe"),
            source=APP_PATHS_SOURCE,
        )
        start_menu_chrome = self._catalog_app(
            "Google Chrome",
            Path("Google Chrome.lnk"),
        )

        self.assertEqual(
            resolve_catalog_matches(
                "Chrome",
                catalog=(
                    start_menu_chrome,
                    app_paths_chrome,
                ),
            ),
            (app_paths_chrome,),
        )

    def test_does_not_fuzzy_match_catalog_entries(self):
        app = self._catalog_app(
            "Visual Studio Code",
            Path("Visual Studio Code.lnk"),
        )

        self.assertEqual(
            resolve_catalog_matches("Visual Studio", catalog=(app,)),
            (),
        )

    def test_launches_one_exact_catalog_match_without_shell(self):
        calls: list[str] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            shortcut = Path(temp_dir) / "Spotify.lnk"
            shortcut.touch()

            app = self._catalog_app(
                "Spotify",
                shortcut,
                source=APP_PATHS_SOURCE,
            )

            result = launch_catalog_app(
                "Spotify",
                catalog=(app,),
                startfile=calls.append,
            )

        self.assertTrue(result.success)
        self.assertEqual(result.display_name, "Spotify")
        self.assertEqual(calls, [str(shortcut)])
        self.assertEqual(result.message, "Opening Spotify, sir.")

    def test_reports_missing_catalog_entry(self):
        def forbidden_launch(_: str) -> None:
            self.fail("Missing apps must never reach the launcher.")

        result = launch_catalog_app(
            "Spotify",
            catalog=(),
            startfile=forbidden_launch,
        )

        self.assertFalse(result.success)
        self.assertIn(
            "could not find an exact local app",
            result.message.lower(),
        )

    def test_refuses_ambiguous_catalog_entries(self):
        calls: list[str] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            first_shortcut = Path(temp_dir) / "First" / "Steam.lnk"
            second_shortcut = Path(temp_dir) / "Second" / "Steam.lnk"
            first_shortcut.parent.mkdir()
            second_shortcut.parent.mkdir()
            first_shortcut.touch()
            second_shortcut.touch()

            first_app = self._catalog_app("Steam", first_shortcut)
            second_app = self._catalog_app("Steam", second_shortcut)

            with patch(
                "skills.app_launcher.collapse_equivalent_catalog_apps",
                return_value=(first_app, second_app),
            ):
                result = launch_catalog_app(
                    "Steam",
                    catalog=(first_app, second_app),
                    startfile=calls.append,
                )

        self.assertFalse(result.success)
        self.assertEqual(calls, [])
        self.assertIn("will not guess", result.message.lower())

    def test_launches_collapsed_duplicate_catalog_entry(self):
        calls: list[str] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            first_shortcut = Path(temp_dir) / "First" / "Steam.lnk"
            second_shortcut = Path(temp_dir) / "Second" / "Steam.lnk"
            first_shortcut.parent.mkdir()
            second_shortcut.parent.mkdir()
            first_shortcut.touch()
            second_shortcut.touch()

            first_app = self._catalog_app("Steam", first_shortcut)
            second_app = self._catalog_app("Steam", second_shortcut)

            with patch(
                "skills.app_launcher.collapse_equivalent_catalog_apps",
                return_value=(first_app,),
            ) as collapse:
                result = launch_catalog_app(
                    "Steam",
                    catalog=(first_app, second_app),
                    startfile=calls.append,
                )

        collapse.assert_called_once_with((first_app, second_app))
        self.assertTrue(result.success)
        self.assertEqual(calls, [str(first_shortcut)])
        self.assertEqual(result.message, "Opening Steam, sir.")

class LocalSkillsRouterTests(unittest.TestCase):
    def test_active_window_control_skill_is_explicit_and_local(self):
        self.assertEqual(
            ACTIVE_WINDOW_CONTROL_SKILL.name,
            "control_active_window",
        )
        self.assertTrue(ACTIVE_WINDOW_CONTROL_SKILL.offline)
        self.assertFalse(
            ACTIVE_WINDOW_CONTROL_SKILL.requires_confirmation
        )
        self.assertEqual(
            ACTIVE_WINDOW_CONTROL_SKILL.allowed_arguments,
            (
                "minimize",
                "maximize",
                "restore",
            ),
        )

    def test_active_window_route_requires_literal_this(self):
        def forbidden_active_control(_: str) -> ActiveWindowResult:
            self.fail(
                "Non-focused-window commands must not use "
                "the active-window controller."
            )

        def forbidden_resolve(_: str) -> tuple[CatalogApp, ...]:
            self.fail(
                "Unsupported commands must not resolve named apps."
            )

        requests = (
            "Close this",
            "Make this fullscreen",
            "Bring Chrome up",
            "Minimize",
            "Restore",
        )

        for user_input in requests:
            with self.subTest(user_input=user_input):
                result = route_local_skill(
                    user_input,
                    control_window=forbidden_active_control,
                    resolve_app=forbidden_resolve,
                )

                self.assertIsNone(result)

    def test_routes_explicit_active_window_control_requests(self):
        control_calls: list[str] = []

        def fake_control(action: str) -> ActiveWindowResult:
            control_calls.append(action)

            return ActiveWindowResult(
                success=True,
                message=f"Handled {action}, sir.",
            )

        def forbidden_launch(_: str) -> LaunchResult:
            self.fail(
                "Focused-window commands must not reach app launching."
            )

        def forbidden_refresh() -> None:
            self.fail(
                "Focused-window commands must not refresh app catalogs."
            )

        def forbidden_resolve(_: str) -> tuple[CatalogApp, ...]:
            self.fail(
                "Focused-window commands must not resolve named apps."
            )

        cases = {
            "Minimize this": "minimize",
            "Maximize this.": "maximize",
            "Can you please restore this?": "restore",
            "Then maximize this please": "maximize",
        }

        for user_input, expected_action in cases.items():
            with self.subTest(user_input=user_input):
                result = route_local_skill(
                    user_input,
                    launch_app=forbidden_launch,
                    refresh_catalog=forbidden_refresh,
                    control_window=fake_control,
                    resolve_app=forbidden_resolve,
                )

                self.assertIsNotNone(result)
                self.assertTrue(result.handled)
                self.assertEqual(
                    result.skill_name,
                    ACTIVE_WINDOW_CONTROL_SKILL.name,
                )
                self.assertEqual(
                    result.message,
                    f"Handled {expected_action}, sir.",
                )

        self.assertEqual(
            control_calls,
            [
                "minimize",
                "maximize",
                "restore",
                "maximize",
            ],
        )

    def test_named_window_close_skill_requires_confirmation(self):
        self.assertEqual(
            NAMED_WINDOW_CLOSE_SKILL.name,
            "close_named_window",
        )
        self.assertTrue(NAMED_WINDOW_CLOSE_SKILL.offline)
        self.assertTrue(
            NAMED_WINDOW_CLOSE_SKILL.requires_confirmation
        )
        self.assertEqual(
            NAMED_WINDOW_CLOSE_SKILL.allowed_arguments,
            (
                "close",
                "close_all",
                "exact_catalog_app_name",
            ),
        )

    def test_close_request_requires_confirmation_before_wm_close(self):
        app = CatalogApp(
            display_name="Google Chrome",
            normalized_name="google chrome",
            launch_path=Path("chrome.exe"),
            source=APP_PATHS_SOURCE,
        )
        close_calls: list[tuple[CatalogApp, bool]] = []
        store = CloseConfirmationStore(
            clock=lambda: 100.0,
        )

        result = route_local_skill(
            "Close Chrome",
            resolve_app=lambda _: (app,),
            inspect_app_windows=lambda _: NamedWindowMatchResult(
                display_name="Google Chrome",
                window_handles=(101,),
                error_message=None,
            ),
            close_app_windows=lambda resolved_app, close_all: (
                close_calls.append((resolved_app, close_all))
                or NamedWindowResult(
                    success=True,
                    message="Should not run yet.",
                )
            ),
            close_confirmations=store,
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertEqual(
            result.skill_name,
            NAMED_WINDOW_CLOSE_SKILL.name,
        )
        self.assertEqual(
            result.message,
            (
                'I found 1 Google Chrome window. Say '
                '"Confirm close Chrome" to continue, sir.'
            ),
        )
        self.assertEqual(close_calls, [])

    def test_close_all_request_requires_confirmation(self):
        app = CatalogApp(
            display_name="Google Chrome",
            normalized_name="google chrome",
            launch_path=Path("chrome.exe"),
            source=APP_PATHS_SOURCE,
        )
        store = CloseConfirmationStore(
            clock=lambda: 100.0,
        )

        result = route_local_skill(
            "Close all Chrome windows",
            resolve_app=lambda _: (app,),
            inspect_app_windows=lambda _: NamedWindowMatchResult(
                display_name="Google Chrome",
                window_handles=(101, 102),
                error_message=None,
            ),
            close_confirmations=store,
        )

        self.assertIsNotNone(result)
        self.assertEqual(
            result.message,
            (
                'I found 2 Google Chrome windows. Say '
                '"Confirm close all Chrome windows" to continue, sir.'
            ),
        )

    def test_confirmation_rechecks_and_sends_named_close(self):
        app = CatalogApp(
            display_name="Google Chrome",
            normalized_name="google chrome",
            launch_path=Path("chrome.exe"),
            source=APP_PATHS_SOURCE,
        )
        close_calls: list[tuple[CatalogApp, bool]] = []
        store = CloseConfirmationStore(
            clock=lambda: 100.0,
        )

        first_result = route_local_skill(
            "Close Chrome",
            resolve_app=lambda _: (app,),
            inspect_app_windows=lambda _: NamedWindowMatchResult(
                display_name="Google Chrome",
                window_handles=(101,),
                error_message=None,
            ),
            close_confirmations=store,
        )

        self.assertIsNotNone(first_result)

        confirm_result = route_local_skill(
            "Confirm, close Chrome",
            resolve_app=lambda _: (app,),
            close_app_windows=lambda resolved_app, close_all: (
                close_calls.append((resolved_app, close_all))
                or NamedWindowResult(
                    success=True,
                    message=(
                        "Sent a close request to Google Chrome, sir."
                    ),
                )
            ),
            close_confirmations=store,
        )

        self.assertIsNotNone(confirm_result)
        self.assertEqual(
            confirm_result.message,
            "Sent a close request to Google Chrome, sir.",
        )
        self.assertEqual(close_calls, [(app, False)])

    def test_confirmation_rejects_bare_yes_and_mismatch(self):
        app = CatalogApp(
            display_name="Google Chrome",
            normalized_name="google chrome",
            launch_path=Path("chrome.exe"),
            source=APP_PATHS_SOURCE,
        )
        close_calls: list[tuple[CatalogApp, bool]] = []
        store = CloseConfirmationStore(
            clock=lambda: 100.0,
        )

        request_result = route_local_skill(
            "Close Chrome",
            resolve_app=lambda _: (app,),
            inspect_app_windows=lambda _: NamedWindowMatchResult(
                display_name="Google Chrome",
                window_handles=(101,),
                error_message=None,
            ),
            close_confirmations=store,
        )

        self.assertIsNotNone(request_result)

        bare_yes_result = route_local_skill(
            "Yes",
            close_app_windows=lambda resolved_app, close_all: (
                close_calls.append((resolved_app, close_all))
                or NamedWindowResult(
                    success=True,
                    message="Should not run.",
                )
            ),
            close_confirmations=store,
        )

        self.assertIsNone(bare_yes_result)
        self.assertEqual(close_calls, [])

        mismatch_result = route_local_skill(
            "Confirm close Notepad",
            close_confirmations=store,
        )

        self.assertIsNotNone(mismatch_result)
        self.assertEqual(
            mismatch_result.message,
            (
                "That confirmation did not match the pending close "
                "request, so I cancelled it, sir."
            ),
        )
        self.assertEqual(close_calls, [])

    def test_cancel_clears_pending_close_request(self):
        app = CatalogApp(
            display_name="Google Chrome",
            normalized_name="google chrome",
            launch_path=Path("chrome.exe"),
            source=APP_PATHS_SOURCE,
        )
        store = CloseConfirmationStore(
            clock=lambda: 100.0,
        )

        route_local_skill(
            "Close Chrome",
            resolve_app=lambda _: (app,),
            inspect_app_windows=lambda _: NamedWindowMatchResult(
                display_name="Google Chrome",
                window_handles=(101,),
                error_message=None,
            ),
            close_confirmations=store,
        )

        cancel_result = route_local_skill(
            "Cancel",
            close_confirmations=store,
        )

        self.assertIsNotNone(cancel_result)
        self.assertEqual(
            cancel_result.message,
            "Pending close request cancelled, sir.",
        )

        confirm_result = route_local_skill(
            "Confirm close Chrome",
            close_confirmations=store,
        )

        self.assertIsNotNone(confirm_result)
        self.assertEqual(
            confirm_result.message,
            "There is no pending close request to confirm, sir.",
        )

    def test_close_request_refuses_multiple_windows_without_all(self):
        app = CatalogApp(
            display_name="Google Chrome",
            normalized_name="google chrome",
            launch_path=Path("chrome.exe"),
            source=APP_PATHS_SOURCE,
        )
        store = CloseConfirmationStore(
            clock=lambda: 100.0,
        )

        result = route_local_skill(
            "Close Chrome",
            resolve_app=lambda _: (app,),
            inspect_app_windows=lambda _: NamedWindowMatchResult(
                display_name="Google Chrome",
                window_handles=(101, 102),
                error_message=None,
            ),
            close_confirmations=store,
        )

        self.assertIsNotNone(result)
        self.assertEqual(
            result.message,
            (
                "I found 2 Google Chrome windows. I will not guess "
                "which one to close, sir. Ask me to close all "
                "matching windows instead."
            ),
        )

    def test_named_window_control_skill_is_explicit_and_local(self):
        self.assertEqual(
            NAMED_WINDOW_CONTROL_SKILL.name,
            "control_named_window",
        )
        self.assertTrue(NAMED_WINDOW_CONTROL_SKILL.offline)
        self.assertFalse(
            NAMED_WINDOW_CONTROL_SKILL.requires_confirmation
        )
        self.assertEqual(
            NAMED_WINDOW_CONTROL_SKILL.allowed_arguments,
            (
                "minimize",
                "maximize",
                "restore",
                "bring_up",
                "exact_catalog_app_name",
            ),
        )

    def test_routes_explicit_named_window_control_requests(self):
        app = CatalogApp(
            display_name="Google Chrome",
            normalized_name="google chrome",
            launch_path=Path("chrome.exe"),
            source=APP_PATHS_SOURCE,
        )
        resolved_names: list[str] = []
        control_calls: list[tuple[CatalogApp, str]] = []

        def fake_resolve(
            requested_name: str,
        ) -> tuple[CatalogApp, ...]:
            resolved_names.append(requested_name)
            return (app,)

        def fake_control(
            resolved_app: CatalogApp,
            action: str,
        ) -> NamedWindowResult:
            control_calls.append((resolved_app, action))

            return NamedWindowResult(
                success=True,
                message=f"Handled {action}, sir.",
            )

        cases = {
            "Minimize Chrome": "minimize",
            "Maximize Chrome.": "maximize",
            "Can you please restore Chrome?": "restore",
            "Then bring up Chrome please": "bring_up",
        }

        for user_input, expected_action in cases.items():
            with self.subTest(user_input=user_input):
                result = route_local_skill(
                    user_input,
                    resolve_app=fake_resolve,
                    control_named_app_window=fake_control,
                )

                self.assertIsNotNone(result)
                self.assertTrue(result.handled)
                self.assertEqual(
                    result.skill_name,
                    NAMED_WINDOW_CONTROL_SKILL.name,
                )
                self.assertEqual(
                    result.message,
                    f"Handled {expected_action}, sir.",
                )

        self.assertEqual(
            resolved_names,
            [
                "Chrome",
                "Chrome",
                "Chrome",
                "Chrome",
            ],
        )
        self.assertEqual(
            control_calls,
            [
                (app, "minimize"),
                (app, "maximize"),
                (app, "restore"),
                (app, "bring_up"),
            ],
        )

    def test_named_window_route_refuses_missing_or_ambiguous_apps(self):
        app_one = CatalogApp(
            display_name="Google Chrome",
            normalized_name="google chrome",
            launch_path=Path("chrome-one.exe"),
            source=APP_PATHS_SOURCE,
        )
        app_two = CatalogApp(
            display_name="Google Chrome",
            normalized_name="google chrome",
            launch_path=Path("chrome-two.exe"),
            source=APP_PATHS_SOURCE,
        )

        def forbidden_control(
            _: CatalogApp,
            __: str,
        ) -> NamedWindowResult:
            self.fail(
                "Missing or ambiguous apps must not reach window control."
            )

        missing = route_local_skill(
            "Minimize Unknown App",
            resolve_app=lambda _: (),
            control_named_app_window=forbidden_control,
        )

        self.assertIsNotNone(missing)
        self.assertTrue(missing.handled)
        self.assertIn(
            "could not find an exact local app",
            missing.message.lower(),
        )

        ambiguous = route_local_skill(
            "Restore Chrome",
            resolve_app=lambda _: (app_one, app_two),
            control_named_app_window=forbidden_control,
        )

        self.assertIsNotNone(ambiguous)
        self.assertTrue(ambiguous.handled)
        self.assertEqual(
            ambiguous.message,
            (
                "I found 2 exact local apps named Google Chrome. "
                "I will not guess which one to control, sir."
            ),
        )

    def test_named_window_route_does_not_intercept_other_commands(self):
        def forbidden_resolve(_: str) -> tuple[CatalogApp, ...]:
            self.fail(
                "Non-matching commands must not resolve named apps."
            )

        def fake_active_control(action: str) -> ActiveWindowResult:
            return ActiveWindowResult(
                success=True,
                message=f"Focused {action}, sir.",
            )

        focused_result = route_local_skill(
            "Minimize this",
            control_window=fake_active_control,
            resolve_app=forbidden_resolve,
        )

        self.assertIsNotNone(focused_result)
        self.assertEqual(
            focused_result.skill_name,
            ACTIVE_WINDOW_CONTROL_SKILL.name,
        )

        for user_input in (
            "Show Chrome",
            "Bring Chrome up",
            "Make Chrome fullscreen",
        ):
            with self.subTest(user_input=user_input):
                result = route_local_skill(
                    user_input,
                    resolve_app=forbidden_resolve,
                )

                self.assertIsNone(result)

    def test_open_app_skill_is_explicit_and_local(self):
        self.assertEqual(OPEN_APP_SKILL.name, "open_app")
        self.assertTrue(OPEN_APP_SKILL.offline)
        self.assertFalse(OPEN_APP_SKILL.requires_confirmation)
        self.assertEqual(
            OPEN_APP_SKILL.allowed_arguments,
            ("exact_start_menu_app_name",),
        )

    def test_refresh_app_catalog_skill_is_explicit_and_local(self):
        self.assertEqual(
            REFRESH_APP_CATALOG_SKILL.name,
            "refresh_app_catalog",
        )
        self.assertTrue(REFRESH_APP_CATALOG_SKILL.offline)
        self.assertFalse(
            REFRESH_APP_CATALOG_SKILL.requires_confirmation
        )
        self.assertEqual(
            REFRESH_APP_CATALOG_SKILL.allowed_arguments,
            (),
        )

    def test_routes_explicit_app_catalog_refresh_requests(self):
        refresh_calls: list[None] = []

        def fake_refresh() -> None:
            refresh_calls.append(None)

        def forbidden_launch(_: str) -> LaunchResult:
            self.fail(
                "Refresh commands must not reach the app launcher."
            )

        commands = (
            "Refresh apps",
            "Refresh app list.",
            "Update app list",
            "Refresh the application catalog",
            "Can you please refresh the apps?",
        )

        for user_input in commands:
            with self.subTest(user_input=user_input):
                result = route_local_skill(
                    user_input,
                    launch_app=forbidden_launch,
                    refresh_catalog=fake_refresh,
                )

                self.assertIsNotNone(result)
                self.assertTrue(result.handled)
                self.assertEqual(
                    result.skill_name,
                    REFRESH_APP_CATALOG_SKILL.name,
                )
                self.assertEqual(
                    result.message,
                    "I refreshed the local app list, sir.",
                )

        self.assertEqual(
            len(refresh_calls),
            len(commands),
        )

    def test_ignores_non_app_refresh_requests(self):
        refresh_calls: list[None] = []

        def fake_refresh() -> None:
            refresh_calls.append(None)

        result = route_local_skill(
            "Refresh weather",
            refresh_catalog=fake_refresh,
        )

        self.assertIsNone(result)
        self.assertEqual(refresh_calls, [])

    def test_routes_an_explicit_launch_request(self):
        requested_names: list[str] = []

        def fake_launch(requested_name: str) -> LaunchResult:
            requested_names.append(requested_name)

            return LaunchResult(
                success=True,
                display_name="Discord",
                message="Opening Discord, sir.",
            )

        result = route_local_skill(
            "Could you please launch Discord?",
            launch_app=fake_launch,
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertEqual(result.skill_name, "open_app")
        self.assertEqual(requested_names, ["Discord"])
        self.assertEqual(result.message, "Opening Discord, sir.")

    def test_routes_launch_request_after_punctuation(self):
        requested_names: list[str] = []

        def fake_launch(requested_name: str) -> LaunchResult:
            requested_names.append(requested_name)

            return LaunchResult(
                success=True,
                display_name=requested_name,
                message=f"Opening {requested_name}, sir.",
            )

        cases = {
            "Open. Calculator": "Calculator",
            "Open: 7 Zip": "7 Zip",
            "Open, Discord": "Discord",
        }

        for user_input, expected_name in cases.items():
            with self.subTest(user_input=user_input):
                result = route_local_skill(
                    user_input,
                    launch_app=fake_launch,
                )

                self.assertIsNotNone(result)
                self.assertTrue(result.handled)
                self.assertEqual(
                    result.skill_name,
                    OPEN_APP_SKILL.name,
                )
                self.assertEqual(
                    result.message,
                    f"Opening {expected_name}, sir.",
                )

        self.assertEqual(
            requested_names,
            ["Calculator", "7 Zip", "Discord"],
        )

    def test_routes_punctuated_unknown_app_to_safe_launcher_result(self):
        requested_names: list[str] = []

        def fake_launch(requested_name: str) -> LaunchResult:
            requested_names.append(requested_name)

            return LaunchResult(
                success=False,
                display_name=requested_name,
                message=(
                    f"I could not find an exact local app named "
                    f"{requested_name}, sir."
                ),
            )

        result = route_local_skill(
            "Open. Seven.",
            launch_app=fake_launch,
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertEqual(
            requested_names,
            ["Seven"],
        )
        self.assertIn(
            "could not find an exact local app",
            result.message.lower(),
        )

    def test_routes_common_stt_connector_prefix(self):
        requested_names: list[str] = []

        def fake_launch(requested_name: str) -> LaunchResult:
            requested_names.append(requested_name)

            return LaunchResult(
                success=True,
                display_name="Google Chrome",
                message="Opening Google Chrome, sir.",
            )

        result = route_local_skill(
            "or start Google Chrome.",
            launch_app=fake_launch,
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertEqual(requested_names, ["Google Chrome"])
        self.assertEqual(
            result.message,
            "Opening Google Chrome, sir.",
        )

    def test_forwards_missing_app_name_to_catalog_launcher(self):
        requested_names: list[str] = []

        def fake_launch(requested_name: str) -> LaunchResult:
            requested_names.append(requested_name)

            return LaunchResult(
                success=False,
                display_name=requested_name,
                message=(
                    f"I could not find an exact local app named "
                    f"{requested_name}, sir."
                ),
            )

        result = route_local_skill(
            "Open Spotify",
            launch_app=fake_launch,
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertEqual(requested_names, ["Spotify"])
        self.assertIn(
            "could not find an exact local app",
            result.message.lower(),
        )

    def test_ignores_non_launch_requests(self):
        result = route_local_skill("What time is it?")

        self.assertIsNone(result)