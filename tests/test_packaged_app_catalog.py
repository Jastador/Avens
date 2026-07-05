from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills.app_catalog import (
    APP_PATHS_SOURCE,
    PACKAGED_APP_SOURCE,
    START_MENU_SOURCE,
    AppPathRegistration,
    CatalogApp,
    LaunchTarget,
    PackagedAppRegistration,
    get_catalog_launch_reference,
    parse_packaged_app_registrations,
    resolve_catalog_launch_target,
    scan_local_app_catalog,
    scan_packaged_apps,
)
from skills.app_launcher import (
    launch_catalog_app,
    resolve_catalog_matches,
)


class PackagedAppCatalogTests(unittest.TestCase):
    def test_parses_packaged_app_json_records(self):
        payload = json.dumps(
            [
                {
                    "Name": "Calculator",
                    "AppID": (
                        "Microsoft.WindowsCalculator_8wekyb3d8bbwe"
                        "!App"
                    ),
                },
                {
                    "Name": "Camera",
                    "AppID": (
                        "Microsoft.WindowsCamera_8wekyb3d8bbwe"
                        "!App"
                    ),
                },
            ]
        )

        registrations = parse_packaged_app_registrations(payload)

        self.assertEqual(
            registrations,
            (
                PackagedAppRegistration(
                    display_name="Calculator",
                    app_user_model_id=(
                        "Microsoft.WindowsCalculator_8wekyb3d8bbwe"
                        "!App"
                    ),
                ),
                PackagedAppRegistration(
                    display_name="Camera",
                    app_user_model_id=(
                        "Microsoft.WindowsCamera_8wekyb3d8bbwe"
                        "!App"
                    ),
                ),
            ),
        )

    def test_ignores_invalid_packaged_app_entries(self):
        registrations = (
            PackagedAppRegistration(
                display_name="Calculator",
                app_user_model_id=(
                    "Microsoft.WindowsCalculator_8wekyb3d8bbwe"
                    "!App"
                ),
            ),
            PackagedAppRegistration(
                display_name="Broken",
                app_user_model_id="not-a-valid-aumid",
            ),
            PackagedAppRegistration(
                display_name="Command",
                app_user_model_id=(
                    "Microsoft.Command_8wekyb3d8bbwe"
                    "!App;calc.exe"
                ),
            ),
        )

        catalog = scan_packaged_apps(registrations)

        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0].display_name, "Calculator")
        self.assertEqual(
            catalog[0].source,
            PACKAGED_APP_SOURCE,
        )

    def test_excludes_packaged_name_already_covered_by_regular_sources(
        self,
    ):
        registration = PackagedAppRegistration(
            display_name="Notepad",
            app_user_model_id=(
                "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App"
            ),
        )

        catalog = scan_packaged_apps(
            (registration,),
            excluded_normalized_names={"notepad"},
        )

        self.assertEqual(catalog, ())

    def test_combines_uncovered_packaged_apps_with_regular_catalog(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shortcut = root / "Notepad.lnk"
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
                packaged_app_registrations=(
                    PackagedAppRegistration(
                        display_name="Notepad",
                        app_user_model_id=(
                            "Microsoft.WindowsNotepad_8wekyb3d8bbwe"
                            "!App"
                        ),
                    ),
                    PackagedAppRegistration(
                        display_name="Calculator",
                        app_user_model_id=(
                            "Microsoft.WindowsCalculator_8wekyb3d8bbwe"
                            "!App"
                        ),
                    ),
                ),
            )

        self.assertEqual(
            {app.display_name for app in catalog},
            {"Calculator", "Notepad", "Player"},
        )
        self.assertEqual(
            {app.source for app in catalog},
            {
                START_MENU_SOURCE,
                APP_PATHS_SOURCE,
                PACKAGED_APP_SOURCE,
            },
        )

    def test_builds_apps_folder_reference_for_packaged_app(self):
        app = CatalogApp(
            display_name="Calculator",
            normalized_name="calculator",
            launch_path=None,
            source=PACKAGED_APP_SOURCE,
            app_user_model_id=(
                "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"
            ),
        )

        self.assertEqual(
            get_catalog_launch_reference(app),
            (
                "shell:AppsFolder\\"
                "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"
            ),
        )
        self.assertEqual(
            resolve_catalog_launch_target(app),
            LaunchTarget(
                target_path=(
                    "shell:AppsFolder\\"
                    "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"
                ),
                arguments="",
                working_directory="",
            ),
        )

    def test_launches_packaged_app_without_command_shell(self):
        calls: list[str] = []
        app = CatalogApp(
            display_name="Calculator",
            normalized_name="calculator",
            launch_path=None,
            source=PACKAGED_APP_SOURCE,
            app_user_model_id=(
                "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"
            ),
        )

        result = launch_catalog_app(
            "Calculator",
            catalog=(app,),
            startfile=calls.append,
        )

        self.assertTrue(result.success)
        self.assertEqual(
            calls,
            [
                (
                    "shell:AppsFolder\\"
                    "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"
                )
            ],
        )
        self.assertEqual(
            result.message,
            "Opening Calculator, sir.",
        )

    def test_runtime_prefers_packaged_exact_match_before_alias(self):
        regular_catalog = (
            CatalogApp(
                display_name="Google Chrome",
                normalized_name="google chrome",
                launch_path=Path("Google Chrome.lnk"),
                source=START_MENU_SOURCE,
            ),
        )
        packaged_catalog = (
            CatalogApp(
                display_name="Chrome",
                normalized_name="chrome",
                launch_path=None,
                source=PACKAGED_APP_SOURCE,
                app_user_model_id=(
                    "Example.Chrome_8wekyb3d8bbwe!App"
                ),
            ),
        )

        with (
            patch(
                "skills.app_launcher.scan_local_app_catalog",
                return_value=regular_catalog,
            ),
            patch(
                "skills.app_launcher.scan_packaged_apps",
                return_value=packaged_catalog,
            ),
        ):
            matches = resolve_catalog_matches("Chrome")

        self.assertEqual(matches, packaged_catalog)


if __name__ == "__main__":
    unittest.main()