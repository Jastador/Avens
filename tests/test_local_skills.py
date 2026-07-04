from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from skills.app_launcher import (
    LaunchResult,
    find_approved_app,
    find_approved_shortcut,
    launch_approved_app,
)
from skills.router import (
    OPEN_APP_SKILL,
    route_local_skill,
)


class AppLauncherTests(unittest.TestCase):
    def test_recognises_only_exact_approved_aliases(self):
        self.assertEqual(
            find_approved_app("Discord").app_id,
            "discord",
        )
        self.assertEqual(
            find_approved_app("VS Code").app_id,
            "vscode",
        )
        self.assertEqual(
            find_approved_app("Google Chrome").app_id,
            "chrome",
        )
        self.assertIsNone(find_approved_app("Spotify"))

    def test_finds_only_exact_shortcut_name(self):
        app = find_approved_app("Discord")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            exact_shortcut = root / "Discord.lnk"
            unrelated_shortcut = root / "Discord Canary.lnk"

            exact_shortcut.touch()
            unrelated_shortcut.touch()

            found = find_approved_shortcut(
                app,
                shortcut_roots=(root,),
            )

        self.assertEqual(found.name, "Discord.lnk")

    def test_does_not_fuzzy_match_shortcut_names(self):
        app = find_approved_app("Discord")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "Discord Canary.lnk").touch()

            found = find_approved_shortcut(
                app,
                shortcut_roots=(root,),
            )

        self.assertIsNone(found)

    def test_launches_resolved_shortcut_without_shell(self):
        calls: list[str] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shortcut = root / "Google Chrome.lnk"
            shortcut.touch()

            result = launch_approved_app(
                "chrome",
                shortcut_roots=(root,),
                startfile=calls.append,
            )

        self.assertTrue(result.success)
        self.assertEqual(calls, [str(shortcut)])
        self.assertEqual(
            result.message,
            "Opening Google Chrome, sir.",
        )

    def test_reports_missing_approved_shortcut(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = launch_approved_app(
                "discord",
                shortcut_roots=(Path(temp_dir),),
                startfile=lambda _: None,
            )

        self.assertFalse(result.success)
        self.assertIn("could not find", result.message)


class LocalSkillsRouterTests(unittest.TestCase):
    def test_open_app_skill_is_explicit_and_local(self):
        self.assertEqual(OPEN_APP_SKILL.name, "open_app")
        self.assertTrue(OPEN_APP_SKILL.offline)
        self.assertFalse(OPEN_APP_SKILL.requires_confirmation)
        self.assertEqual(
            OPEN_APP_SKILL.allowed_arguments,
            ("discord", "vscode", "chrome"),
        )

    def test_routes_an_approved_launch_request(self):
        launched_ids: list[str] = []

        def fake_launch(app_id: str) -> LaunchResult:
            launched_ids.append(app_id)

            return LaunchResult(
                success=True,
                app_id=app_id,
                message="Opening Discord, sir.",
            )

        result = route_local_skill(
            "Could you please launch Discord?",
            launch_app=fake_launch,
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertEqual(result.skill_name, "open_app")
        self.assertEqual(launched_ids, ["discord"])
        self.assertEqual(result.message, "Opening Discord, sir.")

    def test_routes_common_stt_connector_prefix(self):
        launched_ids: list[str] = []

        def fake_launch(app_id: str) -> LaunchResult:
            launched_ids.append(app_id)

            return LaunchResult(
                success=True,
                app_id=app_id,
                message="Opening Google Chrome, sir.",
            )

        result = route_local_skill(
            "or start Google Chrome.",
            launch_app=fake_launch,
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertEqual(result.skill_name, "open_app")
        self.assertEqual(launched_ids, ["chrome"])
        self.assertEqual(
            result.message,
            "Opening Google Chrome, sir.",
        )

    def test_unknown_apps_do_not_call_launcher(self):
        def forbidden_launch(_: str) -> LaunchResult:
            self.fail("Unknown apps must never reach the launcher.")

        result = route_local_skill(
            "Open Spotify",
            launch_app=forbidden_launch,
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertEqual(result.skill_name, "open_app")
        self.assertIn(
            "not in my approved local app list",
            result.message.lower(),
        )

    def test_ignores_non_launch_requests(self):
        result = route_local_skill("What time is it?")

        self.assertIsNone(result)