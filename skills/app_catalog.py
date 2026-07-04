from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CatalogApp:
    """One app shortcut discovered from a safe local Start Menu location."""

    display_name: str
    normalized_name: str
    shortcut_path: Path

@dataclass(frozen=True)
class ShortcutLaunchTarget:
    """The actual local action represented by one Windows shortcut."""

    target_path: str
    arguments: str
    working_directory: str

    def launch_key(self) -> tuple[str, str, str]:
        """Return a case-insensitive key for safe duplicate comparison."""
        return (
            os.path.normcase(
                os.path.normpath(self.target_path)
            ),
            self.arguments.strip(),
            os.path.normcase(
                os.path.normpath(self.working_directory)
            ),
        )

def normalise_name(value: str) -> str:
    """Make spoken names and shortcut names comparable exactly."""
    return " ".join(
        re.sub(r"[^a-z0-9]+", " ", value.casefold()).split()
    )


def get_start_menu_roots() -> tuple[Path, ...]:
    """Return only standard Windows Start Menu program folders.

    Desktop shortcuts are intentionally excluded. This keeps automatic
    discovery limited to normal installed-app locations.
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

        if root.is_dir() and root not in roots:
            roots.append(root)

    return tuple(roots)


def scan_start_menu_shortcuts(
    shortcut_roots: Iterable[Path] | None = None,
) -> tuple[CatalogApp, ...]:
    """Build a deterministic catalog from exact .lnk shortcut files.

    Duplicate display names are preserved deliberately. The launcher will
    later refuse ambiguous matches instead of silently choosing one.
    """
    roots = (
        tuple(shortcut_roots)
        if shortcut_roots is not None
        else get_start_menu_roots()
    )

    catalog: list[CatalogApp] = []

    for root in roots:
        if not root.is_dir():
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
            display_name = shortcut.stem.strip()

            if not display_name:
                continue

            catalog.append(
                CatalogApp(
                    display_name=display_name,
                    normalized_name=normalise_name(display_name),
                    shortcut_path=shortcut,
                )
            )

    return tuple(catalog)


def find_exact_matches(
    requested_name: str,
    catalog: Iterable[CatalogApp],
) -> tuple[CatalogApp, ...]:
    """Return every exact normalized catalog match, never a fuzzy match."""
    normalized_request = normalise_name(requested_name)

    if not normalized_request:
        return ()

    return tuple(
        app
        for app in catalog
        if app.normalized_name == normalized_request
    )

def resolve_shortcut_target(
    shortcut_path: Path,
) -> ShortcutLaunchTarget | None:
    """Read one Windows shortcut without launching it.

    Returns None when the shortcut target cannot be read. Callers must keep
    unresolved shortcuts separate rather than assuming they are duplicates.
    """
    try:
        import win32com.client

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(shortcut_path))

        target_path = str(shortcut.Targetpath or "").strip()

        if not target_path:
            return None

        return ShortcutLaunchTarget(
            target_path=target_path,
            arguments=str(shortcut.Arguments or "").strip(),
            working_directory=str(
                shortcut.WorkingDirectory or ""
            ).strip(),
        )
    except Exception:
        return None


def collapse_equivalent_shortcuts(
    matches: Iterable[CatalogApp],
    *,
    resolve_target: Callable[
        [Path],
        ShortcutLaunchTarget | None,
    ] = resolve_shortcut_target,
) -> tuple[CatalogApp, ...]:
    """Collapse shortcuts only when they represent the same launch action.

    Unresolved shortcuts remain separate. This prevents Avens from guessing
    when two same-named shortcuts cannot be proven equivalent.
    """
    unique_matches: list[CatalogApp] = []
    seen_launch_keys: set[tuple[str, str, str]] = set()

    for app in matches:
        target = resolve_target(app.shortcut_path)

        if target is None:
            unique_matches.append(app)
            continue

        launch_key = target.launch_key()

        if launch_key in seen_launch_keys:
            continue

        seen_launch_keys.add(launch_key)
        unique_matches.append(app)

    return tuple(unique_matches)