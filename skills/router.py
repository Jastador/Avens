from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from skills.app_launcher import (
    LaunchResult,
    clear_catalog_cache,
    launch_catalog_app,
    resolve_catalog_matches,
)

from skills.active_window import (
    ActiveWindowResult,
    control_active_window,
)

from skills.app_catalog import CatalogApp
from skills.named_window import (
    NamedWindowResult,
    control_named_window,
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

REFRESH_APP_CATALOG_SKILL = LocalSkillDefinition(
    name="refresh_app_catalog",
    allowed_arguments=(),
    offline=True,
    requires_confirmation=False,
)

ACTIVE_WINDOW_CONTROL_SKILL = LocalSkillDefinition(
    name="control_active_window",
    allowed_arguments=(
        "minimize",
        "maximize",
        "restore",
    ),
    offline=True,
    requires_confirmation=False,
)

NAMED_WINDOW_CONTROL_SKILL = LocalSkillDefinition(
    name="control_named_window",
    allowed_arguments=(
        "minimize",
        "maximize",
        "restore",
        "bring_up",
        "exact_catalog_app_name",
    ),
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

APP_CATALOG_REFRESH_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:refresh|update)\s+"
    r"(?:the\s+)?"
    r"(?:"
    r"apps?(?:\s+(?:catalog|list))?"
    r"|applications?(?:\s+(?:catalog|list))?"
    r")"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

ACTIVE_WINDOW_CONTROL_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?P<action>minimize|maximize|restore)"
    r"\s+this"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

NAMED_WINDOW_CONTROL_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?P<action>minimize|maximize|restore|bring\s+up)"
    r"(?:\s+|[,:;.!?]+\s*)"
    r"(?:the\s+)?"
    r"(?P<target>.+?)"
    r"(?:\s+please)?"
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
    refresh_catalog: Callable[[], None] = clear_catalog_cache,
    control_window: Callable[[str], ActiveWindowResult] = (
        control_active_window
    ),
    resolve_app: Callable[
        [str],
        tuple[CatalogApp, ...],
    ] = resolve_catalog_matches,
    control_named_app_window: Callable[
        [CatalogApp, str],
        NamedWindowResult,
    ] = control_named_window,
) -> SkillResult | None:
    """Handle explicit local skills before AI or legacy tools."""
    active_window_match = ACTIVE_WINDOW_CONTROL_PATTERN.match(
        user_input
    )

    if active_window_match is not None:
        action = active_window_match.group("action").lower()
        window_result = control_window(action)

        return SkillResult(
            handled=True,
            skill_name=ACTIVE_WINDOW_CONTROL_SKILL.name,
            message=window_result.message,
            offline=ACTIVE_WINDOW_CONTROL_SKILL.offline,
            requires_confirmation=(
                ACTIVE_WINDOW_CONTROL_SKILL.requires_confirmation
            ),
        )

    named_window_match = NAMED_WINDOW_CONTROL_PATTERN.match(
        user_input
    )

    if named_window_match is not None:
        action = (
            named_window_match.group("action")
            .casefold()
            .replace(" ", "_")
        )
        requested_name = _clean_target(
            named_window_match.group("target")
        )
        matches = resolve_app(requested_name)

        if not matches:
            display_name = requested_name or "that app"

            return SkillResult(
                handled=True,
                skill_name=NAMED_WINDOW_CONTROL_SKILL.name,
                message=(
                    f"I could not find an exact local app named "
                    f"{display_name}, sir."
                ),
                offline=NAMED_WINDOW_CONTROL_SKILL.offline,
                requires_confirmation=(
                    NAMED_WINDOW_CONTROL_SKILL
                    .requires_confirmation
                ),
            )

        if len(matches) > 1:
            return SkillResult(
                handled=True,
                skill_name=NAMED_WINDOW_CONTROL_SKILL.name,
                message=(
                    f"I found {len(matches)} exact local apps named "
                    f"{matches[0].display_name}. I will not guess "
                    "which one to control, sir."
                ),
                offline=NAMED_WINDOW_CONTROL_SKILL.offline,
                requires_confirmation=(
                    NAMED_WINDOW_CONTROL_SKILL
                    .requires_confirmation
                ),
            )

        window_result = control_named_app_window(
            matches[0],
            action,
        )

        return SkillResult(
            handled=True,
            skill_name=NAMED_WINDOW_CONTROL_SKILL.name,
            message=window_result.message,
            offline=NAMED_WINDOW_CONTROL_SKILL.offline,
            requires_confirmation=(
                NAMED_WINDOW_CONTROL_SKILL.requires_confirmation
            ),
        )

    refresh_match = APP_CATALOG_REFRESH_PATTERN.match(user_input)

    if refresh_match is not None:
        refresh_catalog()

        return SkillResult(
            handled=True,
            skill_name=REFRESH_APP_CATALOG_SKILL.name,
            message="I refreshed the local app list, sir.",
            offline=REFRESH_APP_CATALOG_SKILL.offline,
            requires_confirmation=(
                REFRESH_APP_CATALOG_SKILL.requires_confirmation
            ),
        )

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