from __future__ import annotations

import ctypes
import os
import shlex
from collections.abc import Callable
from dataclasses import dataclass
from ctypes import wintypes

import pywintypes
import win32con
import win32gui
import win32process

from skills.app_catalog import (
    CatalogApp,
    LaunchTarget,
    PACKAGED_APP_SOURCE,
    resolve_catalog_launch_target,
)


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ERROR_INSUFFICIENT_BUFFER = 122
MAX_PROCESS_IMAGE_PATH_LENGTH = 32768


_KERNEL32 = (
    ctypes.WinDLL("kernel32", use_last_error=True)
    if os.name == "nt"
    else None
)

_USER32 = (
    ctypes.WinDLL("user32", use_last_error=True)
    if os.name == "nt"
    else None
)

_GET_APPLICATION_USER_MODEL_ID = None

if _KERNEL32 is not None:
    _KERNEL32.OpenProcess.argtypes = (
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    )
    _KERNEL32.OpenProcess.restype = wintypes.HANDLE

    _KERNEL32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _KERNEL32.CloseHandle.restype = wintypes.BOOL

    _KERNEL32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    _KERNEL32.QueryFullProcessImageNameW.restype = wintypes.BOOL

    _GET_APPLICATION_USER_MODEL_ID = getattr(
        _KERNEL32,
        "GetApplicationUserModelId",
        None,
    )

    if _GET_APPLICATION_USER_MODEL_ID is not None:
        _GET_APPLICATION_USER_MODEL_ID.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_uint32),
            wintypes.LPWSTR,
        )
        _GET_APPLICATION_USER_MODEL_ID.restype = ctypes.c_long

if _USER32 is not None:
    _USER32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    _USER32.SetForegroundWindow.restype = wintypes.BOOL

@dataclass(frozen=True)
class AppWindowIdentity:
    """One exact identity that can be matched to a running app window."""

    display_name: str
    executable_path: str | None
    app_user_model_id: str | None
    executable_name: str | None = None
    executable_root: str | None = None

@dataclass(frozen=True)
class NamedWindowResult:
    """Result of one explicit named-window control request."""

    success: bool
    message: str

@dataclass(frozen=True)
class NamedWindowMatchResult:
    """Current exact matching windows for one discovered app."""

    display_name: str
    window_handles: tuple[int, ...]
    error_message: str | None

_SHOW_COMMANDS = {
    "minimize": win32con.SW_MINIMIZE,
    "maximize": win32con.SW_MAXIMIZE,
    "restore": win32con.SW_RESTORE,
}

_ACTION_PHRASES = {
    "minimize": "minimize",
    "maximize": "maximize",
    "restore": "restore",
    "bring_up": "bring up",
}


def _normalise_executable_path(path: str) -> str:
    """Make Windows executable paths safe for exact comparison."""
    return os.path.normcase(
        os.path.normpath(path.strip())
    )


def _safe_executable_name(value: str) -> str | None:
    """Return one safe executable filename from a shortcut argument."""
    candidate = value.strip().strip('"')

    if not candidate:
        return None

    candidate = candidate.replace("/", "\\").rsplit("\\", 1)[-1]

    if not candidate.casefold().endswith(".exe"):
        return None

    return candidate.casefold()


def _parse_process_start_executable(arguments: str) -> str | None:
    """Parse updater-style --processStart executable arguments."""
    try:
        tokens = shlex.split(arguments, posix=False)
    except ValueError:
        return None

    cleaned_tokens = [
        token.strip().strip('"')
        for token in tokens
        if token.strip()
    ]

    for index, token in enumerate(cleaned_tokens):
        token_key = token.casefold()

        if (
            token_key == "--processstart"
            and index + 1 < len(cleaned_tokens)
        ):
            return _safe_executable_name(cleaned_tokens[index + 1])

        prefix = "--processstart="

        if token_key.startswith(prefix):
            return _safe_executable_name(token[len(prefix):])

    return None


def _path_is_inside(candidate_path: str, root_path: str) -> bool:
    """Return whether one normalized path is inside one normalized root."""
    try:
        return os.path.commonpath(
            [candidate_path, root_path]
        ) == root_path
    except ValueError:
        return False

