from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from skills.app_catalog import (
    START_MENU_SOURCE,
    normalise_name,
)
from skills.router import route_local_skill


def make_app(
    display_name: str,
):
    """Build one minimal catalog-like object for router tests."""
    return SimpleNamespace(
        display_name=display_name,
        normalized_name=normalise_name(display_name),
        source=START_MENU_SOURCE,
        launch_path=None,
        app_user_model_id=None,
    )


class AppCatalogInspectorRouterTests(unittest.TestCase):
    def setUp(self):
        self.catalog = (
            make_app("Google Chrome"),
            make_app("Visual Studio Code"),
        )
        self.aliases = {
            "chrome browser": "Google Chrome",
            "vscode": "Visual Studio Code",
        }

    def test_list_apps_prints_and_writes_the_full_report(self):
        output = []

        with TemporaryDirectory() as temporary_directory:
            report_path = (
                Path(temporary_directory)
                / "reports"
                / "app_catalog_report.txt"
            )

            result = route_local_skill(
                "List apps",
                catalog_snapshot=lambda: self.catalog,
                get_aliases=lambda: self.aliases,
                console_output=output.append,
                catalog_report_path=report_path,
            )

            self.assertTrue(report_path.is_file())

        self.assertEqual(result.skill_name, "list_app_catalog")
        self.assertIn("Catalog entries: 2", "\n".join(output))
        self.assertIn(
            "Saved app catalog report:",
            "\n".join(output),
        )

    def test_search_apps_prints_catalog_and_alias_matches(self):
        output = []

        result = route_local_skill(
            "Search apps chrome",
            catalog_snapshot=lambda: self.catalog,
            get_aliases=lambda: self.aliases,
            console_output=output.append,
        )

        self.assertEqual(result.skill_name, "search_app_catalog")
        self.assertIn(
            'Catalog search: "chrome"',
            "\n".join(output),
        )
        self.assertIn("Google Chrome", "\n".join(output))
        self.assertIn(
            "chrome browser -> Google Chrome",
            "\n".join(output),
        )

    def test_what_can_i_control_prints_the_safe_guide(self):
        output = []

        result = route_local_skill(
            "What can I control?",
            console_output=output.append,
        )

        self.assertEqual(result.skill_name, "show_local_controls")
        self.assertIn(
            "Avens Safe Local Controls",
            "\n".join(output),
        )
        self.assertIn(
            "Confirm close <app>",
            "\n".join(output),
        )
        self.assertIn(
            "Set volume to <0-100>",
            "\n".join(output),
        )
        self.assertIn(
            "Start reading setup",
            "\n".join(output),
        )
        self.assertIn(
            "Local reminders:",
            "\n".join(output),
        )
        self.assertIn(
            "Set or start a timer for <duration>",
            "\n".join(output),
        )
        self.assertIn(
            "Confirm cancel reminder <id>",
            "\n".join(output),
        )

    def test_app_controls_resolve_an_alias_without_launching(self):
        output = []
        resolved_names = []

        def resolve_app(requested_name: str):
            resolved_names.append(requested_name)
            return (make_app("Visual Studio Code"),)

        result = route_local_skill(
            "What can I do with vscode?",
            resolve_app=resolve_app,
            console_output=output.append,
        )

        self.assertEqual(resolved_names, ["vscode"])
        self.assertEqual(result.skill_name, "show_app_controls")
        self.assertIn(
            "Controls for Visual Studio Code",
            "\n".join(output),
        )
        self.assertIn(
            "Confirm close Visual Studio Code",
            "\n".join(output),
        )

    def test_app_controls_refuse_an_unknown_app(self):
        result = route_local_skill(
            "What can I do with mystery app?",
            resolve_app=lambda _: (),
        )

        self.assertEqual(result.skill_name, "show_app_controls")
        self.assertIn(
            "could not find an exact local app",
            result.message,
        )