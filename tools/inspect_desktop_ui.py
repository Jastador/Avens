from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any


DEFAULT_BACKEND = "uia"
DEFAULT_MAX_DEPTH = 6
DEFAULT_MAX_RESULTS = 120
DEFAULT_TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True)
class ControlSnapshot:
    """Read-only metadata for one accessible desktop control."""

    name: str
    control_type: str
    automation_id: str
    class_name: str
    handle: str
    depth: int

    @property
    def searchable_text(self) -> str:
        """Return the fields used by local read-only filters."""
        return " | ".join(
            (
                self.name,
                self.control_type,
                self.automation_id,
                self.class_name,
            )
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for UI inspection."""
    parser = argparse.ArgumentParser(
        description=(
            "Read accessible Windows UI controls without clicking, "
            "typing, launching, or changing any app state."
        ),
    )
    parser.add_argument(
        "--backend",
        choices=("uia", "win32"),
        default=DEFAULT_BACKEND,
        help="Accessibility backend to inspect. Default: uia.",
    )
    parser.add_argument(
        "--title-regex",
        help=(
            "Regular expression matching the target window title. "
            "Required unless --list-windows is used."
        ),
    )
    parser.add_argument(
        "--list-windows",
        action="store_true",
        help="List visible windows instead of inspecting one window.",
    )
    parser.add_argument(
        "--contains",
        action="append",
        default=[],
        metavar="REGEX",
        help=(
            "Only print controls whose metadata matches this regular "
            "expression. May be supplied more than once."
        ),
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=DEFAULT_MAX_DEPTH,
        help=(
            "Maximum child-control depth to inspect. "
            f"Default: {DEFAULT_MAX_DEPTH}."
        ),
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=DEFAULT_MAX_RESULTS,
        help=(
            "Maximum matching controls to print. "
            f"Default: {DEFAULT_MAX_RESULTS}."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=(
            "Seconds to wait for the target window. "
            f"Default: {DEFAULT_TIMEOUT_SECONDS}."
        ),
    )
    return parser


def parse_arguments(
    arguments: Sequence[str] | None = None,
) -> argparse.Namespace:
    """Parse and validate command-line arguments."""
    parser = build_parser()
    parsed = parser.parse_args(arguments)

    if not parsed.list_windows and not parsed.title_regex:
        parser.error(
            "--title-regex is required unless --list-windows is used."
        )

    if parsed.max_depth < 0:
        parser.error("--max-depth must be zero or greater.")

    if parsed.max_results < 1:
        parser.error("--max-results must be at least 1.")

    if parsed.timeout <= 0:
        parser.error("--timeout must be greater than zero.")

    return parsed


def _read_element_property(
    element_info: object,
    property_name: str,
) -> str:
    """Read one UIA property without failing the whole inspection."""
    try:
        value = getattr(element_info, property_name, "")
    except Exception:
        return "<unavailable>"

    if value is None:
        return ""

    return str(value)


def snapshot_control(
    control: Any,
    *,
    depth: int,
) -> ControlSnapshot:
    """Convert a pywinauto control wrapper into safe display metadata."""
    element_info = control.element_info

    return ControlSnapshot(
        name=_read_element_property(element_info, "name"),
        control_type=_read_element_property(
            element_info,
            "control_type",
        ),
        automation_id=_read_element_property(
            element_info,
            "automation_id",
        ),
        class_name=_read_element_property(
            element_info,
            "class_name",
        ),
        handle=_read_element_property(element_info, "handle"),
        depth=depth,
    )


def iter_control_snapshots(
    root_control: Any,
    *,
    max_depth: int,
) -> Iterable[ControlSnapshot]:
    """Walk accessible child controls without performing UI actions."""
    pending_controls: list[tuple[Any, int]] = [
        (root_control, 0),
    ]

    while pending_controls:
        control, depth = pending_controls.pop()
        yield snapshot_control(control, depth=depth)

        if depth >= max_depth:
            continue

        try:
            child_controls = control.children()
        except Exception as error:
            print(
                f"Skipping unreadable child controls: {error}",
                file=sys.stderr,
            )
            continue

        pending_controls.extend(
            (child_control, depth + 1)
            for child_control in reversed(child_controls)
        )


def compile_filters(
    raw_filters: Sequence[str],
) -> tuple[re.Pattern[str], ...]:
    """Compile user-provided read-only metadata filters."""
    return tuple(
        re.compile(raw_filter, re.IGNORECASE)
        for raw_filter in raw_filters
    )


def control_matches_filters(
    snapshot: ControlSnapshot,
    filters: Sequence[re.Pattern[str]],
) -> bool:
    """Return whether one control matches any requested filter."""
    if not filters:
        return True

    return any(
        control_filter.search(snapshot.searchable_text) is not None
        for control_filter in filters
    )


def format_snapshot(snapshot: ControlSnapshot) -> str:
    """Format one control for stable terminal output."""
    indent = "  " * snapshot.depth
    fields = (
        f"name={snapshot.name!r}",
        f"type={snapshot.control_type!r}",
        f"automation_id={snapshot.automation_id!r}",
        f"class={snapshot.class_name!r}",
        f"handle={snapshot.handle!r}",
    )

    return f"{indent}- " + " | ".join(fields)


def _create_desktop(
    backend: str,
) -> Any:
    """Create a pywinauto desktop reader only when execution begins."""
    try:
        from pywinauto import Desktop
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "pywinauto is not installed. Run "
            "`python -m pip install -r requirements.txt` first."
        ) from error

    return Desktop(backend=backend)


def list_visible_windows(
    desktop: Any,
    filters: Sequence[re.Pattern[str]],
    *,
    max_results: int,
) -> int:
    """Print matching visible windows without inspecting their children."""
    matched_count = 0

    for window in desktop.windows(visible_only=True):
        snapshot = snapshot_control(window, depth=0)

        if not control_matches_filters(snapshot, filters):
            continue

        print(format_snapshot(snapshot))
        matched_count += 1

        if matched_count >= max_results:
            break

    return matched_count


def inspect_window(
    desktop: Any,
    *,
    title_regex: str,
    timeout: float,
    max_depth: int,
    filters: Sequence[re.Pattern[str]],
    max_results: int,
) -> int:
    """Print matching controls from one visible window."""
    target_window = desktop.window(
        title_re=title_regex,
        visible_only=True,
    )
    target_window.wait(
        "exists visible",
        timeout=timeout,
    )
    root_control = target_window.wrapper_object()

    print(f"Inspecting window title regex: {title_regex!r}")
    matched_count = 0

    for snapshot in iter_control_snapshots(
        root_control,
        max_depth=max_depth,
    ):
        if not control_matches_filters(snapshot, filters):
            continue

        print(format_snapshot(snapshot))
        matched_count += 1

        if matched_count >= max_results:
            print(
                "Result limit reached. Narrow --contains or "
                "increase --max-results.",
            )
            break

    return matched_count


def main(
    arguments: Sequence[str] | None = None,
) -> int:
    """Run the read-only UI inspector."""
    parsed = parse_arguments(arguments)

    try:
        if parsed.title_regex:
            re.compile(parsed.title_regex)

        filters = compile_filters(parsed.contains)
        desktop = _create_desktop(parsed.backend)

        if parsed.list_windows:
            print(
                f"Visible windows using backend: {parsed.backend}",
            )
            matched_count = list_visible_windows(
                desktop,
                filters,
                max_results=parsed.max_results,
            )
        else:
            matched_count = inspect_window(
                desktop,
                title_regex=parsed.title_regex,
                timeout=parsed.timeout,
                max_depth=parsed.max_depth,
                filters=filters,
                max_results=parsed.max_results,
            )
    except (re.error, RuntimeError) as error:
        print(f"UI inspection error: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(
            f"UI inspection could not complete safely: {error}",
            file=sys.stderr,
        )
        return 1

    if matched_count == 0:
        print(
            "No matching accessible controls were found. "
            "Try a different backend, title regex, filter, or depth.",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())