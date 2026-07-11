from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skills.local_routine_settings import (
    LocalRoutineSettingsError,
    RoutineSettings,
    get_routine_settings,
    load_routine_settings,
)


class LocalRoutineSettingsTests(unittest.TestCase):
    def test_missing_private_file_loads_no_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "missing.json"

            self.assertEqual(
                load_routine_settings(settings_file=settings_file),
                {},
            )

    def test_loads_private_brightness_and_volume(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "routine_settings.json"
            settings_file.write_text(
                json.dumps(
                    {
                        "study": {
                            "brightness": 90,
                            "volume": 40,
                            "discord_voice_target_alias": "controller",
                        },
                        "project-dev": {
                            "brightness": 80,
                        },
                    }
                ),
                encoding="utf-8",
            )

            settings = load_routine_settings(
                settings_file=settings_file
            )

            self.assertEqual(
                settings["study"],
                RoutineSettings(
                    brightness=90,
                    volume=40,
                    discord_voice_target_alias="controller",
                ),
            )
            self.assertEqual(
                settings["project_dev"],
                RoutineSettings(brightness=80, volume=None),
            )

    def test_get_missing_routine_returns_empty_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "routine_settings.json"
            settings_file.write_text(
                json.dumps(
                    {
                        "study": {
                            "brightness": 90,
                        },
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                get_routine_settings(
                    "gaming",
                    settings_file=settings_file,
                ),
                RoutineSettings(),
            )

    def test_loads_private_discord_voice_target_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "routine_settings.json"
            settings_file.write_text(
                json.dumps(
                    {
                        "gaming": {
                            "discord_voice_target_alias": "controller",
                        },
                    }
                ),
                encoding="utf-8",
            )

            settings = load_routine_settings(
                settings_file=settings_file
            )

            self.assertEqual(
                settings["gaming"],
                RoutineSettings(
                    discord_voice_target_alias="controller",
                ),
            )

    def test_rejects_invalid_brightness(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "routine_settings.json"
            settings_file.write_text(
                json.dumps(
                    {
                        "study": {
                            "brightness": 5,
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(LocalRoutineSettingsError):
                load_routine_settings(settings_file=settings_file)

    def test_rejects_invalid_volume(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "routine_settings.json"
            settings_file.write_text(
                json.dumps(
                    {
                        "study": {
                            "volume": 101,
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(LocalRoutineSettingsError):
                load_routine_settings(settings_file=settings_file)

    def test_rejects_empty_discord_voice_target_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "routine_settings.json"
            settings_file.write_text(
                json.dumps(
                    {
                        "gaming": {
                            "discord_voice_target_alias": " ",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(LocalRoutineSettingsError):
                load_routine_settings(settings_file=settings_file)

    def test_rejects_unknown_setting_key(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "routine_settings.json"
            settings_file.write_text(
                json.dumps(
                    {
                        "study": {
                            "brightness": 90,
                            "turbo_nonsense": True,
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(LocalRoutineSettingsError):
                load_routine_settings(settings_file=settings_file)

    def test_rejects_non_object_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "routine_settings.json"
            settings_file.write_text(
                json.dumps(["study"]),
                encoding="utf-8",
            )

            with self.assertRaises(LocalRoutineSettingsError):
                load_routine_settings(settings_file=settings_file)


if __name__ == "__main__":
    unittest.main()