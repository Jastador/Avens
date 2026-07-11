from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from skills.app_catalog import CatalogApp
from skills.app_launcher import resolve_catalog_matches
from skills.named_window import NamedWindowResult, control_named_window


@dataclass(frozen=True)
class AppWindowFocusResult:
    """Result of focusing one exact app window."""

    success: bool
    display_name: str
    message: str


def focus_app_window(
    app_name: str,
    *,
    resolve_app: Callable[
        [str],
        tuple[CatalogApp, ...],
    ] = resolve_catalog_matches,
    control_window: Callable[
        [CatalogApp, str],
        NamedWindowResult,
    ] = control_named_window,
) -> AppWindowFocusResult:
    """Bring one exact app window to the foreground."""
    requested_name = app_name.strip()

    if not requested_name:
        return AppWindowFocusResult(
            success=False,
            display_name="that app",
            message="I cannot focus an empty app name, sir.",
        )

    matches = resolve_app(requested_name)

    if not matches:
        return AppWindowFocusResult(
            success=False,
            display_name=requested_name,
            message=(
                f"I could not find an exact local app named "
                f"{requested_name}, sir."
            ),
        )

    display_name = matches[0].display_name

    if len(matches) > 1:
        return AppWindowFocusResult(
            success=False,
            display_name=display_name,
            message=(
                f"I found {len(matches)} exact local apps named "
                f"{display_name}. I will not guess which one to "
                "bring to the foreground, sir."
            ),
        )

    result = control_window(matches[0], "bring_up")

    return AppWindowFocusResult(
        success=result.success,
        display_name=display_name,
        message=result.message,
    )