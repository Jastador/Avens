from __future__ import annotations

import unittest

from skills.app_launcher import LaunchResult
from skills.discord_voice_config import DiscordVoiceTarget
from skills.discord_voice_target_resolver import (
    DiscordVoiceTargetResolution,
)
from skills.router import route_local_skill


class DiscordVoiceRouterTests(unittest.TestCase):
    def test_routes_discord_voice_target_resolution(self):
        calls = []
        output = []

        def resolve_discord_voice_command(
            user_input: str,
        ) -> DiscordVoiceTargetResolution | None:
            calls.append(user_input)
            return DiscordVoiceTargetResolution(
                success=True,
                alias="controller",
                target=DiscordVoiceTarget(
                    alias="controller",
                    server_name="Test Server",
                    channel_name="Controller Voice",
                ),
                message=(
                    "Discord voice target resolved: server "
                    "'Test Server', channel 'Controller Voice'. "
                    "UI joining is not implemented yet, sir."
                ),
            )

        def forbidden_launch(_: str) -> LaunchResult:
            self.fail(
                "Discord voice commands must not reach app launching."
            )

        result = route_local_skill(
            "join controller voice",
            resolve_discord_voice_command=resolve_discord_voice_command,
            launch_app=forbidden_launch,
            console_output=output.append,
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertEqual(
            result.skill_name,
            "resolve_discord_voice_target",
        )
        self.assertEqual(
            result.message,
            "Discord voice target resolved: server 'Test Server', "
            "channel 'Controller Voice'. UI joining is not "
            "implemented yet, sir.",
        )
        self.assertTrue(result.offline)
        self.assertFalse(result.requires_confirmation)
        self.assertEqual(calls, ["join controller voice"])
        self.assertEqual(output, [result.message])

    def test_routes_unknown_discord_voice_target_failure(self):
        def resolve_discord_voice_command(
            user_input: str,
        ) -> DiscordVoiceTargetResolution | None:
            return DiscordVoiceTargetResolution(
                success=False,
                alias="music",
                target=None,
                message=(
                    "No Discord voice target configured for 'music'."
                ),
            )

        result = route_local_skill(
            "join music voice",
            resolve_discord_voice_command=resolve_discord_voice_command,
            launch_app=lambda _: self.fail(
                "Unknown Discord voice targets must not launch apps."
            ),
            console_output=lambda _: None,
        )

        self.assertIsNotNone(result)
        self.assertTrue(result.handled)
        self.assertEqual(
            result.skill_name,
            "resolve_discord_voice_target",
        )
        self.assertEqual(
            result.message,
            "No Discord voice target configured for 'music'.",
        )
        self.assertTrue(result.offline)
        self.assertFalse(result.requires_confirmation)

    def test_open_controller_voice_does_not_route_to_app_launcher(self):
        calls = []

        def resolve_discord_voice_command(
            user_input: str,
        ) -> DiscordVoiceTargetResolution | None:
            calls.append(("discord", user_input))
            return DiscordVoiceTargetResolution(
                success=True,
                alias="controller",
                target=DiscordVoiceTarget(
                    alias="controller",
                    server_name="Test Server",
                    channel_name="Controller Voice",
                ),
                message=(
                    "Discord voice target resolved: server "
                    "'Test Server', channel 'Controller Voice'. "
                    "UI joining is not implemented yet, sir."
                ),
            )

        result = route_local_skill(
            "open controller voice",
            resolve_discord_voice_command=resolve_discord_voice_command,
            launch_app=lambda _: self.fail(
                "Open voice commands must not reach app launching."
            ),
            console_output=lambda _: None,
        )

        self.assertIsNotNone(result)
        self.assertEqual(
            result.skill_name,
            "resolve_discord_voice_target",
        )
        self.assertEqual(calls, [("discord", "open controller voice")])

    def test_unrelated_open_app_still_launches_app(self):
        calls = []

        def resolve_discord_voice_command(
            user_input: str,
        ) -> DiscordVoiceTargetResolution | None:
            calls.append(("discord", user_input))
            return None

        def launch_app(name: str) -> LaunchResult:
            calls.append(("launch", name))
            return LaunchResult(
                success=True,
                display_name=name,
                message=f"Opening {name}, sir.",
            )

        result = route_local_skill(
            "open Discord",
            resolve_discord_voice_command=resolve_discord_voice_command,
            launch_app=launch_app,
            console_output=lambda _: None,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.skill_name, "open_app")
        self.assertEqual(result.message, "Opening Discord, sir.")
        self.assertEqual(
            calls,
            [
                ("discord", "open Discord"),
                ("launch", "Discord"),
            ],
        )


if __name__ == "__main__":
    unittest.main()