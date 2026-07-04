from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from skills.app_catalog import (
    CatalogApp,
    collapse_equivalent_shortcuts,
    find_exact_matches,
    normalise_name,
    scan_start_menu_shortcuts,
)


@dataclass(frozen=True)
class LaunchResult:
    """The honest result of one local app launch attempt."""

    success: bool
    display_name: str
    message: str


# These preserve convenient spoken aliases for common apps while the actual
# shortcut lookup remains exact and deterministic.
KNOWN_APP_ALIASES: dict[str, str] = {
    normalise_name("discord app"): normalise_name("discord"),
    normalise_name("vs code"): normalise_name("visual studio code"),
    normalise_name("vscode"): normalise_name("visual studio code"),
    normalise_name("chrome"): normalise_name("google chrome"),
    normalise_name("chrome browser"): normalise_name("google chrome"),
}


def resolve_catalog_matches(
    requested_name: str,
    *,
    catalog: Iterable[CatalogApp] | None = None,
) -> tuple[CatalogApp, ...]:
    """Find exact local Start Menu matches for one spoken app request."""
    entries = (
        tuple(catalog)
        if catalog is not None
        else scan_start_menu_shortcuts()
    )

    normalized_request = normalise_name(requested_name)

    if not normalized_request:
        return ()

    catalog_name = KNOWN_APP_ALIASES.get(
        normalized_request,
        normalized_request,
    )

    matches = find_exact_matches(catalog_name, entries)

    # Most apps have one shortcut, so avoid reading shortcut targets unless
    # duplicate names actually need resolving.
    if len(matches) <= 1:
        return matches

    return collapse_equivalent_shortcuts(matches)


def launch_catalog_app(
    requested_name: str,
    *,
    catalog: Iterable[CatalogApp] | None = None,
    startfile: Callable[[str], object] | None = None,
) -> LaunchResult:
    """Launch one exact Start Menu shortcut without shell commands.

    Zero matches are reported honestly. Multiple matches are refused rather
    than guessed. Only one exact match is allowed to launch.
    """
    matches = resolve_catalog_matches(
        requested_name,
        catalog=catalog,
    )

    display_name = requested_name.strip() or "that app"

    if not matches:
        return LaunchResult(
            success=False,
            display_name=display_name,
            message=(
                f"I could not find an exact Start Menu app named "
                f"{display_name}, sir."
            ),
        )

    if len(matches) > 1:
        return LaunchResult(
            success=False,
            display_name=matches[0].display_name,
            message=(
                f"I found {len(matches)} exact Start Menu shortcuts named "
                f"{matches[0].display_name}. I will not guess which one "
                "to open, sir."
            ),
        )

    app = matches[0]
    launcher = startfile or getattr(os, "startfile", None)

    if launcher is None:
        return LaunchResult(
            success=False,
            display_name=app.display_name,
            message=(
                "Local app launching is available only on Windows."
            ),
        )

    try:
        launcher(str(app.shortcut_path))
    except OSError as error:
        return LaunchResult(
            success=False,
            display_name=app.display_name,
            message=(
                f"I could not open {app.display_name}: {error}"
            ),
        )

    return LaunchResult(
        success=True,
        display_name=app.display_name,
        message=f"Opening {app.display_name}, sir.",
    )