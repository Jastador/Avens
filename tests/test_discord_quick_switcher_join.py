from __future__ import annotations

import unittest

from skills.app_window_focus import AppWindowFocusResult
from skills.discord_quick_switcher_join import (
    send_discord_quick_switcher_join_command,
)
from skills.discord_voice_config import (
    DiscordVoiceConfigError,
    DiscordVoiceTarget,
)


class DiscordQuickSwitcherJoinTests(unittest.TestCase):
    @staticmethod
    def _target(
        *,
        quick_switcher_query: str | None = "music 1.0",
    ) -> DiscordVoiceTarget:
        return DiscordVoiceTarget(
            alias="controller",
            server_name="Test Server",
            channel_name="Test Voice",
            quick_switcher_query=quick_switcher_query,
        )

    def test_sends_quick_switcher_join_keys_after_focus(self):
        calls = []

        result = send_discord_quick_switcher_join_command(
            "controller",
            get_target=lambda alias: calls.append(
                ("target", alias)
            ) or self._target(),
            focus_discord=lambda: calls.append(
                ("focus", "Discord")
            ) or AppWindowFocusResult(
                success=True,
                display_name="Discord",
                message="Brought Discord to foreground.",
            ),
            hotkey=lambda *keys: calls.append(("hotkey", keys)),
            write_text=lambda text, **kwargs: calls.append(
                ("write", text, kwargs)
            ),
            press_key=lambda key: calls.append(("press", key)),
            sleep=lambda seconds: calls.append(("sleep", seconds)),
        )

        self.assertTrue(result.success)
        self.assertEqual(result.alias, "controller")
        self.assertIsNotNone(result.target)
        self.assertEqual(
            result.message,
            "Discord Quick Switcher join command sent for "
            "'music 1.0', sir.",
        )
        self.assertEqual(
            calls,
            [
                ("target", "controller"),
                ("focus", "Discord"),
                ("sleep", 6.0),
                ("hotkey", ("ctrl", "k")),
                ("sleep", 0.50),
                (
                    "write",
                    "music 1.0",
                    {"interval": 0.01},
                ),
                ("sleep", 0.10),
                ("press", "enter"),
            ],
        )

    def test_rejects_empty_alias_without_touching_keyboard(self):
        calls = []

        result = send_discord_quick_switcher_join_command(
            " ",
            get_target=lambda _: calls.append("target"),
            focus_discord=lambda: calls.append("focus"),
            hotkey=lambda *_: calls.append("hotkey"),
            write_text=lambda *_args, **_kwargs: calls.append("write"),
            press_key=lambda _: calls.append("press"),
            sleep=lambda _: calls.append("sleep"),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.alias, "")
        self.assertIsNone(result.target)
        self.assertEqual(calls, [])
        self.assertEqual(
            result.message,
            "Discord voice target alias cannot be empty, sir.",
        )

    def test_reports_unknown_target_without_keyboard(self):
        calls = []

        def get_target(alias: str) -> DiscordVoiceTarget:
            calls.append(("target", alias))
            raise DiscordVoiceConfigError(
                "No Discord voice target configured."
            )

        result = send_discord_quick_switcher_join_command(
            "missing",
            get_target=get_target,
            focus_discord=lambda: calls.append("focus"),
            hotkey=lambda *_: calls.append("hotkey"),
            write_text=lambda *_args, **_kwargs: calls.append("write"),
            press_key=lambda _: calls.append("press"),
            sleep=lambda _: calls.append("sleep"),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.alias, "missing")
        self.assertIsNone(result.target)
        self.assertEqual(calls, [("target", "missing")])
        self.assertEqual(
            result.message,
            "No Discord voice target configured.",
        )

    def test_requires_quick_switcher_query(self):
        calls = []

        result = send_discord_quick_switcher_join_command(
            "controller",
            get_target=lambda alias: calls.append(
                ("target", alias)
            ) or self._target(quick_switcher_query=None),
            focus_discord=lambda: calls.append("focus"),
            hotkey=lambda *_: calls.append("hotkey"),
            write_text=lambda *_args, **_kwargs: calls.append("write"),
            press_key=lambda _: calls.append("press"),
            sleep=lambda _: calls.append("sleep"),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.alias, "controller")
        self.assertEqual(calls, [("target", "controller")])
        self.assertEqual(
            result.message,
            "Discord voice target 'controller' does not define "
            "quick_switcher_query, sir.",
        )

    def test_stops_when_discord_focus_fails(self):
        calls = []

        result = send_discord_quick_switcher_join_command(
            "controller",
            get_target=lambda alias: calls.append(
                ("target", alias)
            ) or self._target(),
            focus_discord=lambda: calls.append(
                ("focus", "Discord")
            ) or AppWindowFocusResult(
                success=False,
                display_name="Discord",
                message="Windows would not focus Discord.",
            ),
            hotkey=lambda *_: calls.append("hotkey"),
            write_text=lambda *_args, **_kwargs: calls.append("write"),
            press_key=lambda _: calls.append("press"),
            sleep=lambda _: calls.append("sleep"),
        )

        self.assertFalse(result.success)
        self.assertEqual(
            calls,
            [
                ("target", "controller"),
                ("focus", "Discord"),
            ],
        )
        self.assertEqual(
            result.message,
            "I could not focus Discord before using Quick Switcher: "
            "Windows would not focus Discord.",
        )

    def test_reports_keyboard_failure_safely(self):
        calls = []

        def broken_hotkey(*keys: str) -> object:
            calls.append(("hotkey", keys))
            raise RuntimeError("keyboard unavailable")

        result = send_discord_quick_switcher_join_command(
            "controller",
            get_target=lambda alias: calls.append(
                ("target", alias)
            ) or self._target(),
            focus_discord=lambda: calls.append(
                ("focus", "Discord")
            ) or AppWindowFocusResult(
                success=True,
                display_name="Discord",
                message="Brought Discord to foreground.",
            ),
            hotkey=broken_hotkey,
            write_text=lambda *_args, **_kwargs: calls.append("write"),
            press_key=lambda _: calls.append("press"),
            sleep=lambda seconds: calls.append(("sleep", seconds)),
        )

        self.assertFalse(result.success)
        self.assertEqual(
            calls,
            [
                ("target", "controller"),
                ("focus", "Discord"),
                ("sleep", 6.0),
                ("hotkey", ("ctrl", "k")),
            ],
        )
        self.assertEqual(
            result.message,
            "I could not send Discord Quick Switcher keys safely: "
            "keyboard unavailable",
        )

    def test_rejects_negative_delays(self):
        with self.assertRaises(ValueError):
            send_discord_quick_switcher_join_command(
                "controller",
                after_focus_delay_seconds=-0.1,
            )

        with self.assertRaises(ValueError):
            send_discord_quick_switcher_join_command(
                "controller",
                type_interval_seconds=-0.1,
            )


if __name__ == "__main__":
    unittest.main()