def _open_process_for_query(
    process_id: int,
) -> wintypes.HANDLE | None:
    """Open one process using only query-limited rights."""
    if _KERNEL32 is None or not process_id:
        return None

    try:
        handle = _KERNEL32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            process_id,
        )
    except OSError:
        return None

    return handle or None


def _close_process_handle(
    process_handle: wintypes.HANDLE,
) -> None:
    """Close one process handle if Windows provided one."""
    if _KERNEL32 is None:
        return

    _KERNEL32.CloseHandle(process_handle)


def _query_process_image_path(
    process_id: int,
) -> str | None:
    """Return one running process's Win32 executable path."""
    if _KERNEL32 is None:
        return None

    process_handle = _open_process_for_query(process_id)

    if process_handle is None:
        return None

    try:
        buffer = ctypes.create_unicode_buffer(
            MAX_PROCESS_IMAGE_PATH_LENGTH,
        )
        length = wintypes.DWORD(len(buffer))

        success = _KERNEL32.QueryFullProcessImageNameW(
            process_handle,
            0,
            buffer,
            ctypes.byref(length),
        )

        if not success:
            return None

        path = buffer.value.strip()

        return path or None
    finally:
        _close_process_handle(process_handle)


def _query_process_aumid(
    process_id: int,
) -> str | None:
    """Return one running packaged process's exact AUMID."""
    if _GET_APPLICATION_USER_MODEL_ID is None:
        return None

    process_handle = _open_process_for_query(process_id)

    if process_handle is None:
        return None

    try:
        length = ctypes.c_uint32(0)

        status = _GET_APPLICATION_USER_MODEL_ID(
            process_handle,
            ctypes.byref(length),
            None,
        )

        if (
            status != ERROR_INSUFFICIENT_BUFFER
            or not length.value
        ):
            return None

        buffer = ctypes.create_unicode_buffer(length.value)

        status = _GET_APPLICATION_USER_MODEL_ID(
            process_handle,
            ctypes.byref(length),
            buffer,
        )

        if status != 0:
            return None

        app_user_model_id = buffer.value.strip()

        return app_user_model_id or None
    finally:
        _close_process_handle(process_handle)


def _list_top_level_windows() -> tuple[int, ...]:
    """Return top-level desktop window handles without title matching."""
    window_handles: list[int] = []

    def collect_window(
        window_handle: int,
        _: object,
    ) -> bool:
        window_handles.append(window_handle)
        return True

    win32gui.EnumWindows(collect_window, None)

    return tuple(window_handles)


def _get_window_process_id(
    window_handle: int,
) -> int:
    """Return the owning process ID for one Windows window."""
    _, process_id = win32process.GetWindowThreadProcessId(
        window_handle,
    )

    return int(process_id)


def _get_window_owner(
    window_handle: int,
) -> int:
    """Return the owner handle for one top-level window."""
    return int(
        win32gui.GetWindow(
            window_handle,
            win32con.GW_OWNER,
        )
    )


def _set_foreground_window(
    window_handle: int,
) -> bool:
    """Ask Windows to foreground one exact window."""
    if _USER32 is None:
        return False

    return bool(_USER32.SetForegroundWindow(window_handle))

def _post_close_message(
    window_handle: int,
) -> None:
    """Post a normal WM_CLOSE request without force-killing a process."""
    win32gui.PostMessage(
        window_handle,
        win32con.WM_CLOSE,
        0,
        0,
    )

