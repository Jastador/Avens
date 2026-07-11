from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from skills.app_catalog import CatalogApp
from skills.app_launcher import resolve_catalog_matches
from skills.named_window import (
    NamedWindowMatchResult,
    inspect_named_app_windows,
)


DEFAULT_APP_WINDOW_WAIT_TIMEOUT_SECONDS: Final = 10.0
DEFAULT_APP_WINDOW_WAIT_POLL_SECONDS: Final = 0.25


@dataclass(frozen=True)
class AppWindowWaitResult:
    """Result of waiting for one exact app window."""

    success: bool
    display_name: str
    window_count: int
    message: str


def _format_timeout_seconds(timeout_seconds: float) -> str:
    """Format timeout seconds without noisy decimals when possible."""
    if timeout_seconds.is_integer():
        return str(int(timeout_seconds))

    return f"{timeout_seconds:.1f}"


def wait_for_app_window(
    app_name: str,
    *,
    resolve_app: Callable[
        [str],
        tuple[CatalogApp, ...],
    ] = resolve_catalog_matches,
    inspect_windows: Callable[
        [CatalogApp],
        NamedWindowMatchResult,
    ] = inspect_named_app_windows,
    sleep: Callable[[float], object] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    timeout_seconds: float = DEFAULT_APP_WINDOW_WAIT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_APP_WINDOW_WAIT_POLL_SECONDS,
) -> AppWindowWaitResult:
    """Wait until one exact app has at least one visible matching window."""
    requested_name = app_name.strip()

    if not requested_name:
        return AppWindowWaitResult(
            success=False,
            display_name="that app",
            window_count=0,
            message="I cannot verify an empty app name, sir.",
        )

    if timeout_seconds < 0:
        raise ValueError("timeout_seconds must be zero or greater.")

    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be greater than zero.")

    matches = resolve_app(requested_name)

    if not matches:
        return AppWindowWaitResult(
            success=False,
            display_name=requested_name,
            window_count=0,
            message=(
                f"I could not find an exact local app named "
                f"{requested_name}, sir."
            ),
        )

    display_name = matches[0].display_name

    if len(matches) > 1:
        return AppWindowWaitResult(
            success=False,
            display_name=display_name,
            window_count=0,
            message=(
                f"I found {len(matches)} exact local apps named "
                f"{display_name}. I will not guess which one to "
                "verify, sir."
            ),
        )

    app = matches[0]
    deadline = monotonic() + timeout_seconds

    while True:
        match_result = inspect_windows(app)

        if match_result.error_message is not None:
            return AppWindowWaitResult(
                success=False,
                display_name=match_result.display_name,
                window_count=0,
                message=match_result.error_message,
            )

        window_count = len(match_result.window_handles)

        if window_count:
            window_word = "window" if window_count == 1 else "windows"

            return AppWindowWaitResult(
                success=True,
                display_name=match_result.display_name,
                window_count=window_count,
                message=(
                    f"{match_result.display_name} is open "
                    f"with {window_count} verified {window_word}, sir."
                ),
            )

        if monotonic() >= deadline:
            timeout_text = _format_timeout_seconds(timeout_seconds)

            return AppWindowWaitResult(
                success=False,
                display_name=match_result.display_name,
                window_count=0,
                message=(
                    f"{match_result.display_name} did not open a "
                    f"verified window within {timeout_text} seconds, sir."
                ),
            )

        remaining_seconds = deadline - monotonic()
        sleep(
            min(
                poll_interval_seconds,
                remaining_seconds,
            )
        )