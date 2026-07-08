from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final


if __package__ in (None, ""):
    sys.path.insert(
        0,
        str(Path(__file__).resolve().parents[1]),
    )

import win32api
import win32con
import win32gui

from tools.inspect_nitrosense_visual import (
    NitroSenseVisualProbe,
    enable_dpi_awareness,
    probe_nitrosense_visual_state,
    restore_window,
)


DEFAULT_TIMEOUT_SECONDS: Final = 3.0
DEFAULT_POLL_INTERVAL_SECONDS: Final = 0.20


class NitroSenseControlError(RuntimeError):
    """Raised when the approved NitroSense action cannot be verified."""


@dataclass(frozen=True)
class NitroSenseGamingProfileReport:
    """Verified result of applying the approved gaming profile."""

    performance_changed: bool
    fan_max_changed: bool
    performance_selected: bool
    fan_max_selected: bool


ProbeVisualState = Callable[..., NitroSenseVisualProbe]
ClickScreenPoint = Callable[[tuple[int, int]], None]
GetForegroundWindow = Callable[[], int]
RestoreWindow = Callable[[int], None]
Sleep = Callable[[float], None]
Monotonic = Callable[[], float]
EnableDpiAwareness = Callable[[], None]


def get_virtual_desktop_bounds() -> tuple[int, int, int, int]:
    """Return the physical pixel bounds of the virtual desktop."""
    left = win32api.GetSystemMetrics(
        win32con.SM_XVIRTUALSCREEN
    )
    top = win32api.GetSystemMetrics(
        win32con.SM_YVIRTUALSCREEN
    )
    width = win32api.GetSystemMetrics(
        win32con.SM_CXVIRTUALSCREEN
    )
    height = win32api.GetSystemMetrics(
        win32con.SM_CYVIRTUALSCREEN
    )

    return left, top, left + width, top + height


def validate_screen_point(
    point: tuple[int, int],
) -> None:
    """Reject an approved click point outside the physical desktop."""
    left, top, right, bottom = get_virtual_desktop_bounds()
    horizontal, vertical = point

    if not (
        left <= horizontal < right
        and top <= vertical < bottom
    ):
        raise NitroSenseControlError(
            "Approved NitroSense click point falls outside the "
            "physical desktop."
        )


def click_screen_point(
    point: tuple[int, int],
) -> None:
    """Click one already-validated physical desktop point."""
    validate_screen_point(point)
    win32api.SetCursorPos(point)
    time.sleep(0.05)
    win32api.mouse_event(
        win32con.MOUSEEVENTF_LEFTDOWN,
        0,
        0,
        0,
        0,
    )
    win32api.mouse_event(
        win32con.MOUSEEVENTF_LEFTUP,
        0,
        0,
        0,
        0,
    )


def _wait_for_selected_state(
    *,
    label: str,
    expected_window_handle: int,
    selection_is_active: Callable[[NitroSenseVisualProbe], bool],
    probe_visual_state: ProbeVisualState,
    timeout_seconds: float,
    poll_interval_seconds: float,
    sleep: Sleep,
    monotonic: Monotonic,
) -> NitroSenseVisualProbe:
    """Wait until one clicked NitroSense option is visibly selected."""
    deadline = monotonic() + timeout_seconds

    while True:
        probe = probe_visual_state(
            restore_previous_foreground=False,
        )

        if probe.window.hwnd != expected_window_handle:
            raise NitroSenseControlError(
                "NitroSense changed windows while the approved "
                "setting was being verified."
            )

        if selection_is_active(probe):
            return probe

        if monotonic() >= deadline:
            raise NitroSenseControlError(
                f"NitroSense did not visibly select {label}."
            )

        remaining_seconds = deadline - monotonic()
        sleep(
            min(
                poll_interval_seconds,
                remaining_seconds,
            )
        )


def _ensure_selected_state(
    *,
    label: str,
    initial_probe: NitroSenseVisualProbe,
    click_point: tuple[int, int],
    selection_is_active: Callable[[NitroSenseVisualProbe], bool],
    probe_visual_state: ProbeVisualState,
    click: ClickScreenPoint,
    get_foreground_window: GetForegroundWindow,
    timeout_seconds: float,
    poll_interval_seconds: float,
    sleep: Sleep,
    monotonic: Monotonic,
) -> tuple[NitroSenseVisualProbe, bool]:
    """Select one known option only when it is not already selected."""
    if selection_is_active(initial_probe):
        return initial_probe, False

    if get_foreground_window() != initial_probe.window.hwnd:
        raise NitroSenseControlError(
            "NitroSense lost foreground before its approved "
            "control could be clicked."
        )

    click(click_point)

    verified_probe = _wait_for_selected_state(
        label=label,
        expected_window_handle=initial_probe.window.hwnd,
        selection_is_active=selection_is_active,
        probe_visual_state=probe_visual_state,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        sleep=sleep,
        monotonic=monotonic,
    )

    return verified_probe, True


