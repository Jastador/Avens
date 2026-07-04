from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from skills.app_launcher import (
    APPROVED_APPS,
    LaunchResult,
    find_approved_app,
    launch_approved_app,
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
    allowed_arguments=tuple(
        app.app_id
        for app in APPROVED_APPS
    ),
    offline=True,
    requires_confirmation=False,
)

APP_LAUNCH_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:open|launch|start)\s+"
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


def _unsupported_app_result() -> SkillResult:
    """Stop unapproved launch requests before they reach Ollama."""
    return SkillResult(
        handled=True,
        skill_name=OPEN_APP_SKILL.name,
        message=(
            "That app is not in my approved local app list yet. "
            "For now, I can open Discord, Visual Studio Code, "
            "or Google Chrome."
        ),
        offline=OPEN_APP_SKILL.offline,
        requires_confirmation=OPEN_APP_SKILL.requires_confirmation,
    )


def route_local_skill(
    user_input: str,
    *,
    launch_app: Callable[[str], LaunchResult] = launch_approved_app,
) -> SkillResult | None:
    """Handle explicit local skills before any AI or legacy automation.

    Unknown app-launch requests are handled locally too. This prevents them
    from reaching Ollama, the old fuzzy launcher, or the Google-search route.
    """
    match = APP_LAUNCH_PATTERN.match(user_input)

    if match is None:
        return None

    app = find_approved_app(
        _clean_target(match.group("target"))
    )

    if app is None:
        return _unsupported_app_result()

    launch_result = launch_app(app.app_id)

    return SkillResult(
        handled=True,
        skill_name=OPEN_APP_SKILL.name,
        message=launch_result.message,
        offline=OPEN_APP_SKILL.offline,
        requires_confirmation=OPEN_APP_SKILL.requires_confirmation,
    )