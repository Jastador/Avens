from __future__ import annotations

import unittest

from tools.inspect_nitrosense_visual import (
    NitroSenseVisualProbe,
    SelectionSignal,
    WindowRect,
)
from tools.nitrosense_gaming_profile import (
    NitroSenseControlError,
    apply_nitrosense_gaming_profile,
    main,
)

from tools.nitrosense_gaming_profile import main



def make_signal(
    selected: bool,
) -> SelectionSignal:
    """Build one deterministic selected-state signal."""
    return SelectionSignal(
        red_pixels=500 if selected else 0,
        total_pixels=10_000,
        red_density=0.05 if selected else 0.0,
        selected=selected,
    )


def make_probe(
    *,
    performance: bool,
    fan_max: bool,
    window_handle: int = 700,
) -> NitroSenseVisualProbe:
    """Build one deterministic NitroSense visual snapshot."""
    window = WindowRect(
        hwnd=window_handle,
        left=100,
        top=50,
        right=1_420,
        bottom=810,
    )

    return NitroSenseVisualProbe(
        window=window,
        fan_max=make_signal(fan_max),
        performance=make_signal(performance),
        fan_max_click_point=(300, 300),
        performance_click_point=(300, 700),
    )


def make_probe_sequence(
    *probes: NitroSenseVisualProbe,
):
    """Return one fake visual reader with stable final state."""
    remaining_probes = list(probes)
    latest_probe = remaining_probes[-1]

    def probe_visual_state(
        *,
        restore_previous_foreground: bool,
    ) -> NitroSenseVisualProbe:
        nonlocal latest_probe

        if remaining_probes:
            latest_probe = remaining_probes.pop(0)

        return latest_probe

    return probe_visual_state


class NitroSenseGamingProfileTests(unittest.TestCase):

    def test_status_mode_reports_probe_failure_without_traceback(self):
        def failing_probe_visual_state():
            raise RuntimeError("test layout failure")

        original_probe = (
            __import__(
                "tools.nitrosense_gaming_profile",
                fromlist=["probe_nitrosense_visual_state"],
            ).probe_nitrosense_visual_state
        )

        module = __import__(
            "tools.nitrosense_gaming_profile",
            fromlist=["probe_nitrosense_visual_state"],
        )

        try:
            module.probe_nitrosense_visual_state = (
                failing_probe_visual_state
            )

            result = main([])
        finally:
            module.probe_nitrosense_visual_state = original_probe

        self.assertEqual(result, 1)

    def test_applies_performance_then_fan_max_and_verifies_both(self):
        initial_probe = make_probe(
            performance=False,
            fan_max=False,
        )
        performance_probe = make_probe(
            performance=True,
            fan_max=False,
        )
        final_probe = make_probe(
            performance=True,
            fan_max=True,
        )
        clicks = []
        restored_windows = []
        foreground_windows = iter((999, 700, 700))

        result = apply_nitrosense_gaming_profile(
            probe_visual_state=make_probe_sequence(
                initial_probe,
                performance_probe,
                final_probe,
            ),
            click=clicks.append,
            get_foreground_window=lambda: next(
                foreground_windows
            ),
            restore_foreground_window=restored_windows.append,
            sleep=lambda _: None,
            monotonic=lambda: 0.0,
            enable_dpi=lambda: None,
            timeout_seconds=0.0,
        )

        self.assertEqual(
            clicks,
            [
                initial_probe.performance_click_point,
                performance_probe.fan_max_click_point,
            ],
        )
        self.assertTrue(result.performance_changed)
        self.assertTrue(result.fan_max_changed)
        self.assertTrue(result.performance_selected)
        self.assertTrue(result.fan_max_selected)
        self.assertEqual(restored_windows, [999])

    def test_skips_clicks_when_both_states_are_already_selected(self):
        selected_probe = make_probe(
            performance=True,
            fan_max=True,
        )
        clicks = []
        restored_windows = []

        result = apply_nitrosense_gaming_profile(
            probe_visual_state=make_probe_sequence(selected_probe),
            click=clicks.append,
            get_foreground_window=lambda: 999,
            restore_foreground_window=restored_windows.append,
            sleep=lambda _: None,
            monotonic=lambda: 0.0,
            enable_dpi=lambda: None,
            timeout_seconds=0.0,
        )

        self.assertEqual(clicks, [])
        self.assertFalse(result.performance_changed)
        self.assertFalse(result.fan_max_changed)
        self.assertEqual(restored_windows, [999])

    def test_refuses_to_click_when_nitrosense_loses_foreground(self):
        initial_probe = make_probe(
            performance=False,
            fan_max=False,
        )
        clicks = []
        restored_windows = []
        foreground_windows = iter((999, 555))

        with self.assertRaises(NitroSenseControlError):
            apply_nitrosense_gaming_profile(
                probe_visual_state=make_probe_sequence(initial_probe),
                click=clicks.append,
                get_foreground_window=lambda: next(
                    foreground_windows
                ),
                restore_foreground_window=restored_windows.append,
                sleep=lambda _: None,
                monotonic=lambda: 0.0,
                enable_dpi=lambda: None,
                timeout_seconds=0.0,
            )

        self.assertEqual(clicks, [])
        self.assertEqual(restored_windows, [999])

    def test_reports_failure_when_visual_verification_does_not_change(self):
        unselected_probe = make_probe(
            performance=False,
            fan_max=False,
        )
        clicks = []
        restored_windows = []
        foreground_windows = iter((999, 700))

        with self.assertRaisesRegex(
            NitroSenseControlError,
            "did not visibly select Performance",
        ):
            apply_nitrosense_gaming_profile(
                probe_visual_state=make_probe_sequence(
                    unselected_probe,
                    unselected_probe,
                ),
                click=clicks.append,
                get_foreground_window=lambda: next(
                    foreground_windows
                ),
                restore_foreground_window=restored_windows.append,
                sleep=lambda _: None,
                monotonic=lambda: 0.0,
                enable_dpi=lambda: None,
                timeout_seconds=0.0,
            )

        self.assertEqual(
            clicks,
            [unselected_probe.performance_click_point],
        )
        self.assertEqual(restored_windows, [999])

    def test_rejects_negative_timeout_without_touching_nitrosense(self):
        with self.assertRaisesRegex(
            ValueError,
            "timeout_seconds",
        ):
            apply_nitrosense_gaming_profile(
                timeout_seconds=-0.1,
                enable_dpi=lambda: None,
            )


if __name__ == "__main__":
    unittest.main()