def apply_nitrosense_gaming_profile(
    *,
    probe_visual_state: ProbeVisualState = (
        probe_nitrosense_visual_state
    ),
    click: ClickScreenPoint = click_screen_point,
    get_foreground_window: GetForegroundWindow = (
        win32gui.GetForegroundWindow
    ),
    restore_foreground_window: RestoreWindow = restore_window,
    sleep: Sleep = time.sleep,
    monotonic: Monotonic = time.monotonic,
    enable_dpi: EnableDpiAwareness = enable_dpi_awareness,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = (
        DEFAULT_POLL_INTERVAL_SECONDS
    ),
) -> NitroSenseGamingProfileReport:
    """Enable only the verified Performance and Fan Max controls."""
    if timeout_seconds < 0:
        raise ValueError(
            "timeout_seconds must be zero or greater."
        )

    if poll_interval_seconds <= 0:
        raise ValueError(
            "poll_interval_seconds must be greater than zero."
        )

    enable_dpi()
    previous_foreground_window = get_foreground_window()

    try:
        initial_probe = probe_visual_state(
            restore_previous_foreground=False,
        )

        after_performance_probe, performance_changed = (
            _ensure_selected_state(
                label="Performance",
                initial_probe=initial_probe,
                click_point=(
                    initial_probe.performance_click_point
                ),
                selection_is_active=(
                    lambda probe: probe.performance.selected
                ),
                probe_visual_state=probe_visual_state,
                click=click,
                get_foreground_window=get_foreground_window,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                sleep=sleep,
                monotonic=monotonic,
            )
        )

        final_probe, fan_max_changed = _ensure_selected_state(
            label="Fan Max",
            initial_probe=after_performance_probe,
            click_point=after_performance_probe.fan_max_click_point,
            selection_is_active=(
                lambda probe: probe.fan_max.selected
            ),
            probe_visual_state=probe_visual_state,
            click=click,
            get_foreground_window=get_foreground_window,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            sleep=sleep,
            monotonic=monotonic,
        )

        if not final_probe.performance.selected:
            raise NitroSenseControlError(
                "NitroSense no longer shows Performance selected."
            )

        if not final_probe.fan_max.selected:
            raise NitroSenseControlError(
                "NitroSense no longer shows Fan Max selected."
            )

        return NitroSenseGamingProfileReport(
            performance_changed=performance_changed,
            fan_max_changed=fan_max_changed,
            performance_selected=final_probe.performance.selected,
            fan_max_selected=final_probe.fan_max.selected,
        )
    finally:
        restore_foreground_window(previous_foreground_window)


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit command-line interface."""
    parser = argparse.ArgumentParser(
        description=(
            "Apply only NitroSense Performance mode and Fan Max, "
            "with visual verification."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Click the two approved controls after safety checks.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=(
            "Seconds to wait for each visible state verification. "
            f"Default: {DEFAULT_TIMEOUT_SECONDS}."
        ),
    )
    return parser


def _format_changed(changed: bool) -> str:
    """Return a stable human-readable action status."""
    if changed:
        return "changed"

    return "already selected"


def main(
    arguments: Sequence[str] | None = None,
) -> int:
    """Run a status check or one explicit, verified apply action."""
    parser = build_parser()
    parsed = parser.parse_args(arguments)

    if not parsed.apply:
        try:
            probe = probe_nitrosense_visual_state()
        except RuntimeError as error:
            print(f"NitroSense gaming profile status failed: {error}")
            return 1

        print("NitroSense gaming profile status")
        print(
            f"Performance selected: {probe.performance.selected}"
        )
        print(f"Fan Max selected: {probe.fan_max.selected}")
        print(
            "No settings were changed. Re-run with --apply to "
            "click only the approved controls."
        )
        return 0

    try:
        report = apply_nitrosense_gaming_profile(
            timeout_seconds=parsed.timeout,
        )
    except (NitroSenseControlError, RuntimeError) as error:
        print(f"NitroSense gaming profile failed: {error}")
        return 1

    print("NitroSense gaming profile applied")
    print(
        "Performance: "
        f"{_format_changed(report.performance_changed)}"
    )
    print(
        "Fan Max: "
        f"{_format_changed(report.fan_max_changed)}"
    )
    print(
        "Visual verification: "
        f"Performance={report.performance_selected} | "
        f"Fan Max={report.fan_max_selected}"
    )
    print("Previous foreground window restoration was requested.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())