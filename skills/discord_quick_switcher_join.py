from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import pyautogui

from skills.app_window_focus import (
    AppWindowFocusResult,
    focus_app_window,
)
from skills.discord_voice_config import (
    DiscordVoiceConfigError,
    DiscordVoiceTarget,
    get_discord_voice_target,
)


DISCORD_APP_NAME: Final = "Discord"
DEFAULT_AFTER_FOCUS_DELAY_SECONDS: Final = 2.0
DEFAULT_AFTER_HOTKEY_DELAY_SECONDS: Final = 0.25
DEFAULT_AFTER_TYPE_DELAY_SECONDS: Final = 0.10
DEFAULT_TYPE_INTERVAL_SECONDS: Final = 0.01


@dataclass(frozen=True)
class DiscordQuickSwitcherJoinResult:
    """Result of sending a Discord Quick Switcher join command."""

    success: bool
    alias: str
    target: DiscordVoiceTarget | None
    message: str


def _focus_discord_window() -> AppWindowFocusResult:
    """Bring the exact Discord app window to the foreground."""
    return focus_app_window(DISCORD_APP_NAME)


def _validate_delay(
    value: float,
    *,
    label: str,
) -> float:
    """Validate one automation delay."""
    if value < 0:
        raise ValueError(f"{label} must be zero or greater.")

    return value


def send_discord_quick_switcher_join_command(
    target_alias: str,
    *,
    get_target: Callable[
        [str],
        DiscordVoiceTarget,
    ] = get_discord_voice_target,
    focus_discord: Callable[[], AppWindowFocusResult] = (
        _focus_discord_window
    ),
    hotkey: Callable[..., object] = pyautogui.hotkey,
    write_text: Callable[..., object] = pyautogui.write,
    press_key: Callable[[str], object] = pyautogui.press,
    sleep: Callable[[float], object] = time.sleep,
    after_focus_delay_seconds: float = (
        DEFAULT_AFTER_FOCUS_DELAY_SECONDS
    ),
    after_hotkey_delay_seconds: float = (
        DEFAULT_AFTER_HOTKEY_DELAY_SECONDS
    ),
    after_type_delay_seconds: float = (
        DEFAULT_AFTER_TYPE_DELAY_SECONDS
    ),
    type_interval_seconds: float = DEFAULT_TYPE_INTERVAL_SECONDS,
) -> DiscordQuickSwitcherJoinResult:
    """Send a guarded Discord Quick Switcher join command."""
    requested_alias = target_alias.strip()

    if not requested_alias:
        return DiscordQuickSwitcherJoinResult(
            success=False,
            alias="",
            target=None,
            message="Discord voice target alias cannot be empty, sir.",
        )

    _validate_delay(
        after_focus_delay_seconds,
        label="after_focus_delay_seconds",
    )
    _validate_delay(
        after_hotkey_delay_seconds,
        label="after_hotkey_delay_seconds",
    )
    _validate_delay(
        after_type_delay_seconds,
        label="after_type_delay_seconds",
    )
    _validate_delay(
        type_interval_seconds,
        label="type_interval_seconds",
    )

    try:
        target = get_target(requested_alias)
    except DiscordVoiceConfigError as error:
        return DiscordQuickSwitcherJoinResult(
            success=False,
            alias=requested_alias,
            target=None,
            message=str(error),
        )

    quick_switcher_query = target.quick_switcher_query

    if quick_switcher_query is None or not quick_switcher_query.strip():
        return DiscordQuickSwitcherJoinResult(
            success=False,
            alias=target.alias,
            target=target,
            message=(
                f"Discord voice target '{target.alias}' does not "
                "define quick_switcher_query, sir."
            ),
        )

    focus_result = focus_discord()

    if not focus_result.success:
        return DiscordQuickSwitcherJoinResult(
            success=False,
            alias=target.alias,
            target=target,
            message=(
                "I could not focus Discord before using Quick "
                f"Switcher: {focus_result.message}"
            ),
        )

    try:
        sleep(after_focus_delay_seconds)
        hotkey("ctrl", "k")
        sleep(after_hotkey_delay_seconds)
        write_text(
            quick_switcher_query.strip(),
            interval=type_interval_seconds,
        )
        sleep(after_type_delay_seconds)
        press_key("enter")
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        pyautogui.PyAutoGUIException,
    ) as error:
        return DiscordQuickSwitcherJoinResult(
            success=False,
            alias=target.alias,
            target=target,
            message=(
                "I could not send Discord Quick Switcher keys "
                f"safely: {error}"
            ),
        )

    return DiscordQuickSwitcherJoinResult(
        success=True,
        alias=target.alias,
        target=target,
        message=(
            "Discord Quick Switcher join command sent for "
            f"'{quick_switcher_query.strip()}', sir."
        ),
    )