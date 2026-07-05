from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pywintypes
import win32con
import win32gui


@dataclass(frozen=True)
class ActiveWindowResult:
    """Result of one explicit focused-window state change."""

    success: bool
    message: str


_SHOW_COMMANDS = {
    "minimize": win32con.SW_MINIMIZE,
    "maximize": win32con.SW_MAXIMIZE,
    "restore": win32con.SW_RESTORE,
}

_SUCCESS_MESSAGES = {
    "minimize": "Minimized the focused window, sir.",
    "maximize": "Maximized the focused window, sir.",
    "restore": "Restored the focused window, sir.",
}


def control_active_window(
    action: str,
    *,
    get_foreground_window: Callable[[], int] = (
        win32gui.GetForegroundWindow
    ),
    is_window: Callable[[int], bool] = win32gui.IsWindow,
    show_window: Callable[[int, int], object] = win32gui.ShowWindow,
) -> ActiveWindowResult:
    """Apply one allowlisted state change to the focused window."""

    action_key = action.strip().lower()
    show_command = _SHOW_COMMANDS.get(action_key)

    if show_command is None:
        return ActiveWindowResult(
            success=False,
            message="I cannot perform that active-window action, sir.",
        )

    try:
        window_handle = get_foreground_window()

        if not window_handle or not is_window(window_handle):
            return ActiveWindowResult(
                success=False,
                message=(
                    f"I could not find a focused window to "
                    f"{action_key}, sir."
                ),
            )

        show_window(window_handle, show_command)

    except (OSError, pywintypes.error):
        return ActiveWindowResult(
            success=False,
            message=(
                f"I could not {action_key} the focused window, sir."
            ),
        )

    return ActiveWindowResult(
        success=True,
        message=_SUCCESS_MESSAGES[action_key],
    )