def build_window_app_identity(
    app: CatalogApp,
    *,
    resolve_launch_target: Callable[
        [CatalogApp],
        LaunchTarget | None,
    ] = resolve_catalog_launch_target,
) -> AppWindowIdentity | None:
    """Build one exact executable-path or AUMID identity."""
    display_name = app.display_name.strip() or "that app"

    if app.source == PACKAGED_APP_SOURCE:
        app_user_model_id = (
            app.app_user_model_id or ""
        ).strip()

        if not app_user_model_id:
            return None

        return AppWindowIdentity(
            display_name=display_name,
            executable_path=None,
            app_user_model_id=app_user_model_id.casefold(),
        )

    launch_target = resolve_launch_target(app)

    if launch_target is None:
        return None

    executable_path = launch_target.target_path.strip()

    if (
        not executable_path
        or not executable_path.casefold().endswith(".exe")
    ):
        return None

    executable_name = os.path.basename(executable_path).casefold()
    process_start_executable = _parse_process_start_executable(
        launch_target.arguments
    )

    if (
        executable_name == "update.exe"
        and process_start_executable is not None
    ):
        executable_root = (
            launch_target.working_directory.strip()
            or os.path.dirname(executable_path)
        )

        if not executable_root:
            return None

        return AppWindowIdentity(
            display_name=display_name,
            executable_path=None,
            app_user_model_id=None,
            executable_name=process_start_executable,
            executable_root=_normalise_executable_path(
                executable_root
            ),
        )

    return AppWindowIdentity(
        display_name=display_name,
        executable_path=_normalise_executable_path(
            executable_path
        ),
        app_user_model_id=None,
    )


def find_matching_windows(
    identity: AppWindowIdentity,
    *,
    list_top_level_windows: Callable[
        [],
        tuple[int, ...],
    ] = _list_top_level_windows,
    is_window: Callable[[int], bool] = win32gui.IsWindow,
    is_window_visible: Callable[[int], bool] = (
        win32gui.IsWindowVisible
    ),
    get_window_owner: Callable[[int], int] = _get_window_owner,
    get_window_process_id: Callable[
        [int],
        int,
    ] = _get_window_process_id,
    get_process_image_path: Callable[
        [int],
        str | None,
    ] = _query_process_image_path,
    get_process_aumid: Callable[
        [int],
        str | None,
    ] = _query_process_aumid,
) -> tuple[int, ...]:
    """Find visible unowned windows matching one exact app identity."""
    matching_handles: list[int] = []
    seen_handles: set[int] = set()

    for window_handle in list_top_level_windows():
        if window_handle in seen_handles:
            continue

        seen_handles.add(window_handle)

        if (
            not is_window(window_handle)
            or not is_window_visible(window_handle)
            or get_window_owner(window_handle)
        ):
            continue

        process_id = get_window_process_id(window_handle)

        if not process_id:
            continue

        if identity.executable_path is not None:
            process_path = get_process_image_path(process_id)

            if (
                not isinstance(process_path, str)
                or _normalise_executable_path(process_path)
                != identity.executable_path
            ):
                continue
        elif (
            identity.executable_name is not None
            and identity.executable_root is not None
        ):
            process_path = get_process_image_path(process_id)

            if not isinstance(process_path, str):
                continue

            normalized_process_path = _normalise_executable_path(
                process_path
            )
            process_executable_name = os.path.basename(
                normalized_process_path
            ).casefold()

            if process_executable_name != identity.executable_name:
                continue

            if not _path_is_inside(
                normalized_process_path,
                identity.executable_root,
            ):
                continue
        elif identity.app_user_model_id is not None:
            process_aumid = get_process_aumid(process_id)

            if (
                not isinstance(process_aumid, str)
                or process_aumid.casefold()
                != identity.app_user_model_id
            ):
                continue

        else:
            continue

        matching_handles.append(window_handle)

    return tuple(matching_handles)

