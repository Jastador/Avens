from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from skills.discord_voice_target_resolver import (
    parse_discord_voice_target_alias,
    resolve_discord_voice_target_command,
)


class DiscordVoiceTargetResolverTests(unittest.TestCase):
    def write_config(
        self,
        config: object,
        *,
        directory: str,
    ) -> Path:
        path = Path(directory) / "discord_voice_channels.json"
        path.write_text(
            json.dumps(config),
            encoding="utf-8",
        )
        return path

    def test_ignores_unrelated_text(self):
        self.assertIsNone(
            parse_discord_voice_target_alias("start gaming mode")
        )
        self.assertIsNone(
            resolve_discord_voice_target_command("start gaming mode")
        )

    def test_parses_join_voice_command(self):
        self.assertEqual(
            parse_discord_voice_target_alias("join controller voice"),
            "controller",
        )

    def test_parses_polite_discord_voice_channel_command(self):
        self.assertEqual(
            parse_discord_voice_target_alias(
                "please connect to main-voice discord voice channel"
            ),
            "main-voice",
        )

    def test_rejects_command_without_alias(self):
        self.assertIsNone(
            parse_discord_voice_target_alias("join voice")
        )

    def test_resolves_configured_voice_target(self):
        with TemporaryDirectory() as directory:
            path = self.write_config(
                {
                    "targets": {
                        "controller": {
                            "server_name": "Test Server",
                            "channel_name": "Controller Voice",
                        }
                    }
                },
                directory=directory,
            )

            result = resolve_discord_voice_target_command(
                "join controller voice",
                path=path,
            )

            self.assertIsNotNone(result)
            self.assertTrue(result.success)
            self.assertEqual(result.alias, "controller")
            self.assertIsNotNone(result.target)
            self.assertEqual(result.target.server_name, "Test Server")
            self.assertEqual(
                result.target.channel_name,
                "Controller Voice",
            )
            self.assertEqual(
                result.message,
                "Discord voice target resolved: server 'Test Server', "
                "channel 'Controller Voice'. UI joining is not "
                "implemented yet, sir.",
            )

    def test_reports_unknown_configured_voice_target(self):
        with TemporaryDirectory() as directory:
            path = self.write_config(
                {
                    "targets": {
                        "controller": {
                            "server_name": "Test Server",
                            "channel_name": "Controller Voice",
                        }
                    }
                },
                directory=directory,
            )

            result = resolve_discord_voice_target_command(
                "join music voice",
                path=path,
            )

            self.assertIsNotNone(result)
            self.assertFalse(result.success)
            self.assertEqual(result.alias, "music")
            self.assertIsNone(result.target)
            self.assertIn(
                "No Discord voice target configured",
                result.message,
            )

    def test_reports_missing_config_as_unknown_target(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "missing.json"

            result = resolve_discord_voice_target_command(
                "join controller voice",
                path=path,
            )

            self.assertIsNotNone(result)
            self.assertFalse(result.success)
            self.assertEqual(result.alias, "controller")
            self.assertIsNone(result.target)
            self.assertIn(
                "No Discord voice target configured",
                result.message,
            )

    def test_reports_invalid_config(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "discord_voice_channels.json"
            path.write_text("{not json", encoding="utf-8")

            result = resolve_discord_voice_target_command(
                "join controller voice",
                path=path,
            )

            self.assertIsNotNone(result)
            self.assertFalse(result.success)
            self.assertEqual(result.alias, "controller")
            self.assertIsNone(result.target)
            self.assertIn("not valid JSON", result.message)


if __name__ == "__main__":
    unittest.main()