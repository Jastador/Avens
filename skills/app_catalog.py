from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path


START_MENU_SOURCE = "start_menu"
APP_PATHS_SOURCE = "app_paths"
PACKAGED_APP_SOURCE = "packaged_app"

APP_PATHS_REGISTRY_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\App Paths"
)

PACKAGED_APPS_POWERSHELL_SCRIPT = (
    "$ErrorActionPreference = 'Stop'; "
    "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
    "Get-StartApps | "
    "Where-Object { $_.AppID -match '!' } | "
    "Select-Object Name, AppID | "
    "ConvertTo-Json -Compress"
)


@dataclass(frozen=True)
class CatalogApp:
    """One safe local application launch target."""

    display_name: str
    normalized_name: str
    launch_path: Path | None
    source: str = START_MENU_SOURCE
    app_user_model_id: str | None = None


@dataclass(frozen=True)
class AppPathRegistration:
    """One raw App Paths registry registration read from Windows."""

    executable_name: str
    raw_target: str


@dataclass(frozen=True)
class PackagedAppRegistration:
    """One current-user packaged-app registration from Start."""

    display_name: str
    app_user_model_id: str


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


def _catalog_sort_key(app: CatalogApp) -> tuple[str, str, str]:
    """Keep catalog ordering stable across all local launch sources."""
    reference = (
        app.app_user_model_id
        if app.app_user_model_id is not None
        else str(app.launch_path or "")
    )

    return (
        app.normalized_name,
        app.source,
        reference.casefold(),
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

    return tuple(sorted(catalog, key=_catalog_sort_key))


def _read_packaged_apps_json() -> str | None:
    """Read packaged app names and AUMIDs using one fixed PowerShell query."""
    if os.name != "nt":
        return None

    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                PACKAGED_APPS_POWERSHELL_SCRIPT,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            creationflags=getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            ),
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    return result.stdout


def parse_packaged_app_registrations(
    payload: str,
) -> tuple[PackagedAppRegistration, ...]:
    """Parse fixed Get-StartApps JSON output without launching anything."""
    if not payload.strip():
        return ()

    try:
        raw_records = json.loads(payload)
    except json.JSONDecodeError:
        return ()

    if isinstance(raw_records, dict):
        records = (raw_records,)
    elif isinstance(raw_records, list):
        records = raw_records
    else:
        return ()

    registrations: list[PackagedAppRegistration] = []
    seen_entries: set[tuple[str, str]] = set()

    for record in records:
        if not isinstance(record, dict):
            continue

        display_name = record.get("Name")
        app_user_model_id = record.get("AppID")

        if (
            not isinstance(display_name, str)
            or not isinstance(app_user_model_id, str)
        ):
            continue

        display_name = display_name.strip()
        app_user_model_id = app_user_model_id.strip()

        entry_key = (
            display_name.casefold(),
            app_user_model_id.casefold(),
        )

        if (
            not display_name
            or entry_key in seen_entries
        ):
            continue

        seen_entries.add(entry_key)
        registrations.append(
            PackagedAppRegistration(
                display_name=display_name,
                app_user_model_id=app_user_model_id,
            )
        )

    return tuple(registrations)


def read_packaged_app_registrations() -> tuple[PackagedAppRegistration, ...]:
    """Read current-user packaged app registrations from Start."""
    payload = _read_packaged_apps_json()

    if payload is None:
        return ()

    return parse_packaged_app_registrations(payload)


def _is_safe_aumid(
    app_user_model_id: str,
) -> bool:
    """Accept a simple package-family and application-id AUMID only."""
    candidate = app_user_model_id.strip()

    if (
        candidate != app_user_model_id
        or candidate.count("!") != 1
    ):
        return False

    package_family, application_id = candidate.split("!", 1)

    if not package_family or not application_id:
        return False

    return not any(
        character.isspace()
        or ord(character) < 32
        or character in r'\/:*?"<>|;'
        for character in candidate
    )


def scan_packaged_apps(
    registrations: Iterable[PackagedAppRegistration] | None = None,
    *,
    excluded_normalized_names: Iterable[str] = (),
) -> tuple[CatalogApp, ...]:
    """Build safe package entries from current-user Start AUMIDs."""
    entries = (
        tuple(registrations)
        if registrations is not None
        else read_packaged_app_registrations()
    )
    excluded_names = set(excluded_normalized_names)

    catalog: list[CatalogApp] = []

    for registration in entries:
        display_name = registration.display_name.strip()
        normalized_name = normalise_name(display_name)

        if (
            not display_name
            or not normalized_name
            or normalized_name in excluded_names
            or not _is_safe_aumid(
                registration.app_user_model_id
            )
        ):
            continue

        catalog.append(
            CatalogApp(
                display_name=display_name,
                normalized_name=normalized_name,
                launch_path=None,
                source=PACKAGED_APP_SOURCE,
                app_user_model_id=registration.app_user_model_id,
            )
        )

    return tuple(sorted(catalog, key=_catalog_sort_key))


def scan_local_app_catalog(
    *,
    shortcut_roots: Iterable[Path] | None = None,
    app_path_registrations: Iterable[
        AppPathRegistration
    ] | None = None,
    packaged_app_registrations: Iterable[
        PackagedAppRegistration
    ] | None = None,
    include_packaged: bool = True,
) -> tuple[CatalogApp, ...]:
    """Combine safe local launch sources into one catalog."""
    regular_catalog = (
        *scan_start_menu_shortcuts(
            shortcut_roots=shortcut_roots,
        ),
        *scan_app_paths(
            registrations=app_path_registrations,
        ),
    )

    catalog: tuple[CatalogApp, ...] = tuple(regular_catalog)

    if include_packaged:
        occupied_names = {
            app.normalized_name
            for app in regular_catalog
        }
        catalog = (
            *catalog,
            *scan_packaged_apps(
                registrations=packaged_app_registrations,
                excluded_normalized_names=occupied_names,
            ),
        )

    return tuple(sorted(catalog, key=_catalog_sort_key))


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
    if app.source == PACKAGED_APP_SOURCE:
        launch_reference = get_catalog_launch_reference(app)

        if launch_reference is None:
            return None

        return LaunchTarget(
            target_path=launch_reference,
            arguments="",
            working_directory="",
        )

    if app.source == APP_PATHS_SOURCE:
        if app.launch_path is None:
            return None

        return LaunchTarget(
            target_path=str(app.launch_path),
            arguments="",
            working_directory="",
        )

    if app.source == START_MENU_SOURCE:
        if app.launch_path is None:
            return None

        return resolve_shortcut_target(app.launch_path)

    return None


def get_catalog_launch_reference(
    app: CatalogApp,
) -> str | None:
    """Return the one safe shell target represented by a catalog entry."""
    if app.source == PACKAGED_APP_SOURCE:
        if (
            app.app_user_model_id is None
            or not _is_safe_aumid(app.app_user_model_id)
        ):
            return None

        return (
            "shell:AppsFolder\\"
            f"{app.app_user_model_id}"
        )

    if (
        app.source in {START_MENU_SOURCE, APP_PATHS_SOURCE}
        and app.launch_path is not None
    ):
        return str(app.launch_path)

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