def inspect_named_app_windows(
    app: CatalogApp,
    *,
    resolve_launch_target: Callable[
        [CatalogApp],
        LaunchTarget | None,
    ] = resolve_catalog_launch_target,
    list_top_level_windows: Callable[
        [],
        tuple[int, ...],
    ] = _list_top_level_windows,
    is_window: Callable[[int], bool] = win32gui.IsWindow,
    is_window_visible: Callable[[int], bool] = (
        win32gui.IsWindowVisible
    ),
    get_window_owner: Callable[[int], int] = _get_window_owner,
    get_window_process_id: Callable[
        [int],
        int,
    ] = _get_window_process_id,
    get_process_image_path: Callable[
        [int],
        str | None,
    ] = _query_process_image_path,
    get_process_aumid: Callable[
        [int],
        str | None,
    ] = _query_process_aumid,
) -> NamedWindowMatchResult:
    """Inspect current exact app windows without controlling them."""
    display_name = app.display_name.strip() or "that app"

    try:
        identity = build_window_app_identity(
            app,
            resolve_launch_target=resolve_launch_target,
        )
    except (OSError, pywintypes.error):
        identity = None

    if identity is None:
        return NamedWindowMatchResult(
            display_name=display_name,
            window_handles=(),
            error_message=(
                f"I could not safely identify windows for "
                f"{display_name}, sir."
            ),
        )

    try:
        matching_windows = find_matching_windows(
            identity,
            list_top_level_windows=list_top_level_windows,
            is_window=is_window,
            is_window_visible=is_window_visible,
            get_window_owner=get_window_owner,
            get_window_process_id=get_window_process_id,
            get_process_image_path=get_process_image_path,
            get_process_aumid=get_process_aumid,
        )
    except (OSError, pywintypes.error):
        return NamedWindowMatchResult(
            display_name=identity.display_name,
            window_handles=(),
            error_message=(
                f"I could not inspect open windows for "
                f"{identity.display_name}, sir."
            ),
        )

    return NamedWindowMatchResult(
        display_name=identity.display_name,
        window_handles=matching_windows,
        error_message=None,
    )

def control_named_window(
    app: CatalogApp,
    action: str,
    *,
    resolve_launch_target: Callable[
        [CatalogApp],
        LaunchTarget | None,
    ] = resolve_catalog_launch_target,
    list_top_level_windows: Callable[
        [],
        tuple[int, ...],
    ] = _list_top_level_windows,
    is_window: Callable[[int], bool] = win32gui.IsWindow,
    is_window_visible: Callable[[int], bool] = (
        win32gui.IsWindowVisible
    ),
    get_window_owner: Callable[[int], int] = _get_window_owner,
    get_window_process_id: Callable[
        [int],
        int,
    ] = _get_window_process_id,
    get_process_image_path: Callable[
        [int],
        str | None,
    ] = _query_process_image_path,
    get_process_aumid: Callable[
        [int],
        str | None,
    ] = _query_process_aumid,
    is_iconic: Callable[[int], bool] = win32gui.IsIconic,
    show_window: Callable[[int, int], object] = win32gui.ShowWindow,
    set_foreground_window: Callable[
        [int],
        bool,
    ] = _set_foreground_window,
) -> NamedWindowResult:
    """Control exactly one visible top-level window for one catalog app."""
    action_key = action.strip().casefold()

    if action_key not in _ACTION_PHRASES:
        return NamedWindowResult(
            success=False,
            message="I cannot perform that named-window action, sir.",
        )

    match_result = inspect_named_app_windows(
        app,
        resolve_launch_target=resolve_launch_target,
        list_top_level_windows=list_top_level_windows,
        is_window=is_window,
        is_window_visible=is_window_visible,
        get_window_owner=get_window_owner,
        get_window_process_id=get_window_process_id,
        get_process_image_path=get_process_image_path,
        get_process_aumid=get_process_aumid,
    )

    if match_result.error_message is not None:
        return NamedWindowResult(
            success=False,
            message=match_result.error_message,
        )

    display_name = match_result.display_name
    matching_windows = match_result.window_handles

    if not matching_windows:
        return NamedWindowResult(
            success=False,
            message=(
                f"{display_name} is not currently open, sir."
            ),
        )

    if len(matching_windows) > 1:
        return NamedWindowResult(
            success=False,
            message=(
                f"I found {len(matching_windows)} "
                f"{display_name} windows. I will not guess "
                f"which one to {_ACTION_PHRASES[action_key]}, sir."
            ),
        )

    window_handle = matching_windows[0]

    try:
        if action_key == "bring_up":
            was_minimized = is_iconic(window_handle)

            if was_minimized:
                show_window(
                    window_handle,
                    win32con.SW_RESTORE,
                )

            if not set_foreground_window(window_handle):
                if was_minimized:
                    return NamedWindowResult(
                        success=False,
                        message=(
                            f"I restored {display_name}, but "
                            "Windows would not bring it to the "
                            "foreground, sir."
                        ),
                    )

                return NamedWindowResult(
                    success=False,
                    message=(
                        f"Windows would not bring "
                        f"{display_name} to the foreground, "
                        "sir."
                    ),
                )

            return NamedWindowResult(
                success=True,
                message=(
                    f"Brought {display_name} to the "
                    "foreground, sir."
                ),
            )

        show_window(
            window_handle,
            _SHOW_COMMANDS[action_key],
        )
    except (OSError, pywintypes.error):
        return NamedWindowResult(
            success=False,
            message=(
                f"I could not {_ACTION_PHRASES[action_key]} "
                f"{display_name}, sir."
            ),
        )

    success_verb = {
        "minimize": "Minimized",
        "maximize": "Maximized",
        "restore": "Restored",
    }[action_key]

    return NamedWindowResult(
        success=True,
        message=f"{success_verb} {display_name}, sir.",
    )

