from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from skills.discord_voice_config import (
    DiscordVoiceConfigError,
    get_discord_voice_target,
    load_discord_voice_targets,
)


class DiscordVoiceConfigTests(unittest.TestCase):
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

    def test_missing_config_returns_no_targets(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "missing.json"

            self.assertEqual(
                load_discord_voice_targets(path=path),
                (),
            )

    def test_loads_private_voice_target(self):
        with TemporaryDirectory() as directory:
            path = self.write_config(
                {
                    "targets": {
                        "controller": {
                            "server_name": "Test Server",
                            "channel_name": "Test Voice",
                            "quick_switcher_query": "test voice",
                        }
                    }
                },
                directory=directory,
            )

            targets = load_discord_voice_targets(path=path)

            self.assertEqual(len(targets), 1)
            self.assertEqual(targets[0].alias, "controller")
            self.assertEqual(targets[0].server_name, "Test Server")
            self.assertEqual(targets[0].channel_name, "Test Voice")
            self.assertEqual(
                targets[0].quick_switcher_query,
                "test voice",
            )

    def test_resolves_alias_without_guessing_case_or_hyphen_spacing(self):
        with TemporaryDirectory() as directory:
            path = self.write_config(
                {
                    "targets": {
                        "main voice": {
                            "server_name": "Test Server",
                            "channel_name": "General Voice",
                        }
                    }
                },
                directory=directory,
            )

            target = get_discord_voice_target(
                "MAIN-VOICE",
                path=path,
            )

            self.assertEqual(target.alias, "main voice")
            self.assertEqual(target.server_name, "Test Server")
            self.assertEqual(target.channel_name, "General Voice")
            self.assertIsNone(target.quick_switcher_query)

    def test_rejects_unknown_alias(self):
        with TemporaryDirectory() as directory:
            path = self.write_config(
                {
                    "targets": {
                        "controller": {
                            "server_name": "Test Server",
                            "channel_name": "Test Voice",
                        }
                    }
                },
                directory=directory,
            )

            with self.assertRaisesRegex(
                DiscordVoiceConfigError,
                "No Discord voice target configured",
            ):
                get_discord_voice_target("music", path=path)

    def test_rejects_empty_requested_alias(self):
        with self.assertRaisesRegex(
            DiscordVoiceConfigError,
            "alias cannot be empty",
        ):
            get_discord_voice_target(" ")

    def test_rejects_invalid_json(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "discord_voice_channels.json"
            path.write_text("{not json", encoding="utf-8")

            with self.assertRaisesRegex(
                DiscordVoiceConfigError,
                "not valid JSON",
            ):
                load_discord_voice_targets(path=path)

    def test_rejects_non_object_root(self):
        with TemporaryDirectory() as directory:
            path = self.write_config(
                [],
                directory=directory,
            )

            with self.assertRaisesRegex(
                DiscordVoiceConfigError,
                "must be a JSON object",
            ):
                load_discord_voice_targets(path=path)

    def test_rejects_non_object_targets_field(self):
        with TemporaryDirectory() as directory:
            path = self.write_config(
                {
                    "targets": [],
                },
                directory=directory,
            )

            with self.assertRaisesRegex(
                DiscordVoiceConfigError,
                "targets",
            ):
                load_discord_voice_targets(path=path)

    def test_rejects_missing_server_name(self):
        with TemporaryDirectory() as directory:
            path = self.write_config(
                {
                    "targets": {
                        "controller": {
                            "channel_name": "Test Voice",
                        }
                    }
                },
                directory=directory,
            )

            with self.assertRaisesRegex(
                DiscordVoiceConfigError,
                "server_name",
            ):
                load_discord_voice_targets(path=path)

    def test_rejects_missing_channel_name(self):
        with TemporaryDirectory() as directory:
            path = self.write_config(
                {
                    "targets": {
                        "controller": {
                            "server_name": "Test Server",
                        }
                    }
                },
                directory=directory,
            )

            with self.assertRaisesRegex(
                DiscordVoiceConfigError,
                "channel_name",
            ):
                load_discord_voice_targets(path=path)

    def test_rejects_empty_quick_switcher_query(self):
        with TemporaryDirectory() as directory:
            path = self.write_config(
                {
                    "targets": {
                        "controller": {
                            "server_name": "Test Server",
                            "channel_name": "Test Voice",
                            "quick_switcher_query": " ",
                        }
                    }
                },
                directory=directory,
            )

            with self.assertRaisesRegex(
                DiscordVoiceConfigError,
                "quick_switcher_query",
            ):
                load_discord_voice_targets(path=path)

    def test_rejects_duplicate_normalised_aliases(self):
        with TemporaryDirectory() as directory:
            path = self.write_config(
                {
                    "targets": {
                        "main voice": {
                            "server_name": "Test Server",
                            "channel_name": "One",
                        },
                        "main-voice": {
                            "server_name": "Test Server",
                            "channel_name": "Two",
                        },
                    }
                },
                directory=directory,
            )

            with self.assertRaisesRegex(
                DiscordVoiceConfigError,
                "Duplicate Discord voice target alias",
            ):
                load_discord_voice_targets(path=path)


if __name__ == "__main__":
    unittest.main()