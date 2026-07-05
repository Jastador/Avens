from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from skills.app_catalog import (
    CatalogApp,
    collapse_equivalent_catalog_apps,
    find_exact_matches,
    get_catalog_launch_reference,
    normalise_name,
    scan_local_app_catalog,
    scan_packaged_apps,
)


@dataclass(frozen=True)
class LaunchResult:
    """The honest result of one local app launch attempt."""

    success: bool
    display_name: str
    message: str


KNOWN_APP_ALIASES: dict[str, str] = {
    normalise_name("discord app"): normalise_name("discord"),
    normalise_name("vs code"): normalise_name("visual studio code"),
    normalise_name("vscode"): normalise_name("visual studio code"),
    normalise_name("chrome"): normalise_name("google chrome"),
    normalise_name("chrome browser"): normalise_name("google chrome"),
}


def _collapse_matches(
    matches: tuple[CatalogApp, ...],
) -> tuple[CatalogApp, ...]:
    """Resolve duplicate launch entries only after exact matching."""
    if len(matches) <= 1:
        return matches

    return collapse_equivalent_catalog_apps(matches)


def _find_exact_matches(
    normalized_name: str,
    catalog: Iterable[CatalogApp],
) -> tuple[CatalogApp, ...]:
    """Find and collapse only exact entries from one catalog source."""
    return _collapse_matches(
        find_exact_matches(normalized_name, catalog)
    )


def _alias_for(
    normalized_name: str,
) -> str | None:
    """Return a known exact alias target, never a fuzzy substitute."""
    alias_name = KNOWN_APP_ALIASES.get(normalized_name)

    if alias_name is None or alias_name == normalized_name:
        return None

    return alias_name


def _resolve_matches_from_catalog(
    normalized_request: str,
    catalog: Iterable[CatalogApp],
) -> tuple[CatalogApp, ...]:
    """Resolve exact names before convenience aliases in one catalog."""
    exact_matches = _find_exact_matches(
        normalized_request,
        catalog,
    )

    if exact_matches:
        return exact_matches

    alias_name = _alias_for(normalized_request)

    if alias_name is None:
        return ()

    return _find_exact_matches(alias_name, catalog)


def resolve_catalog_matches(
    requested_name: str,
    *,
    catalog: Iterable[CatalogApp] | None = None,
) -> tuple[CatalogApp, ...]:
    """Find exact local catalog matches for one spoken app request.

    Packaged-app discovery starts only after the regular local catalog has no
    exact match. This avoids a PowerShell process for common desktop apps.
    """
    normalized_request = normalise_name(requested_name)

    if not normalized_request:
        return ()

    if catalog is not None:
        return _resolve_matches_from_catalog(
            normalized_request,
            tuple(catalog),
        )

    regular_catalog = scan_local_app_catalog(
        include_packaged=False,
    )
    regular_exact_matches = _find_exact_matches(
        normalized_request,
        regular_catalog,
    )

    if regular_exact_matches:
        return regular_exact_matches

    packaged_catalog = scan_packaged_apps(
        excluded_normalized_names={
            app.normalized_name
            for app in regular_catalog
        },
    )
    packaged_exact_matches = _find_exact_matches(
        normalized_request,
        packaged_catalog,
    )

    if packaged_exact_matches:
        return packaged_exact_matches

    alias_name = _alias_for(normalized_request)

    if alias_name is None:
        return ()

    regular_alias_matches = _find_exact_matches(
        alias_name,
        regular_catalog,
    )

    if regular_alias_matches:
        return regular_alias_matches

    return _find_exact_matches(
        alias_name,
        packaged_catalog,
    )


def launch_catalog_app(
    requested_name: str,
    *,
    catalog: Iterable[CatalogApp] | None = None,
    startfile: Callable[[str], object] | None = None,
) -> LaunchResult:
    """Launch one exact local catalog target without shell commands."""
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
                f"I could not find an exact local app named "
                f"{display_name}, sir."
            ),
        )

    if len(matches) > 1:
        return LaunchResult(
            success=False,
            display_name=matches[0].display_name,
            message=(
                f"I found {len(matches)} exact local apps named "
                f"{matches[0].display_name}. I will not guess which "
                "one to open, sir."
            ),
        )

    app = matches[0]
    launch_reference = get_catalog_launch_reference(app)

    if launch_reference is None:
        return LaunchResult(
            success=False,
            display_name=app.display_name,
            message=(
                f"I could not prepare a safe launch target for "
                f"{app.display_name}, sir."
            ),
        )

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
        launcher(launch_reference)
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