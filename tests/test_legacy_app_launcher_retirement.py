from __future__ import annotations

import unittest
from unittest.mock import patch

from skills.app_launcher import LaunchResult


class LegacyAppLauncherRetirementTests(unittest.TestCase):
    def test_legacy_open_tag_is_not_executed(self):
        from automation.commands import execute_command

        with patch(
            "core.brain.chat_history",
            [{"content": "open steam"}],
        ):
            result = execute_command("<OPEN: Steam>", {})

        self.assertIsNone(result)

    def test_discord_macro_uses_catalog_launcher(self):
        from automation.commands import execute_command

        launch_result = LaunchResult(
            success=True,
            display_name="Discord",
            message="Opening Discord, sir.",
        )

        with (
            patch(
                "core.brain.chat_history",
                [{"content": "join music channel in discord"}],
            ),
            patch(
                "automation.commands.gw.getWindowsWithTitle",
                return_value=[],
            ),
            patch(
                "automation.commands.launch_catalog_app",
                return_value=launch_result,
            ) as launch_app,
            patch("automation.commands.time.sleep"),
            patch("automation.commands.pyautogui.hotkey"),
            patch("automation.commands.pyautogui.write"),
            patch("automation.commands.pyautogui.press"),
        ):
            result = execute_command("<CMD: JOIN_DISCORD>", {})

        launch_app.assert_called_once_with("Discord")
        self.assertEqual(
            result,
            "Joining the Music voice channel, sir.",
        )