from __future__ import annotations

import unittest

from PIL import Image

from tools.inspect_nitrosense_visual import (
    MIN_SELECTED_RED_DENSITY,
    MIN_SELECTED_RED_PIXELS,
    WindowRect,
    measure_selected_red,
    normalized_anchor_to_screen,
    normalized_region_to_box,
    validate_window_layout,
)


class NitroSenseVisualInspectorTests(unittest.TestCase):
    def test_normalized_region_converts_to_pixel_box(self):
        pixel_box = normalized_region_to_box(
            (0.10, 0.20, 0.40, 0.50),
            width=1000,
            height=500,
        )

        self.assertEqual(pixel_box, (100, 100, 400, 250))

    def test_red_selected_state_is_detected(self):
        image = Image.new("RGB", (100, 100), (30, 30, 30))

        for horizontal_position in range(20, 60):
            for vertical_position in range(20, 60):
                image.putpixel(
                    (horizontal_position, vertical_position),
                    (230, 40, 40),
                )

        signal = measure_selected_red(
            image,
            region=(0.10, 0.10, 0.90, 0.90),
        )

        self.assertTrue(signal.selected)
        self.assertGreaterEqual(
            signal.red_pixels,
            MIN_SELECTED_RED_PIXELS,
        )
        self.assertGreaterEqual(
            signal.red_density,
            MIN_SELECTED_RED_DENSITY,
        )

    def test_dark_region_is_not_detected_as_selected(self):
        image = Image.new("RGB", (100, 100), (45, 45, 45))

        signal = measure_selected_red(
            image,
            region=(0.10, 0.10, 0.90, 0.90),
        )

        self.assertFalse(signal.selected)
        self.assertEqual(signal.red_pixels, 0)

    def test_normalized_anchor_uses_live_window_position(self):
        window = WindowRect(
            hwnd=123,
            left=100,
            top=50,
            right=1100,
            bottom=550,
        )

        point = normalized_anchor_to_screen(
            (0.25, 0.50),
            window=window,
        )

        self.assertEqual(point, (350, 300))

    def test_known_nitrosense_layout_is_accepted(self):
        window = WindowRect(
            hwnd=456,
            left=108,
            top=52,
            right=1428,
            bottom=812,
        )

        validate_window_layout(window)


if __name__ == "__main__":
    unittest.main()