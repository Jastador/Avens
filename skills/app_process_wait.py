from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Final

import psutil

from skills.app_catalog import (
    CatalogApp,
    resolve_catalog_launch_target,
)
from skills.app_launcher import resolve_catalog_matches


DEFAULT_APP_PROCESS_WAIT_TIMEOUT_SECONDS: Final = 10.0
DEFAULT_APP_PROCESS_WAIT_POLL_SECONDS: Final = 0.25


@dataclass(frozen=True)
class AppProcessWaitResult:
    """Result of waiting for one exact app process."""

    success: bool
    display_name: str
    process_count: int
    message: str


def _normalise_process_path(path: str) -> str:
    """Make process paths safe for exact comparison."""
    return os.path.normcase(os.path.normpath(path.strip()))


def _list_process_executable_paths() -> tuple[str, ...]:
    """Return visible process executable paths without raising per process."""
    paths: list[str] = []

    for process in psutil.process_iter(["exe"]):
        try:
            executable_path = process.info.get("exe")
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue

        if isinstance(executable_path, str) and executable_path.strip():
            paths.append(executable_path)

    return tuple(paths)


def _format_timeout_seconds(timeout_seconds: float) -> str:
    """Format timeout seconds without noisy decimals when possible."""
    if timeout_seconds.is_integer():
        return str(int(timeout_seconds))

    return f"{timeout_seconds:.1f}"


def _count_exact_process_matches(
    target_path: str,
    process_paths: Iterable[str],
) -> int:
    """Count running processes matching one exact executable path."""
    normalized_target = _normalise_process_path(target_path)

    return sum(
        1
        for process_path in process_paths
        if _normalise_process_path(process_path) == normalized_target
    )


def wait_for_app_process(
    app_name: str,
    *,
    resolve_app: Callable[
        [str],
        tuple[CatalogApp, ...],
    ] = resolve_catalog_matches,
    resolve_launch_target: Callable[
        [CatalogApp],
        object,
    ] = resolve_catalog_launch_target,
    list_process_paths: Callable[
        [],
        tuple[str, ...],
    ] = _list_process_executable_paths,
    sleep: Callable[[float], object] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    timeout_seconds: float = DEFAULT_APP_PROCESS_WAIT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_APP_PROCESS_WAIT_POLL_SECONDS,
) -> AppProcessWaitResult:
    """Wait until one exact app launch target has a running process."""
    requested_name = app_name.strip()

    if not requested_name:
        return AppProcessWaitResult(
            success=False,
            display_name="that app",
            process_count=0,
            message="I cannot verify an empty app name, sir.",
        )

    if timeout_seconds < 0:
        raise ValueError("timeout_seconds must be zero or greater.")

    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be greater than zero.")

    matches = resolve_app(requested_name)

    if not matches:
        return AppProcessWaitResult(
            success=False,
            display_name=requested_name,
            process_count=0,
            message=(
                f"I could not find an exact local app named "
                f"{requested_name}, sir."
            ),
        )

    display_name = matches[0].display_name

    if len(matches) > 1:
        return AppProcessWaitResult(
            success=False,
            display_name=display_name,
            process_count=0,
            message=(
                f"I found {len(matches)} exact local apps named "
                f"{display_name}. I will not guess which one to "
                "verify, sir."
            ),
        )

    app = matches[0]
    launch_target = resolve_launch_target(app)

    target_path = getattr(launch_target, "target_path", "")

    if not isinstance(target_path, str) or not target_path.strip():
        return AppProcessWaitResult(
            success=False,
            display_name=display_name,
            process_count=0,
            message=(
                f"I could not safely identify the process target for "
                f"{display_name}, sir."
            ),
        )

    deadline = monotonic() + timeout_seconds

    while True:
        process_count = _count_exact_process_matches(
            target_path,
            list_process_paths(),
        )

        if process_count:
            process_word = "process" if process_count == 1 else "processes"

            return AppProcessWaitResult(
                success=True,
                display_name=display_name,
                process_count=process_count,
                message=(
                    f"{display_name} is running with {process_count} "
                    f"verified {process_word}, sir."
                ),
            )

        if monotonic() >= deadline:
            timeout_text = _format_timeout_seconds(timeout_seconds)

            return AppProcessWaitResult(
                success=False,
                display_name=display_name,
                process_count=0,
                message=(
                    f"{display_name} did not start a verified process "
                    f"within {timeout_text} seconds, sir."
                ),
            )

        remaining_seconds = deadline - monotonic()
        sleep(min(poll_interval_seconds, remaining_seconds))