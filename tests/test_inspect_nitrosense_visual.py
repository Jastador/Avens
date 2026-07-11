from __future__ import annotations

from types import SimpleNamespace
import unittest

import tools.inspect_nitrosense_visual as visual


class InspectNitroSenseVisualTests(unittest.TestCase):
    def test_activate_window_wraps_foreground_api_failure(self):
        calls = []

        fake_win32gui = SimpleNamespace(
            IsWindow=lambda hwnd: True,
            IsIconic=lambda hwnd: False,
            ShowWindow=lambda hwnd, command: calls.append(
                ("show", hwnd, command)
            ),
            BringWindowToTop=lambda hwnd: calls.append(
                ("bring", hwnd)
            ),
            SetForegroundWindow=lambda hwnd: (_ for _ in ()).throw(
                Exception("foreground blocked")
            ),
            GetForegroundWindow=lambda: 999,
        )

        original_win32gui = visual.win32gui
        original_sleep = visual.time.sleep

        try:
            visual.win32gui = fake_win32gui
            visual.time.sleep = lambda _: None

            with self.assertRaisesRegex(
                RuntimeError,
                "NitroSense could not be brought to the foreground",
            ):
                visual.activate_window(700)
        finally:
            visual.win32gui = original_win32gui
            visual.time.sleep = original_sleep

        self.assertEqual(
            calls,
            [
                ("show", 700, visual.win32con.SW_SHOW),
                ("bring", 700),
            ],
        )


if __name__ == "__main__":
    unittest.main()