from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from pywinauto import Desktop

from skills.discord_ui_inspector import (
    DiscordUiInspection,
    inspect_discord_ui,
)


DEFAULT_MAX_ACCESSIBILITY_NODES: Final = 200
MAX_FIELD_LENGTH: Final = 120


@dataclass(frozen=True)
class DiscordAccessibilityNode:
    """One read-only Discord UI Automation node."""

    index: int
    name: str
    control_type: str
    class_name: str
    automation_id: str


@dataclass(frozen=True)
class DiscordAccessibilityInspection:
    """Read-only Discord accessibility inspection result."""

    success: bool
    window_handle: int | None
    window_title: str
    node_count: int
    nodes: tuple[DiscordAccessibilityNode, ...]
    message: str


def _clean_field(
    value: object,
    *,
    max_length: int = MAX_FIELD_LENGTH,
) -> str:
    """Clean one UI Automation text field for safe debug output."""
    if not isinstance(value, str):
        return ""

    cleaned = " ".join(value.strip().split())

    if len(cleaned) <= max_length:
        return cleaned

    return f"{cleaned[: max_length - 3]}..."


def _read_element_field(
    element_info: object,
    field_name: str,
) -> str:
    """Read one UI Automation element field safely."""
    try:
        value = getattr(element_info, field_name)
    except (AttributeError, RuntimeError, OSError, TypeError, ValueError):
        return ""

    return _clean_field(value)


def _collect_pywinauto_nodes(
    window_handle: int,
    *,
    max_nodes: int = DEFAULT_MAX_ACCESSIBILITY_NODES,
) -> tuple[DiscordAccessibilityNode, ...]:
    """Collect read-only UI Automation descendants for one window."""
    desktop = Desktop(backend="uia")
    window = desktop.window(handle=window_handle)

    descendants = window.descendants()
    nodes: list[DiscordAccessibilityNode] = []

    for wrapper in descendants[:max_nodes]:
        element_info = getattr(wrapper, "element_info", None)

        if element_info is None:
            continue

        nodes.append(
            DiscordAccessibilityNode(
                index=len(nodes) + 1,
                name=_read_element_field(element_info, "name"),
                control_type=_read_element_field(
                    element_info,
                    "control_type",
                ),
                class_name=_read_element_field(
                    element_info,
                    "class_name",
                ),
                automation_id=_read_element_field(
                    element_info,
                    "automation_id",
                ),
            )
        )

    return tuple(nodes)


def inspect_discord_accessibility(
    *,
    inspect_discord: Callable[[], DiscordUiInspection] = (
        inspect_discord_ui
    ),
    collect_nodes: Callable[
        ...,
        tuple[DiscordAccessibilityNode, ...],
    ] = _collect_pywinauto_nodes,
    max_nodes: int = DEFAULT_MAX_ACCESSIBILITY_NODES,
) -> DiscordAccessibilityInspection:
    """Inspect Discord's UI Automation tree without controlling it."""
    if max_nodes <= 0:
        raise ValueError("max_nodes must be greater than zero.")

    discord_inspection = inspect_discord()

    if not discord_inspection.success:
        return DiscordAccessibilityInspection(
            success=False,
            window_handle=None,
            window_title="",
            node_count=0,
            nodes=(),
            message=discord_inspection.message,
        )

    if discord_inspection.window_count != 1:
        return DiscordAccessibilityInspection(
            success=False,
            window_handle=None,
            window_title="",
            node_count=0,
            nodes=(),
            message=(
                "I need exactly one verified Discord window before "
                "inspecting accessibility, sir."
            ),
        )

    window = discord_inspection.windows[0]

    try:
        nodes = collect_nodes(
            window.window_handle,
            max_nodes=max_nodes,
        )
    except (
        AttributeError,
        RuntimeError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        return DiscordAccessibilityInspection(
            success=False,
            window_handle=window.window_handle,
            window_title=window.title,
            node_count=0,
            nodes=(),
            message=(
                "I could not inspect Discord accessibility safely: "
                f"{error}"
            ),
        )

    if not nodes:
        return DiscordAccessibilityInspection(
            success=False,
            window_handle=window.window_handle,
            window_title=window.title,
            node_count=0,
            nodes=(),
            message=(
                "Discord accessibility inspection found no readable "
                "UI elements, sir."
            ),
        )

    node_count = len(nodes)

    return DiscordAccessibilityInspection(
        success=True,
        window_handle=window.window_handle,
        window_title=window.title,
        node_count=node_count,
        nodes=nodes,
        message=(
            "Discord accessibility inspection found "
            f"{node_count} readable UI elements, sir."
        ),
    )


def format_discord_accessibility_inspection(
    inspection: DiscordAccessibilityInspection,
    *,
    max_nodes_to_show: int = 40,
) -> str:
    """Format one Discord accessibility inspection for debug output."""
    if max_nodes_to_show <= 0:
        raise ValueError("max_nodes_to_show must be greater than zero.")

    status = "success" if inspection.success else "failed"
    title = inspection.window_title or "<untitled>"

    lines = [
        "Discord accessibility inspection:",
        f"Status: {status}",
        f"Message: {inspection.message}",
    ]

    if inspection.window_handle is not None:
        lines.append(
            f"Window: {inspection.window_handle:#x} | title={title}"
        )

    if inspection.nodes:
        lines.append("Nodes:")

        for node in inspection.nodes[:max_nodes_to_show]:
            name = node.name or "<no name>"
            control_type = node.control_type or "<no type>"
            class_name = node.class_name or "<no class>"
            automation_id = node.automation_id or "<no automation id>"

            lines.append(
                f"- {node.index}. type={control_type} | "
                f"name={name} | class={class_name} | "
                f"automation_id={automation_id}"
            )

        remaining_count = inspection.node_count - max_nodes_to_show

        if remaining_count > 0:
            lines.append(
                f"... {remaining_count} more nodes not shown."
            )

    return "\n".join(lines)