from __future__ import annotations

import unittest

from skills.system_controls import (
    BRIGHTNESS_MINIMUM,
    NIGHT_LIGHT_SETTINGS_URI,
    ReadingModeResult,
    SystemControlError,
    adjust_master_volume,
    adjust_primary_brightness,
    get_master_volume,
    get_primary_brightness,
    open_night_light_settings,
    set_master_mute,
    set_master_volume,
    set_primary_brightness,
    start_reading_mode,
)


class FakeVolumeEndpoint:
    def __init__(
        self,
        *,
        scalar: float = 0.5,
        muted: bool = False,
    ) -> None:
        self.scalar = scalar
        self.muted = muted
        self.set_scalar_calls: list[float] = []
        self.set_mute_calls: list[bool] = []

    def GetMasterVolumeLevelScalar(self) -> float:
        return self.scalar

    def SetMasterVolumeLevelScalar(
        self,
        scalar: float,
        _event_context: object,
    ) -> None:
        self.scalar = scalar
        self.set_scalar_calls.append(scalar)

    def GetMute(self) -> bool:
        return self.muted

    def SetMute(
        self,
        muted: bool,
        _event_context: object,
    ) -> None:
        self.muted = muted
        self.set_mute_calls.append(muted)


class FakeBrightnessApi:
    def __init__(
        self,
        *,
        level: int = 50,
    ) -> None:
        self.level = level
        self.get_calls: list[int] = []
        self.set_calls: list[tuple[int, int]] = []

    def get_brightness(
        self,
        *,
        display: int,
    ) -> list[int]:
        self.get_calls.append(display)
        return [self.level]

    def set_brightness(
        self,
        level: int,
        *,
        display: int,
    ) -> None:
        self.level = level
        self.set_calls.append((level, display))


class SystemControlsTests(unittest.TestCase):
    def test_reads_master_volume_and_mute_state(self):
        endpoint = FakeVolumeEndpoint(
            scalar=0.50058,
            muted=True,
        )

        state = get_master_volume(endpoint=endpoint)

        self.assertEqual(state.level, 50)
        self.assertTrue(state.muted)

    def test_sets_exact_master_volume_without_unmuting(self):
        endpoint = FakeVolumeEndpoint(
            scalar=0.25,
            muted=True,
        )

        state = set_master_volume(
            70,
            endpoint=endpoint,
        )

        self.assertEqual(endpoint.set_scalar_calls, [0.7])
        self.assertEqual(state.level, 70)
        self.assertTrue(state.muted)

    def test_adjusts_master_volume_and_clamps_to_100(self):
        endpoint = FakeVolumeEndpoint(scalar=0.96)

        state = adjust_master_volume(
            10,
            endpoint=endpoint,
        )

        self.assertEqual(endpoint.set_scalar_calls, [1.0])
        self.assertEqual(state.level, 100)

    def test_adjusts_master_volume_and_clamps_to_zero(self):
        endpoint = FakeVolumeEndpoint(scalar=0.04)

        state = adjust_master_volume(
            -10,
            endpoint=endpoint,
        )

        self.assertEqual(endpoint.set_scalar_calls, [0.0])
        self.assertEqual(state.level, 0)

    def test_mute_and_unmute_use_the_real_endpoint_state(self):
        endpoint = FakeVolumeEndpoint(muted=False)

        muted_state = set_master_mute(
            True,
            endpoint=endpoint,
        )
        unmuted_state = set_master_mute(
            False,
            endpoint=endpoint,
        )

        self.assertEqual(endpoint.set_mute_calls, [True, False])
        self.assertTrue(muted_state.muted)
        self.assertFalse(unmuted_state.muted)

    def test_volume_rejects_invalid_percentages(self):
        endpoint = FakeVolumeEndpoint()

        with self.assertRaisesRegex(
            SystemControlError,
            "between 0 and 100",
        ):
            set_master_volume(
                101,
                endpoint=endpoint,
            )

    def test_reads_primary_brightness_from_display_zero_only(self):
        brightness_api = FakeBrightnessApi(level=99)

        state = get_primary_brightness(
            brightness_api=brightness_api,
        )

        self.assertEqual(state.level, 99)
        self.assertEqual(brightness_api.get_calls, [0])

    def test_sets_primary_brightness_with_a_visible_floor(self):
        brightness_api = FakeBrightnessApi(level=99)

        state = set_primary_brightness(
            50,
            brightness_api=brightness_api,
        )

        self.assertEqual(brightness_api.set_calls, [(50, 0)])
        self.assertEqual(state.level, 50)

        with self.assertRaisesRegex(
            SystemControlError,
            f"between {BRIGHTNESS_MINIMUM} and 100",
        ):
            set_primary_brightness(
                0,
                brightness_api=brightness_api,
            )

    def test_adjusts_brightness_and_clamps_to_visible_floor(self):
        brightness_api = FakeBrightnessApi(level=15)

        state = adjust_primary_brightness(
            -10,
            brightness_api=brightness_api,
        )

        self.assertEqual(
            brightness_api.set_calls,
            [(BRIGHTNESS_MINIMUM, 0)],
        )
        self.assertEqual(
            state.level,
            BRIGHTNESS_MINIMUM,
        )

    def test_open_night_light_settings_uses_only_fixed_uri(self):
        opened_uris = []

        open_night_light_settings(
            open_uri=opened_uris.append,
        )

        self.assertEqual(
            opened_uris,
            [NIGHT_LIGHT_SETTINGS_URI],
        )

    def test_reading_mode_sets_brightness_then_opens_settings(self):
        brightness_api = FakeBrightnessApi(level=99)
        opened_uris = []

        result = start_reading_mode(
            brightness_api=brightness_api,
            open_uri=opened_uris.append,
        )

        self.assertIsInstance(result, ReadingModeResult)
        self.assertEqual(result.brightness.level, 30)
        self.assertTrue(result.night_light_settings_opened)
        self.assertEqual(brightness_api.set_calls, [(30, 0)])
        self.assertEqual(
            opened_uris,
            [NIGHT_LIGHT_SETTINGS_URI],
        )