from __future__ import annotations

from dataclasses import dataclass
from typing import Final


class LocalRoutineError(ValueError):
    """Raised when a local routine cannot be resolved safely."""


@dataclass(frozen=True)
class RoutineAction:
    """One planned routine action, not executed by the preview layer."""

    label: str
    detail: str
    requires_confirmation: bool = False


@dataclass(frozen=True)
class LocalRoutine:
    """A deterministic local routine definition."""

    routine_id: str
    display_name: str
    spoken_names: tuple[str, ...]
    description: str
    actions: tuple[RoutineAction, ...]


LOCAL_ROUTINES: Final[tuple[LocalRoutine, ...]] = (
    LocalRoutine(
        routine_id="study",
        display_name="Study Mode",
        spoken_names=(
            "study mode",
            "german study mode",
        ),
        description="Sets up the local German-study workspace.",
        actions=(
            RoutineAction(
                label="Launch app",
                detail="Google Chrome",
            ),
            RoutineAction(
                label="Open approved URL group",
                detail="study URLs, configured privately later",
            ),
            RoutineAction(
                label="Set brightness",
                detail="100%",
            ),
            RoutineAction(
                label="Set volume",
                detail="50%",
            ),
            RoutineAction(
                label="Start timer",
                detail="50 minutes",
            ),
            RoutineAction(
                label="Open settings",
                detail="Night Light Settings",
            ),
        ),
    ),
    LocalRoutine(
        routine_id="project_dev",
        display_name="Project/Dev Mode",
        spoken_names=(
            "project mode",
            "dev mode",
            "project dev mode",
            "development mode",
        ),
        description="Sets up the local coding workspace.",
        actions=(
            RoutineAction(
                label="Launch app",
                detail="Visual Studio Code",
            ),
            RoutineAction(
                label="Launch app",
                detail="Google Chrome",
            ),
            RoutineAction(
                label="Open approved URL group",
                detail="project URLs, configured privately later",
            ),
            RoutineAction(
                label="Set brightness",
                detail="100%",
            ),
            RoutineAction(
                label="Set volume",
                detail="50%",
            ),
        ),
    ),
    LocalRoutine(
        routine_id="gaming",
        display_name="Gaming Mode",
        spoken_names=(
            "gaming mode",
            "game mode",
        ),
        description="Sets up the local gaming workspace.",
        actions=(
            RoutineAction(
                label="Launch app",
                detail="Steam",
            ),
            RoutineAction(
                label="Launch app",
                detail="Discord",
            ),
            RoutineAction(
                label="Set brightness",
                detail="100%",
            ),
            RoutineAction(
                label="Set volume",
                detail="50%",
            ),
            RoutineAction(
                label="Set NitroSense gaming profile",
                detail="Performance mode and Fan Max",
                requires_confirmation=True,
            ),
        ),
    ),
    LocalRoutine(
        routine_id="market_prep",
        display_name="Market-Prep Mode",
        spoken_names=(
            "market prep mode",
            "market-prep mode",
            "market mode",
            "trading prep mode",
        ),
        description=(
            "Sets up the local market-prep workspace without "
            "placing or modifying trades."
        ),
        actions=(
            RoutineAction(
                label="Launch app",
                detail="Google Chrome",
            ),
            RoutineAction(
                label="Open approved URL group",
                detail="market URLs, configured privately later",
            ),
            RoutineAction(
                label="Set brightness",
                detail="100%",
            ),
            RoutineAction(
                label="Set volume",
                detail="50%",
            ),
        ),
    ),
)


def _normalise_routine_name(value: str) -> str:
    """Normalise one spoken routine name without guessing."""
    return " ".join(value.strip().casefold().replace("-", " ").split())


def list_local_routines() -> tuple[LocalRoutine, ...]:
    """Return the deterministic local routine registry."""
    return LOCAL_ROUTINES


def get_routine_definition(
    requested_name: str,
) -> LocalRoutine:
    """Resolve one exact routine name or spoken alias."""
    normalised_name = _normalise_routine_name(requested_name)

    if not normalised_name:
        raise LocalRoutineError("Routine name cannot be empty.")

    for routine in LOCAL_ROUTINES:
        possible_names = (
            routine.routine_id.replace("_", " "),
            routine.display_name,
            *routine.spoken_names,
        )

        if normalised_name in {
            _normalise_routine_name(name)
            for name in possible_names
        }:
            return routine

    raise LocalRoutineError(
        f"Unknown local routine: {requested_name.strip()}"
    )


def format_routine_list(
    routines: tuple[LocalRoutine, ...] = LOCAL_ROUTINES,
) -> str:
    """Format all available local routines for console output."""
    lines = ["Available local routines:"]

    for routine in routines:
        lines.append(
            f"- {routine.display_name}: {routine.description}"
        )

    lines.extend(
        (
            "",
            "Preview commands:",
            "- What routines do you have?",
            "- What does study mode do?",
            "- What does gaming mode do?",
        )
    )

    return "\n".join(lines)


def format_routine_preview(
    routine: LocalRoutine,
) -> str:
    """Format one routine plan without executing it."""
    lines = [
        f"{routine.display_name}",
        routine.description,
        "",
        "Planned actions:",
    ]

    for index, action in enumerate(routine.actions, start=1):
        confirmation_note = (
            " [requires confirmation]"
            if action.requires_confirmation
            else ""
        )
        lines.append(
            f"{index}. {action.label}: "
            f"{action.detail}{confirmation_note}"
        )

    lines.extend(
        (
            "",
            "Preview only: no apps, URLs, settings, timers, or "
            "hardware controls were changed.",
        )
    )

    return "\n".join(lines)