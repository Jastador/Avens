from __future__ import annotations

import ctypes
import time
from dataclasses import dataclass
from typing import Final

import numpy as np
import win32con
import win32gui
from PIL import Image, ImageGrab


NITROSENSE_WINDOW_TITLE: Final = "NitroSense"
NITROSENSE_CLASS_PREFIX: Final = (
    "HwndWrapper[NitroSense.exe"
)

MIN_NITROSENSE_WIDTH: Final = 1000
MIN_NITROSENSE_HEIGHT: Final = 650

EXPECTED_ASPECT_RATIO: Final = 1320 / 760
ASPECT_RATIO_TOLERANCE: Final = 0.12

MIN_SELECTED_RED_PIXELS: Final = 100
MIN_SELECTED_RED_DENSITY: Final = 0.003

FAN_MAX_SELECTION_REGION: Final = (
    0.08,
    0.29,
    0.27,
    0.40,
)

PERFORMANCE_SELECTION_REGION: Final = (
    0.08,
    0.80,
    0.32,
    0.91,
)

FAN_MAX_CLICK_ANCHOR: Final = (
    0.155,
    0.345,
)

PERFORMANCE_CLICK_ANCHOR: Final = (
    0.155,
    0.865,
)


@dataclass(frozen=True)
class WindowRect:
    """One visible native NitroSense window."""

    hwnd: int
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        """Return the native window width."""
        return self.right - self.left

    @property
    def height(self) -> int:
        """Return the native window height."""
        return self.bottom - self.top

def read_window_rect(hwnd: int) -> WindowRect:
    """Read the current native rectangle for one existing window."""
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError("NitroSense window no longer exists.")

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)

    return WindowRect(
        hwnd=hwnd,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
    )

@dataclass(frozen=True)
class SelectionSignal:
    """Visual evidence for one selected NitroSense option."""

    red_pixels: int
    total_pixels: int
    red_density: float
    selected: bool


@dataclass(frozen=True)
class NitroSenseVisualProbe:
    """Read-only visual state for the NitroSense main window."""

    window: WindowRect
    fan_max: SelectionSignal
    performance: SelectionSignal
    fan_max_click_point: tuple[int, int]
    performance_click_point: tuple[int, int]


