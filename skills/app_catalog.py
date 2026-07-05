from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path


START_MENU_SOURCE = "start_menu"
APP_PATHS_SOURCE = "app_paths"

APP_PATHS_REGISTRY_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\App Paths"
)


@dataclass(frozen=True)
class CatalogApp:
    """One safe local application launch target."""

    display_name: str
    normalized_name: str
    launch_path: Path
    source: str = START_MENU_SOURCE


@dataclass(frozen=True)
class AppPathRegistration:
    """One raw App Paths registry registration read from Windows."""

    executable_name: str
    raw_target: str


@dataclass(frozen=True)
class LaunchTarget:
    """The actual local action represented by one catalog entry."""

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
    """Make spoken names and catalog names comparable exactly."""
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
    """Build catalog entries from exact Start Menu .lnk files."""
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
                    launch_path=shortcut,
                    source=START_MENU_SOURCE,
                )
            )

    return tuple(catalog)


def read_app_path_registrations() -> tuple[AppPathRegistration, ...]:
    """Read Windows App Paths registrations without changing the registry."""
    if os.name != "nt":
        return ()

    try:
        import winreg
    except ImportError:
        return ()

    views = tuple(
        dict.fromkeys(
            (
                getattr(winreg, "KEY_WOW64_64KEY", 0),
                getattr(winreg, "KEY_WOW64_32KEY", 0),
            )
        )
    )

    registry_locations = tuple(
        (hive, view)
        for hive in (
            winreg.HKEY_CURRENT_USER,
            winreg.HKEY_LOCAL_MACHINE,
        )
        for view in views
    )

    registrations: list[AppPathRegistration] = []
    seen_entries: set[tuple[str, str]] = set()

    for hive, view in registry_locations:
        access = winreg.KEY_READ | view

        try:
            with winreg.OpenKey(
                hive,
                APP_PATHS_REGISTRY_KEY,
                0,
                access,
            ) as app_paths_key:
                index = 0

                while True:
                    try:
                        executable_name = winreg.EnumKey(
                            app_paths_key,
                            index,
                        )
                    except OSError:
                        break

                    index += 1

                    try:
                        with winreg.OpenKey(
                            app_paths_key,
                            executable_name,
                            0,
                            access,
                        ) as app_key:
                            raw_target, _ = winreg.QueryValueEx(
                                app_key,
                                "",
                            )
                    except OSError:
                        continue

                    if not isinstance(raw_target, str):
                        continue

                    entry_key = (
                        executable_name.casefold(),
                        raw_target.casefold(),
                    )

                    if entry_key in seen_entries:
                        continue

                    seen_entries.add(entry_key)
                    registrations.append(
                        AppPathRegistration(
                            executable_name=executable_name,
                            raw_target=raw_target,
                        )
                    )
        except OSError:
            continue

    return tuple(registrations)


def _app_paths_display_name(
    executable_name: str,
) -> str | None:
    """Accept only a simple .exe key name from App Paths."""
    candidate = executable_name.strip()
    path = Path(candidate)

    if (
        not candidate
        or path.name != candidate
        or path.suffix.casefold() != ".exe"
    ):
        return None

    display_name = path.stem.strip()

    return display_name or None


def resolve_app_path_executable(
    raw_target: str,
) -> Path | None:
    """Validate one App Paths default value as a direct .exe target.

    Command strings with arguments are rejected instead of parsed. This
    catalog launches only an existing executable path, never a shell command.
    """
    candidate = os.path.expandvars(raw_target.strip())

    if (
        len(candidate) >= 2
        and candidate.startswith('"')
        and candidate.endswith('"')
    ):
        candidate = candidate[1:-1].strip()
    elif '"' in candidate:
        return None

    if not candidate or "\x00" in candidate:
        return None

    path = Path(candidate)

    try:
        if (
            path.suffix.casefold() != ".exe"
            or not path.is_file()
        ):
            return None

        return path.resolve()
    except OSError:
        return None


def scan_app_paths(
    registrations: Iterable[AppPathRegistration] | None = None,
) -> tuple[CatalogApp, ...]:
    """Build validated direct-executable entries from App Paths."""
    entries = (
        tuple(registrations)
        if registrations is not None
        else read_app_path_registrations()
    )

    catalog: list[CatalogApp] = []

    for registration in entries:
        display_name = _app_paths_display_name(
            registration.executable_name,
        )
        executable_path = resolve_app_path_executable(
            registration.raw_target,
        )

        if display_name is None or executable_path is None:
            continue

        catalog.append(
            CatalogApp(
                display_name=display_name,
                normalized_name=normalise_name(display_name),
                launch_path=executable_path,
                source=APP_PATHS_SOURCE,
            )
        )

    return tuple(
        sorted(
            catalog,
            key=lambda app: (
                app.normalized_name,
                str(app.launch_path).casefold(),
            ),
        )
    )


def scan_local_app_catalog(
    *,
    shortcut_roots: Iterable[Path] | None = None,
    app_path_registrations: Iterable[
        AppPathRegistration
    ] | None = None,
) -> tuple[CatalogApp, ...]:
    """Combine all safe local launch sources into one catalog."""
    catalog = (
        *scan_start_menu_shortcuts(
            shortcut_roots=shortcut_roots,
        ),
        *scan_app_paths(
            registrations=app_path_registrations,
        ),
    )

    return tuple(
        sorted(
            catalog,
            key=lambda app: (
                app.normalized_name,
                app.source,
                str(app.launch_path).casefold(),
            ),
        )
    )


def find_exact_matches(
    requested_name: str,
    catalog: Iterable[CatalogApp],
) -> tuple[CatalogApp, ...]:
    """Return exact normalized catalog matches, never fuzzy matches."""
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
) -> LaunchTarget | None:
    """Read one Windows shortcut without launching it."""
    try:
        import win32com.client

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(shortcut_path))

        target_path = str(shortcut.Targetpath or "").strip()

        if not target_path:
            return None

        return LaunchTarget(
            target_path=target_path,
            arguments=str(shortcut.Arguments or "").strip(),
            working_directory=str(
                shortcut.WorkingDirectory or ""
            ).strip(),
        )
    except Exception:
        return None


def resolve_catalog_launch_target(
    app: CatalogApp,
) -> LaunchTarget | None:
    """Resolve a catalog entry into its actual local launch action."""
    if app.source == APP_PATHS_SOURCE:
        return LaunchTarget(
            target_path=str(app.launch_path),
            arguments="",
            working_directory="",
        )

    if app.source == START_MENU_SOURCE:
        return resolve_shortcut_target(app.launch_path)

    return None


def collapse_equivalent_catalog_apps(
    matches: Iterable[CatalogApp],
    *,
    resolve_target: Callable[
        [CatalogApp],
        LaunchTarget | None,
    ] = resolve_catalog_launch_target,
) -> tuple[CatalogApp, ...]:
    """Collapse entries only when they represent one launch action."""
    unique_matches: list[CatalogApp] = []
    seen_launch_keys: set[tuple[str, str, str]] = set()

    for app in matches:
        target = resolve_target(app)

        if target is None:
            unique_matches.append(app)
            continue

        launch_key = target.launch_key()

        if launch_key in seen_launch_keys:
            continue

        seen_launch_keys.add(launch_key)
        unique_matches.append(app)

    return tuple(unique_matches)