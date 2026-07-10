from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skills import app_launcher
from skills.app_catalog import (
    APP_PATHS_SOURCE,
    PACKAGED_APP_SOURCE,
    START_MENU_SOURCE,
    normalise_name,
)
from skills.app_catalog_inspector import (
    build_catalog_report,
    build_supported_controls_guide,
    format_catalog_search_result,
    search_catalog,
    write_catalog_report,
    build_app_controls_guide,
)


def make_app(
    display_name: str,
    source: str,
):
    """Build a minimal catalog-like object for read-only unit tests."""
    return SimpleNamespace(
        display_name=display_name,
        normalized_name=normalise_name(display_name),
        source=source,
        launch_path=None,
        app_user_model_id=None,
    )


class AppCatalogInspectorTests(unittest.TestCase):
    def setUp(self):
        self.catalog = (
            make_app("Google Chrome", START_MENU_SOURCE),
            make_app("chrome", APP_PATHS_SOURCE),
            make_app("Calculator", PACKAGED_APP_SOURCE),
            make_app("Visual Studio Code", START_MENU_SOURCE),
        )
        self.aliases = {
            "chrome browser": "Google Chrome",
            "vscode": "Visual Studio Code",
        }

    def test_build_catalog_report_groups_sources_and_aliases(self):
        report = build_catalog_report(
            self.catalog,
            self.aliases,
        )

        self.assertEqual(report.entry_count, 4)
        self.assertEqual(report.alias_count, 2)
        self.assertIn("[Start Menu] (2)", report.text)
        self.assertIn("[App Paths] (1)", report.text)
        self.assertIn("[Packaged Apps] (1)", report.text)
        self.assertIn(
            "- chrome browser -> Google Chrome",
            report.text,
        )
        self.assertIn(
            "- vscode -> Visual Studio Code",
            report.text,
        )

    def test_write_catalog_report_creates_parent_directory(self):
        report = build_catalog_report(
            self.catalog,
            self.aliases,
        )

        with TemporaryDirectory() as temporary_directory:
            output_path = (
                Path(temporary_directory)
                / "reports"
                / "app_catalog_report.txt"
            )

            written_path = write_catalog_report(
                report,
                output_path,
            )

            self.assertEqual(written_path, output_path)
            self.assertTrue(output_path.is_file())
            self.assertIn(
                "Avens Local App Catalog",
                output_path.read_text(encoding="utf-8"),
            )

    def test_search_catalog_matches_apps_and_aliases(self):
        result = search_catalog(
            "visual studio",
            self.catalog,
            self.aliases,
        )

        self.assertEqual(result.query, "visual studio")
        self.assertEqual(
            [app.display_name for app in result.apps],
            ["Visual Studio Code"],
        )
        self.assertEqual(
            result.aliases,
            (("vscode", "visual studio code"),),
        )

    def test_format_catalog_search_result_includes_sources(self):
        result = search_catalog(
            "chrome",
            self.catalog,
            self.aliases,
        )

        formatted = format_catalog_search_result(result)

        self.assertIn("Google Chrome | Start Menu", formatted)
        self.assertIn("chrome | App Paths", formatted)
        self.assertIn(
            "chrome browser -> Google Chrome",
            formatted,
        )

    def test_supported_controls_guide_lists_close_confirmation(self):
        guide = build_supported_controls_guide()

        self.assertIn("Open <app>", guide)
        self.assertIn("Confirm close <app>", guide)
        self.assertIn("Search apps <text>", guide)
        self.assertIn("Take a note <text>", guide)
        self.assertIn("Confirm delete note <id>", guide)
        self.assertIn("Local reminders:", guide)
        self.assertIn(
            "Set or start a timer for <duration>",
            guide,
        )
        self.assertIn(
            "Remind me tomorrow at <time> to <task>",
            guide,
        )
        self.assertIn(
            "Confirm cancel reminder <id>",
            guide,
        )
        self.assertIn("Set volume to <0-100>", guide)
        self.assertIn("Set brightness to <10-100>", guide)
        self.assertIn("Open Night Light settings", guide)
        self.assertIn("Local file discovery:", guide)
        self.assertIn("Find file <terms>", guide)
        self.assertIn(
            "What files can you search?",
            guide,
        )
        self.assertIn("NitroSense gaming profile:", guide)
        self.assertIn("Set NitroSense gaming profile", guide)
        self.assertIn("Max out NitroSense fans", guide)
        self.assertIn(
            "Requires confirmation before changing laptop performance or fans.",
            guide,
        )
        self.assertIn("Local routines:", guide)
        self.assertIn("What routines do you have?", guide)
        self.assertIn("What does study mode do?", guide)
        self.assertIn("Local routines:", guide)
        self.assertIn("What routines do you have?", guide)
        self.assertIn("What does study mode do?", guide)
        self.assertIn("Start study mode", guide)
        self.assertIn("Start gaming mode", guide)
        self.assertIn(
            "URL groups open only from private approved config.",
            guide,
        )

    def test_app_controls_guide_uses_the_catalog_display_name(self):
        guide = build_app_controls_guide(self.catalog[0])

        self.assertIn("Controls for Google Chrome", guide)
        self.assertIn("Minimize Google Chrome", guide)
        self.assertIn("Confirm close Google Chrome", guide)
        self.assertIn(
            "Confirm close all Google Chrome windows",
            guide,
        )

    def test_catalog_snapshot_reuses_cached_catalog_sources(self):
        regular_catalog = (
            make_app("Google Chrome", START_MENU_SOURCE),
        )
        packaged_catalog = (
            make_app("Calculator", PACKAGED_APP_SOURCE),
        )

        with patch.object(
            app_launcher,
            "_get_regular_catalog",
            return_value=regular_catalog,
        ), patch.object(
            app_launcher,
            "_get_packaged_catalog",
            return_value=packaged_catalog,
        ) as get_packaged_catalog:
            snapshot = app_launcher.get_catalog_snapshot()

        self.assertEqual(
            [app.display_name for app in snapshot],
            ["Calculator", "Google Chrome"],
        )
        get_packaged_catalog.assert_called_once_with(
            frozenset({"google chrome"})
        )