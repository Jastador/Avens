from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from skills.app_launcher import (
    LaunchResult,
    launch_catalog_app,
)


@dataclass(frozen=True)
class LocalSkillDefinition:
    """Metadata required for every deterministic local skill."""

    name: str
    allowed_arguments: tuple[str, ...]
    offline: bool
    requires_confirmation: bool


@dataclass(frozen=True)
class SkillResult:
    """Result returned to app.py when a local skill handles a request."""

    handled: bool
    skill_name: str
    message: str
    offline: bool
    requires_confirmation: bool


OPEN_APP_SKILL = LocalSkillDefinition(
    name="open_app",
    allowed_arguments=("exact_start_menu_app_name",),
    offline=True,
    requires_confirmation=False,
)

APP_LAUNCH_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:open|launch|start)"
    r"(?:\s+|[,:;.!?]+\s*)"
    r"(?:the\s+)?"
    r"(?P<target>.+?)"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)


def _clean_target(target: str) -> str:
    """Remove trailing politeness without guessing an app name."""
    return re.sub(
        r"\bplease\b\s*$",
        "",
        target,
        flags=re.IGNORECASE,
    ).strip()


def route_local_skill(
    user_input: str,
    *,
    launch_app: Callable[[str], LaunchResult] = launch_catalog_app,
) -> SkillResult | None:
    """Handle explicit local app-launch requests before AI or legacy tools."""
    match = APP_LAUNCH_PATTERN.match(user_input)

    if match is None:
        return None

    requested_name = _clean_target(match.group("target"))
    launch_result = launch_app(requested_name)

    return SkillResult(
        handled=True,
        skill_name=OPEN_APP_SKILL.name,
        message=launch_result.message,
        offline=OPEN_APP_SKILL.offline,
        requires_confirmation=OPEN_APP_SKILL.requires_confirmation,
    )