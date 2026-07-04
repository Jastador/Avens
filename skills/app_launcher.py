from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ApprovedApp:
    """One explicitly allowed local application target."""

    app_id: str
    display_name: str
    aliases: tuple[str, ...]
    shortcut_names: tuple[str, ...]


@dataclass(frozen=True)
class LaunchResult:
    """The honest result of one local app launch attempt."""

    success: bool
    app_id: str
    message: str


APPROVED_APPS: tuple[ApprovedApp, ...] = (
    ApprovedApp(
        app_id="discord",
        display_name="Discord",
        aliases=("discord", "discord app"),
        shortcut_names=("discord",),
    ),
    ApprovedApp(
        app_id="vscode",
        display_name="Visual Studio Code",
        aliases=("vs code", "visual studio code", "vscode"),
        shortcut_names=("visual studio code",),
    ),
    ApprovedApp(
        app_id="chrome",
        display_name="Google Chrome",
        aliases=("chrome", "google chrome", "chrome browser"),
        shortcut_names=("google chrome",),
    ),
)

APPS_BY_ID = {
    app.app_id: app
    for app in APPROVED_APPS
}


def normalise_name(value: str) -> str:
    """Make spoken and shortcut names comparable without fuzzy matching."""
    return " ".join(
        re.sub(r"[^a-z0-9]+", " ", value.casefold()).split()
    )


def find_approved_app(requested_name: str) -> ApprovedApp | None:
    """Return an app only for an exact approved alias."""
    requested = normalise_name(requested_name)

    for app in APPROVED_APPS:
        aliases = {
            normalise_name(alias)
            for alias in app.aliases
        }

        if requested in aliases:
            return app

    return None


def get_start_menu_roots() -> tuple[Path, ...]:
    """Return only standard Start Menu program locations.

    Desktop shortcuts are intentionally excluded. A future skill can add an
    explicit user-managed shortcut directory, but this first slice stays narrow.
    """
    roots: list[Path] = []

    for environment_variable in ("PROGRAMDATA", "APPDATA"):
        base_path = os.getenv(environment_variable)

        if not base_path:
            continue

        root = (
            Path(base_path)
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
        )

        if root.exists():
            roots.append(root)

    return tuple(roots)


def find_approved_shortcut(
    app: ApprovedApp,
    shortcut_roots: Iterable[Path] | None = None,
) -> Path | None:
    """Find an exact approved Start Menu shortcut for one app."""
    accepted_names = {
        normalise_name(shortcut_name)
        for shortcut_name in app.shortcut_names
    }

    roots = (
        tuple(shortcut_roots)
        if shortcut_roots is not None
        else get_start_menu_roots()
    )

    for root in roots:
        if not root.exists():
            continue

        try:
            shortcuts = sorted(
                (
                    path
                    for path in root.rglob("*")
                    if path.is_file()
                    and path.suffix.casefold() == ".lnk"
                ),
                key=lambda path: str(path).casefold(),
            )
        except OSError:
            continue

        for shortcut in shortcuts:
            if normalise_name(shortcut.stem) in accepted_names:
                return shortcut

    return None


def launch_approved_app(
    app_id: str,
    *,
    shortcut_roots: Iterable[Path] | None = None,
    startfile: Callable[[str], object] | None = None,
) -> LaunchResult:
    """Launch only one approved app via its exact Start Menu shortcut.

    This function never builds shell commands, never uses fuzzy matching, and
    never opens Windows search for unknown requests.
    """
    app = APPS_BY_ID.get(app_id)

    if app is None:
        raise ValueError(f"Unknown approved app id: {app_id}")

    shortcut = find_approved_shortcut(
        app,
        shortcut_roots=shortcut_roots,
    )

    if shortcut is None:
        return LaunchResult(
            success=False,
            app_id=app.app_id,
            message=(
                f"{app.display_name} is approved, but I could not find its "
                "exact Start Menu shortcut."
            ),
        )

    launcher = startfile or getattr(os, "startfile", None)

    if launcher is None:
        return LaunchResult(
            success=False,
            app_id=app.app_id,
            message=(
                "Local app launching is available only on Windows."
            ),
        )

    try:
        launcher(str(shortcut))
    except OSError as error:
        return LaunchResult(
            success=False,
            app_id=app.app_id,
            message=(
                f"I could not open {app.display_name}: {error}"
            ),
        )

    return LaunchResult(
        success=True,
        app_id=app.app_id,
        message=f"Opening {app.display_name}, sir.",
    )