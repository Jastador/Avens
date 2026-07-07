from __future__ import annotations

import unittest

from skills.router import route_local_skill
from skills.system_controls import (
    BrightnessState,
    ReadingModeResult,
    SystemControlError,
    VolumeState,
)


class SystemControlsRouterTests(unittest.TestCase):
    def test_set_volume_uses_exact_requested_percentage(self):
        requested_levels = []

        result = route_local_skill(
            "Set volume to 70",
            set_volume=lambda level: (
                requested_levels.append(level)
                or VolumeState(level=70, muted=False)
            ),
        )

        self.assertEqual(requested_levels, [70])
        self.assertEqual(result.skill_name, "control_master_volume")
        self.assertEqual(
            result.message,
            "Master volume set to 70%, sir.",
        )

    def test_default_volume_adjustment_is_ten_percent(self):
        changes = []

        result = route_local_skill(
            "Increase volume",
            adjust_volume=lambda change: (
                changes.append(change)
                or VolumeState(level=60, muted=False)
            ),
        )

        self.assertEqual(changes, [10])
        self.assertEqual(
            result.message,
            "Master volume increased to 60%, sir.",
        )

    def test_explicit_volume_decrease_uses_requested_amount(self):
        changes = []

        result = route_local_skill(
            "Decrease volume by 15",
            adjust_volume=lambda change: (
                changes.append(change)
                or VolumeState(level=35, muted=False)
            ),
        )

        self.assertEqual(changes, [-15])
        self.assertEqual(
            result.message,
            "Master volume decreased to 35%, sir.",
        )

    def test_set_volume_does_not_claim_to_unmute(self):
        result = route_local_skill(
            "Set volume to 70",
            set_volume=lambda _: VolumeState(
                level=70,
                muted=True,
            ),
        )

        self.assertEqual(
            result.message,
            (
                "Master volume set to 70%, but audio remains muted, "
                "sir."
            ),
        )

    def test_mute_and_unmute_call_exact_mute_states(self):
        mute_states = []

        muted_result = route_local_skill(
            "Mute volume",
            set_volume_mute=lambda muted: (
                mute_states.append(muted)
                or VolumeState(level=45, muted=muted)
            ),
        )
        unmuted_result = route_local_skill(
            "Unmute volume",
            set_volume_mute=lambda muted: (
                mute_states.append(muted)
                or VolumeState(level=45, muted=muted)
            ),
        )

        self.assertEqual(mute_states, [True, False])
        self.assertEqual(
            muted_result.message,
            "Master volume muted at 45%, sir.",
        )
        self.assertEqual(
            unmuted_result.message,
            "Master volume unmuted at 45%, sir.",
        )

    def test_get_volume_reports_level_and_mute_state(self):
        result = route_local_skill(
            "What is the volume?",
            get_volume=lambda: VolumeState(
                level=50,
                muted=False,
            ),
        )

        self.assertEqual(
            result.message,
            "Master volume is 50%, and audio is unmuted, sir.",
        )

    def test_set_brightness_uses_exact_requested_percentage(self):
        requested_levels = []

        result = route_local_skill(
            "Set brightness to 50",
            set_brightness=lambda level: (
                requested_levels.append(level)
                or BrightnessState(level=50)
            ),
        )

        self.assertEqual(requested_levels, [50])
        self.assertEqual(
            result.skill_name,
            "control_primary_brightness",
        )
        self.assertEqual(
            result.message,
            "Built-in display brightness set to 50%, sir.",
        )

    def test_default_brightness_adjustment_is_ten_percent(self):
        changes = []

        result = route_local_skill(
            "Decrease brightness",
            adjust_brightness=lambda change: (
                changes.append(change)
                or BrightnessState(level=40)
            ),
        )

        self.assertEqual(changes, [-10])
        self.assertEqual(
            result.message,
            "Built-in display brightness decreased to 40%, sir.",
        )

    def test_open_night_light_uses_the_fixed_router_skill(self):
        calls = []

        result = route_local_skill(
            "Open Night Light settings",
            open_night_light=lambda: calls.append("opened"),
        )

        self.assertEqual(calls, ["opened"])
        self.assertEqual(
            result.skill_name,
            "open_night_light_settings",
        )
        self.assertEqual(
            result.message,
            "I opened Night Light Settings, sir.",
        )

    def test_reading_setup_is_honest_about_night_light(self):
        result = route_local_skill(
            "Start reading setup",
            start_reading_setup=lambda: ReadingModeResult(
                brightness=BrightnessState(level=30),
                night_light_settings_opened=True,
            ),
        )

        self.assertEqual(
            result.skill_name,
            "start_reading_setup",
        )
        self.assertIn(
            "brightness is 30%",
            result.message,
        )
        self.assertIn(
            "you can enable Night Light there",
            result.message,
        )

    def test_system_control_error_is_handled_without_ai_fallback(self):
        output = []

        def fail(_: int) -> VolumeState:
            raise SystemControlError("test failure")

        result = route_local_skill(
            "Set volume to 70",
            set_volume=fail,
            console_output=output.append,
        )

        self.assertEqual(
            result.message,
            "I could not set master volume safely, sir.",
        )
        self.assertIn(
            "System controls error: test failure",
            "\n".join(output),
        )