def close_named_app_windows(
    app: CatalogApp,
    close_all: bool,
    *,
    resolve_launch_target: Callable[
        [CatalogApp],
        LaunchTarget | None,
    ] = resolve_catalog_launch_target,
    list_top_level_windows: Callable[
        [],
        tuple[int, ...],
    ] = _list_top_level_windows,
    is_window: Callable[[int], bool] = win32gui.IsWindow,
    is_window_visible: Callable[[int], bool] = (
        win32gui.IsWindowVisible
    ),
    get_window_owner: Callable[[int], int] = _get_window_owner,
    get_window_process_id: Callable[
        [int],
        int,
    ] = _get_window_process_id,
    get_process_image_path: Callable[
        [int],
        str | None,
    ] = _query_process_image_path,
    get_process_aumid: Callable[
        [int],
        str | None,
    ] = _query_process_aumid,
    post_close_message: Callable[[int], object] = (
        _post_close_message
    ),
) -> NamedWindowResult:
    """Send normal WM_CLOSE requests to current exact matching windows."""
    match_result = inspect_named_app_windows(
        app,
        resolve_launch_target=resolve_launch_target,
        list_top_level_windows=list_top_level_windows,
        is_window=is_window,
        is_window_visible=is_window_visible,
        get_window_owner=get_window_owner,
        get_window_process_id=get_window_process_id,
        get_process_image_path=get_process_image_path,
        get_process_aumid=get_process_aumid,
    )

    if match_result.error_message is not None:
        return NamedWindowResult(
            success=False,
            message=match_result.error_message,
        )

    display_name = match_result.display_name
    matching_windows = match_result.window_handles

    if not matching_windows:
        return NamedWindowResult(
            success=False,
            message=(
                f"{display_name} is not currently open, sir."
            ),
        )

    if not close_all and len(matching_windows) > 1:
        return NamedWindowResult(
            success=False,
            message=(
                f"I found {len(matching_windows)} "
                f"{display_name} windows. I will not guess "
                "which one to close, sir."
            ),
        )

    windows_to_close = (
        matching_windows
        if close_all
        else (matching_windows[0],)
    )

    sent_count = 0

    for window_handle in windows_to_close:
        try:
            post_close_message(window_handle)
        except (OSError, pywintypes.error):
            if sent_count:
                return NamedWindowResult(
                    success=False,
                    message=(
                        f"I sent close requests to {sent_count} of "
                        f"{len(windows_to_close)} {display_name} "
                        "windows before Windows rejected the rest, "
                        "sir."
                    ),
                )

            return NamedWindowResult(
                success=False,
                message=(
                    f"I could not send a close request to "
                    f"{display_name}, sir."
                ),
            )

        sent_count += 1

    if close_all:
        window_word = (
            "window"
            if sent_count == 1
            else "windows"
        )

        return NamedWindowResult(
            success=True,
            message=(
                f"Sent close requests to {sent_count} "
                f"{display_name} {window_word}, sir."
            ),
        )

    return NamedWindowResult(
        success=True,
        message=f"Sent a close request to {display_name}, sir.",
    )