def enable_dpi_awareness() -> None:
    """Use physical desktop pixels for Win32 and screenshot coordinates."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def find_nitrosense_window() -> WindowRect:
    """Find exactly one visible NitroSense native window."""
    matches: list[WindowRect] = []

    def visit_window(hwnd: int, _: object) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return

        title = win32gui.GetWindowText(hwnd).strip()
        class_name = win32gui.GetClassName(hwnd)

        if title != NITROSENSE_WINDOW_TITLE:
            return

        if not class_name.startswith(NITROSENSE_CLASS_PREFIX):
            return

        matches.append(read_window_rect(hwnd))

    win32gui.EnumWindows(visit_window, None)

    if len(matches) != 1:
        raise RuntimeError(
            "Expected exactly one visible NitroSense window, "
            f"found {len(matches)}."
        )

    return matches[0]


def validate_window_layout(window: WindowRect) -> None:
    """Reject a window whose size is unsafe for this known layout."""
    if window.width < MIN_NITROSENSE_WIDTH:
        raise RuntimeError(
            "NitroSense window is too narrow for the approved layout."
        )

    if window.height < MIN_NITROSENSE_HEIGHT:
        raise RuntimeError(
            "NitroSense window is too short for the approved layout."
        )

    aspect_ratio = window.width / window.height

    if abs(aspect_ratio - EXPECTED_ASPECT_RATIO) > ASPECT_RATIO_TOLERANCE:
        raise RuntimeError(
            "NitroSense window aspect ratio does not match the "
            "approved layout."
        )


def activate_window(hwnd: int) -> None:
    """Bring one known window forward without clicking inside it."""
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError("NitroSense window no longer exists.")

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    else:
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

    win32gui.BringWindowToTop(hwnd)
    win32gui.SetForegroundWindow(hwnd)

    time.sleep(0.35)

    if win32gui.GetForegroundWindow() != hwnd:
        raise RuntimeError(
            "NitroSense could not be brought to the foreground."
        )


def restore_window(hwnd: int) -> None:
    """Best-effort restoration of the window focused before probing."""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return

    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass


def capture_window_image(window: WindowRect) -> Image.Image:
    """Capture only the current NitroSense window pixels."""
    image = ImageGrab.grab(
        bbox=(
            window.left,
            window.top,
            window.right,
            window.bottom,
        ),
        all_screens=True,
    ).convert("RGB")

    if image.size != (window.width, window.height):
        raise RuntimeError(
            "NitroSense screenshot size did not match its window size."
        )

    return image


def normalized_region_to_box(
    region: tuple[float, float, float, float],
    *,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    """Convert one approved normalized region to pixel coordinates."""
    left_fraction, top_fraction, right_fraction, bottom_fraction = region

    if not (
        0 <= left_fraction < right_fraction <= 1
        and 0 <= top_fraction < bottom_fraction <= 1
    ):
        raise ValueError("Normalized region must stay inside the window.")

    left = round(left_fraction * width)
    top = round(top_fraction * height)
    right = round(right_fraction * width)
    bottom = round(bottom_fraction * height)

    if right <= left or bottom <= top:
        raise ValueError("Normalized region resolved to an empty box.")

    return left, top, right, bottom


def measure_selected_red(
    image: Image.Image,
    *,
    region: tuple[float, float, float, float],
) -> SelectionSignal:
    """Measure red selected-state pixels inside one approved region."""
    pixel_box = normalized_region_to_box(
        region,
        width=image.width,
        height=image.height,
    )
    cropped_image = image.crop(pixel_box)

    pixels = np.asarray(cropped_image, dtype=np.int16)
    red = pixels[:, :, 0]
    green = pixels[:, :, 1]
    blue = pixels[:, :, 2]

    selected_red_mask = (
        (red >= 130)
        & (red - green >= 70)
        & (red - blue >= 70)
    )

    red_pixels = int(selected_red_mask.sum())
    total_pixels = int(selected_red_mask.size)
    red_density = red_pixels / total_pixels

    return SelectionSignal(
        red_pixels=red_pixels,
        total_pixels=total_pixels,
        red_density=red_density,
        selected=(
            red_pixels >= MIN_SELECTED_RED_PIXELS
            and red_density >= MIN_SELECTED_RED_DENSITY
        ),
    )


def normalized_anchor_to_screen(
    anchor: tuple[float, float],
    *,
    window: WindowRect,
) -> tuple[int, int]:
    """Convert one approved normalized anchor to a screen point."""
    horizontal_fraction, vertical_fraction = anchor

    if not (
        0 <= horizontal_fraction <= 1
        and 0 <= vertical_fraction <= 1
    ):
        raise ValueError("Normalized anchor must stay inside the window.")

    return (
        window.left + round(horizontal_fraction * window.width),
        window.top + round(vertical_fraction * window.height),
    )


def probe_nitrosense_visual_state(
    *,
    restore_previous_foreground: bool = True,
) -> NitroSenseVisualProbe:
    """Read NitroSense selected states without changing app settings."""
    enable_dpi_awareness()

    window = find_nitrosense_window()

    previous_foreground_window = win32gui.GetForegroundWindow()

    try:
        activate_window(window.hwnd)
        window = read_window_rect(window.hwnd)
        validate_window_layout(window)
        image = capture_window_image(window)
    finally:
        if (
            restore_previous_foreground
            and previous_foreground_window != window.hwnd
        ):
            restore_window(previous_foreground_window)

    return NitroSenseVisualProbe(
        window=window,
        fan_max=measure_selected_red(
            image,
            region=FAN_MAX_SELECTION_REGION,
        ),
        performance=measure_selected_red(
            image,
            region=PERFORMANCE_SELECTION_REGION,
        ),
        fan_max_click_point=normalized_anchor_to_screen(
            FAN_MAX_CLICK_ANCHOR,
            window=window,
        ),
        performance_click_point=normalized_anchor_to_screen(
            PERFORMANCE_CLICK_ANCHOR,
            window=window,
        ),
    )

def format_signal(
    label: str,
    signal: SelectionSignal,
) -> str:
    """Format one visual state signal for terminal output."""
    return (
        f"{label}: selected={signal.selected} | "
        f"red_pixels={signal.red_pixels}/{signal.total_pixels} | "
        f"red_density={signal.red_density:.4f}"
    )


def main() -> int:
    """Run the read-only NitroSense visual probe."""
    try:
        probe = probe_nitrosense_visual_state()
    except RuntimeError as error:
        print(f"NitroSense visual probe failed: {error}")
        return 1

    print("NitroSense visual probe")
    print(
        "Read-only: no clicks, typing, launches, or settings changes."
    )
    print(
        "Window: "
        f"hwnd=0x{probe.window.hwnd:08X} | "
        f"rect=({probe.window.left}, {probe.window.top}, "
        f"{probe.window.width}, {probe.window.height})"
    )
    print(format_signal("Fan Max", probe.fan_max))
    print(format_signal("Performance", probe.performance))
    print(
        "Approved future click anchors, not used by this probe:"
    )
    print(f"- Fan Max: {probe.fan_max_click_point}")
    print(
        f"- Performance: {probe.performance_click_point}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())