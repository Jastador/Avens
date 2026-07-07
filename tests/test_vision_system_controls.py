from __future__ import annotations

import unittest
from unittest.mock import patch

from core import vision
from core.gesture_engine import GestureSignal
from skills.system_controls import (
    BRIGHTNESS_MINIMUM,
    BrightnessState,
    SystemControlError,
    VolumeState,
)


class VisionSystemControlsTests(unittest.TestCase):
    def setUp(self):
        self.processor = vision.HandVisionProcessor.__new__(
            vision.HandVisionProcessor
        )

    def test_vision_module_imports_without_legacy_volume_helper(self):
        self.assertTrue(
            hasattr(vision, "HandVisionProcessor")
        )
        self.assertFalse(
            hasattr(vision, "force_volume_change")
        )

    def test_volume_gesture_uses_shared_direct_volume_control(self):
        signal = GestureSignal(
            label="VOLUME UP",
            mode="VOLUME",
            action="VOLUME_DELTA",
            value=3,
        )

        with patch.object(
            vision,
            "adjust_master_volume",
            return_value=VolumeState(
                level=53,
                muted=False,
            ),
        ) as adjust_volume:
            result = self.processor._apply_signal(signal)

        adjust_volume.assert_called_once_with(3)
        self.assertEqual(result, "VOLUME UP x3")

    def test_volume_gesture_keeps_existing_eight_step_cap(self):
        signal = GestureSignal(
            label="VOLUME DOWN",
            mode="VOLUME",
            action="VOLUME_DELTA",
            value=-12,
        )

        with patch.object(
            vision,
            "adjust_master_volume",
            return_value=VolumeState(
                level=42,
                muted=False,
            ),
        ) as adjust_volume:
            result = self.processor._apply_signal(signal)

        adjust_volume.assert_called_once_with(-8)
        self.assertEqual(result, "VOLUME DOWN x8")

    def test_volume_gesture_handles_system_control_error(self):
        signal = GestureSignal(
            label="VOLUME UP",
            mode="VOLUME",
            action="VOLUME_DELTA",
            value=2,
        )

        with patch.object(
            vision,
            "adjust_master_volume",
            side_effect=SystemControlError("test failure"),
        ):
            result = self.processor._apply_signal(signal)

        self.assertEqual(result, "VOLUME FAILED")

    def test_brightness_gesture_uses_shared_safe_control(self):
        signal = GestureSignal(
            label="BRIGHTNESS: 50%",
            mode="BRIGHTNESS",
            action="SET_BRIGHTNESS",
            value=50,
        )

        with patch.object(
            vision,
            "set_primary_brightness",
            return_value=BrightnessState(level=50),
        ) as set_brightness:
            result = self.processor._apply_signal(signal)

        set_brightness.assert_called_once_with(50)
        self.assertEqual(result, "BRIGHTNESS 50%")

    def test_brightness_gesture_respects_shared_visible_floor(self):
        signal = GestureSignal(
            label="BRIGHTNESS: 0%",
            mode="BRIGHTNESS",
            action="SET_BRIGHTNESS",
            value=0,
        )

        with patch.object(
            vision,
            "set_primary_brightness",
            return_value=BrightnessState(
                level=BRIGHTNESS_MINIMUM
            ),
        ) as set_brightness:
            result = self.processor._apply_signal(signal)

        set_brightness.assert_called_once_with(
            BRIGHTNESS_MINIMUM
        )
        self.assertEqual(
            result,
            f"BRIGHTNESS {BRIGHTNESS_MINIMUM}%",
        )

    def test_brightness_gesture_handles_system_control_error(self):
        signal = GestureSignal(
            label="BRIGHTNESS: 50%",
            mode="BRIGHTNESS",
            action="SET_BRIGHTNESS",
            value=50,
        )

        with patch.object(
            vision,
            "set_primary_brightness",
            side_effect=SystemControlError("test failure"),
        ):
            result = self.processor._apply_signal(signal)

        self.assertEqual(result, "BRIGHTNESS FAILED")