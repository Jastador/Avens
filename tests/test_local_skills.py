from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from skills.app_catalog import (
    CatalogApp,
    ShortcutLaunchTarget,
    collapse_equivalent_shortcuts,
    find_exact_matches,
    normalise_name,
    scan_start_menu_shortcuts,
)

from skills.app_launcher import (
    LaunchResult,
    launch_catalog_app,
    resolve_catalog_matches,
)
from skills.router import (
    OPEN_APP_SKILL,
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
        self.assertEqual(catalog[0].shortcut_path, shortcut)

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
            {match.shortcut_path.name for match in matches},
            {"Steam.lnk"},
        )

    def test_returns_only_exact_normalised_matches(self):
        app = CatalogApp(
            display_name="Visual Studio Code",
            normalized_name="visual studio code",
            shortcut_path=Path("Visual Studio Code.lnk"),
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
            shortcut_path=Path("ProgramData Steam.lnk"),
        )
        second_app = CatalogApp(
            display_name="Steam",
            normalized_name="steam",
            shortcut_path=Path("AppData Steam.lnk"),
        )

        targets = {
            first_app.shortcut_path: ShortcutLaunchTarget(
                target_path=r"G:\Games\Launchers\Steam\Steam.exe",
                arguments="",
                working_directory=r"G:\Games\Launchers\Steam",
            ),
            second_app.shortcut_path: ShortcutLaunchTarget(
                target_path=r"g:\games\launchers\steam\steam.exe",
                arguments="",
                working_directory=r"g:\games\launchers\steam",
            ),
        }

        collapsed = collapse_equivalent_shortcuts(
            (first_app, second_app),
            resolve_target=targets.get,
        )

        self.assertEqual(collapsed, (first_app,))

    def test_keeps_shortcuts_separate_when_arguments_differ(self):
        first_app = CatalogApp(
            display_name="Launcher",
            normalized_name="launcher",
            shortcut_path=Path("Normal Launcher.lnk"),
        )
        second_app = CatalogApp(
            display_name="Launcher",
            normalized_name="launcher",
            shortcut_path=Path("Safe Mode Launcher.lnk"),
        )

        targets = {
            first_app.shortcut_path: ShortcutLaunchTarget(
                target_path=r"C:\Tools\Launcher.exe",
                arguments="",
                working_directory=r"C:\Tools",
            ),
            second_app.shortcut_path: ShortcutLaunchTarget(
                target_path=r"C:\Tools\Launcher.exe",
                arguments="--safe-mode",
                working_directory=r"C:\Tools",
            ),
        }

        collapsed = collapse_equivalent_shortcuts(
            (first_app, second_app),
            resolve_target=targets.get,
        )

        self.assertEqual(
            collapsed,
            (first_app, second_app),
        )

class AppLauncherTests(unittest.TestCase):
    @staticmethod
    def _catalog_app(
        display_name: str,
        shortcut_path: Path,
    ) -> CatalogApp:
        return CatalogApp(
            display_name=display_name,
            normalized_name=normalise_name(display_name),
            shortcut_path=shortcut_path,
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

            app = self._catalog_app("Spotify", shortcut)

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
            "could not find an exact start menu app",
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
                "skills.app_launcher.collapse_equivalent_shortcuts",
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
                "skills.app_launcher.collapse_equivalent_shortcuts",
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
    def test_open_app_skill_is_explicit_and_local(self):
        self.assertEqual(OPEN_APP_SKILL.name, "open_app")
        self.assertTrue(OPEN_APP_SKILL.offline)
        self.assertFalse(OPEN_APP_SKILL.requires_confirmation)
        self.assertEqual(
            OPEN_APP_SKILL.allowed_arguments,
            ("exact_start_menu_app_name",),
        )

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
                    f"I could not find an exact Start Menu app named "
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
            "could not find an exact start menu app",
            result.message.lower(),
        )

    def test_ignores_non_launch_requests(self):
        result = route_local_skill("What time is it?")

        self.assertIsNone(result)