from __future__ import annotations

import unittest

from PIL import Image

from tools.inspect_nitrosense_visual import measure_selected_red


def make_test_image(
    *,
    red_pixels: int,
    width: int = 200,
    height: int = 200,
) -> Image.Image:
    """Build a tiny deterministic image with exact red-pixel count."""
    image = Image.new("RGB", (width, height), (0, 0, 0))
    pixels = image.load()

    for index in range(red_pixels):
        x = index % width
        y = index // width
        pixels[x, y] = (255, 0, 0)

    return image


class NitroSenseVisualTests(unittest.TestCase):
    def test_rejects_weak_red_noise_seen_on_default_profile(self):
        signal = measure_selected_red(
            make_test_image(red_pixels=300),
            region=(0.0, 0.0, 1.0, 1.0),
        )

        self.assertFalse(signal.selected)
        self.assertEqual(signal.red_pixels, 300)
        self.assertAlmostEqual(
            signal.red_density,
            300 / 40_000,
        )

    def test_accepts_strong_red_selection_signal(self):
        signal = measure_selected_red(
            make_test_image(red_pixels=600),
            region=(0.0, 0.0, 1.0, 1.0),
        )

        self.assertTrue(signal.selected)
        self.assertEqual(signal.red_pixels, 600)
        self.assertAlmostEqual(
            signal.red_density,
            600 / 40_000,
        )


if __name__ == "__main__":
    unittest.main()