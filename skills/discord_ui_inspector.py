from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import pywintypes
import win32gui

from skills.app_catalog import CatalogApp
from skills.app_launcher import resolve_catalog_matches
from skills.named_window import (
    NamedWindowMatchResult,
    inspect_named_app_windows,
)


DISCORD_APP_NAME: Final = "Discord"


@dataclass(frozen=True)
class DiscordWindowSnapshot:
    """Read-only snapshot of one verified Discord window."""

    window_handle: int
    title: str
    is_foreground: bool


@dataclass(frozen=True)
class DiscordUiInspection:
    """Read-only Discord UI inspection result."""

    success: bool
    display_name: str
    window_count: int
    windows: tuple[DiscordWindowSnapshot, ...]
    message: str


def _read_window_title(
    window_handle: int,
    *,
    get_window_title: Callable[[int], str],
) -> str:
    """Read one window title without letting Win32 errors escape."""
    try:
        title = get_window_title(window_handle)
    except (OSError, pywintypes.error):
        return ""

    if not isinstance(title, str):
        return ""

    return title.strip()


def _is_foreground_window(
    window_handle: int,
    *,
    get_foreground_window: Callable[[], int],
) -> bool:
    """Return whether one window is currently foreground."""
    try:
        foreground_window = int(get_foreground_window())
    except (OSError, pywintypes.error, TypeError, ValueError):
        return False

    return foreground_window == window_handle


def inspect_discord_ui(
    *,
    resolve_app: Callable[
        [str],
        tuple[CatalogApp, ...],
    ] = resolve_catalog_matches,
    inspect_windows: Callable[
        [CatalogApp],
        NamedWindowMatchResult,
    ] = inspect_named_app_windows,
    get_window_title: Callable[[int], str] = win32gui.GetWindowText,
    get_foreground_window: Callable[[], int] = win32gui.GetForegroundWindow,
) -> DiscordUiInspection:
    """Inspect verified Discord windows without controlling Discord."""
    matches = resolve_app(DISCORD_APP_NAME)

    if not matches:
        return DiscordUiInspection(
            success=False,
            display_name=DISCORD_APP_NAME,
            window_count=0,
            windows=(),
            message=(
                "I could not find an exact local app named "
                "Discord, sir."
            ),
        )

    display_name = matches[0].display_name

    if len(matches) > 1:
        return DiscordUiInspection(
            success=False,
            display_name=display_name,
            window_count=0,
            windows=(),
            message=(
                f"I found {len(matches)} exact local apps named "
                f"{display_name}. I will not guess which one to "
                "inspect, sir."
            ),
        )

    window_match = inspect_windows(matches[0])

    if window_match.error_message is not None:
        return DiscordUiInspection(
            success=False,
            display_name=window_match.display_name,
            window_count=0,
            windows=(),
            message=window_match.error_message,
        )

    if not window_match.window_handles:
        return DiscordUiInspection(
            success=False,
            display_name=window_match.display_name,
            window_count=0,
            windows=(),
            message=(
                f"{window_match.display_name} is not open with a "
                "verified window, sir."
            ),
        )

    windows = tuple(
        DiscordWindowSnapshot(
            window_handle=window_handle,
            title=_read_window_title(
                window_handle,
                get_window_title=get_window_title,
            ),
            is_foreground=_is_foreground_window(
                window_handle,
                get_foreground_window=get_foreground_window,
            ),
        )
        for window_handle in window_match.window_handles
    )

    window_count = len(windows)
    window_word = "window" if window_count == 1 else "windows"
    foreground_count = sum(
        1 for window in windows if window.is_foreground
    )

    if foreground_count == 1:
        foreground_message = (
            "One verified Discord window is currently foreground, sir."
        )
    elif foreground_count > 1:
        foreground_message = (
            f"{foreground_count} verified Discord windows are marked "
            "foreground, sir."
        )
    else:
        foreground_message = (
            "No verified Discord window is currently foreground, sir."
        )

    return DiscordUiInspection(
        success=True,
        display_name=window_match.display_name,
        window_count=window_count,
        windows=windows,
        message=(
            f"Discord UI inspection found {window_count} verified "
            f"{window_word}. {foreground_message}"
        ),
    )


def format_discord_ui_inspection(
    inspection: DiscordUiInspection,
) -> str:
    """Format one Discord UI inspection for console output."""
    status = "success" if inspection.success else "failed"

    lines = [
        "Discord UI inspection:",
        f"Status: {status}",
        f"Message: {inspection.message}",
    ]

    if inspection.windows:
        lines.append("Windows:")

        for window in inspection.windows:
            title = window.title or "<untitled>"
            foreground = "yes" if window.is_foreground else "no"

            lines.append(
                f"- {window.window_handle:#x} | "
                f"foreground={foreground} | "
                f"title={title}"
            )

    return "\n".join(lines)