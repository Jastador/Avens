from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills.app_aliases import (
    load_app_aliases,
    resolve_alias_target,
)
from skills.app_catalog import (
    CatalogApp,
    START_MENU_SOURCE,
    normalise_name,
)
from skills.app_launcher import resolve_catalog_matches


class AppAliasesTests(unittest.TestCase):
    def test_loads_normalised_aliases_from_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            alias_file = Path(temp_dir) / "app_aliases.json"
            alias_file.write_text(
                json.dumps(
                    {
                        " VS-Code ": "Visual Studio Code",
                        "7zip": "7-Zip File Manager",
                        "7 Zip": "7-Zip File Manager",
                        "Seven Zip": "7-Zip File Manager",
                        "same": "same",
                        "invalid": 42,
                    }
                ),
                encoding="utf-8",
            )

            aliases = load_app_aliases(alias_file)

        self.assertEqual(
            aliases,
            {
                "vs code": "visual studio code",
                "7zip": "7 zip file manager",
                "7 zip": "7 zip file manager",
                "seven zip": "7 zip file manager",
            }
        )

    def test_ignores_missing_or_invalid_alias_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_file = Path(temp_dir) / "missing.json"
            invalid_file = Path(temp_dir) / "invalid.json"
            invalid_file.write_text(
                "{not valid json",
                encoding="utf-8",
            )

            self.assertEqual(
                load_app_aliases(missing_file),
                {},
            )
            self.assertEqual(
                load_app_aliases(invalid_file),
                {},
            )

    def test_resolves_configured_alias_target(self):
        self.assertEqual(
            resolve_alias_target(
                "VS Code",
                aliases={
                    "vs code": "Visual Studio Code",
                },
            ),
            "visual studio code",
        )

    def test_direct_catalog_match_beats_alias(self):
        direct_app = CatalogApp(
            display_name="Chrome",
            normalized_name="chrome",
            launch_path=Path("chrome.exe"),
            source=START_MENU_SOURCE,
        )
        alias_target = CatalogApp(
            display_name="Google Chrome",
            normalized_name="google chrome",
            launch_path=Path("Google Chrome.lnk"),
            source=START_MENU_SOURCE,
        )

        with patch(
            "skills.app_aliases.load_app_aliases",
            return_value={
                "chrome": "google chrome",
            },
        ):
            matches = resolve_catalog_matches(
                "Chrome",
                catalog=(direct_app, alias_target),
            )

        self.assertEqual(matches, (direct_app,))

    def test_alias_must_resolve_to_live_catalog_entry(self):
        app = CatalogApp(
            display_name="Visual Studio Code",
            normalized_name=normalise_name(
                "Visual Studio Code"
            ),
            launch_path=Path("Visual Studio Code.lnk"),
            source=START_MENU_SOURCE,
        )

        with patch(
            "skills.app_aliases.load_app_aliases",
            return_value={
                "work code": "visual studio code",
                "music": "spotify",
            },
        ):
            work_code_matches = resolve_catalog_matches(
                "work code",
                catalog=(app,),
            )
            music_matches = resolve_catalog_matches(
                "music",
                catalog=(app,),
            )

        self.assertEqual(work_code_matches, (app,))
        self.assertEqual(music_matches, ())


if __name__ == "__main__":
    unittest.main()