from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from config import LOCAL_DATA_DIR

from skills.app_launcher import (
    LaunchResult,
    clear_catalog_cache,
    launch_catalog_app,
    resolve_catalog_matches,
    get_catalog_snapshot,
)

from skills.active_window import (
    ActiveWindowResult,
    control_active_window,
)

from skills.app_catalog import CatalogApp
from skills.app_aliases import load_app_aliases
from skills.app_catalog_inspector import (
    CatalogReport,
    build_app_controls_guide,
    build_catalog_report,
    build_supported_controls_guide,
    format_catalog_search_result,
    search_catalog,
    write_catalog_report,
)
from skills.close_confirmation import (
    CloseConfirmationStore,
    close_confirmation_store,
)

from skills.named_window import (
    NamedWindowMatchResult,
    NamedWindowResult,
    close_named_app_windows,
    control_named_window,
    inspect_named_app_windows,
)

APP_CATALOG_REPORT_PATH = (
    LOCAL_DATA_DIR
    / "reports"
    / "app_catalog_report.txt"
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

LIST_APP_CATALOG_SKILL = LocalSkillDefinition(
    name="list_app_catalog",
    allowed_arguments=(),
    offline=True,
    requires_confirmation=False,
)

SEARCH_APP_CATALOG_SKILL = LocalSkillDefinition(
    name="search_app_catalog",
    allowed_arguments=("query",),
    offline=True,
    requires_confirmation=False,
)

SHOW_LOCAL_CONTROLS_SKILL = LocalSkillDefinition(
    name="show_local_controls",
    allowed_arguments=(),
    offline=True,
    requires_confirmation=False,
)

SHOW_APP_CONTROLS_SKILL = LocalSkillDefinition(
    name="show_app_controls",
    allowed_arguments=("exact_catalog_app_name",),
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

NAMED_WINDOW_CLOSE_SKILL = LocalSkillDefinition(
    name="close_named_window",
    allowed_arguments=(
        "close",
        "close_all",
        "exact_catalog_app_name",
    ),
    offline=True,
    requires_confirmation=True,
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

APP_CATALOG_LIST_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:list|show)\s+"
    r"(?:(?:all)\s+)?"
    r"(?:the\s+)?"
    r"(?:apps?|applications?)"
    r"(?:\s+(?:catalog|list))?"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

APP_CATALOG_SEARCH_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:search|find)\s+"
    r"(?:the\s+)?"
    r"(?:apps?|applications?)"
    r"(?:\s+for)?\s+"
    r"(?P<query>.+?)"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

LOCAL_CONTROLS_GUIDE_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"what\s+can\s+(?:you|i)\s+control"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

APP_CONTROLS_GUIDE_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"what\s+can\s+(?:you|i)\s+do\s+with"
    r"(?:\s+|[,:;.!?]+\s*)"
    r"(?:the\s+)?"
    r"(?P<target>.+?)"
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

NAMED_WINDOW_CLOSE_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"close\s+"
    r"(?:(?P<close_all>all)\s+)?"
    r"(?:the\s+)?"
    r"(?P<target>.+?)"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

CONFIRM_NAMED_WINDOW_CLOSE_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"confirm(?:\s+|[,:;.!?]+\s*)close\s+"
    r"(?:(?P<close_all>all)\s+)?"
    r"(?:the\s+)?"
    r"(?P<target>.+?)"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

CANCEL_NAMED_WINDOW_CLOSE_PATTERN = re.compile(
    r"^\s*"
    r"(?:cancel|cancel\s+close|never\s+mind|forget\s+it)"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

LOCAL_SKILL_REQUEST_PATTERNS = (
    APP_LAUNCH_PATTERN,
    APP_CATALOG_REFRESH_PATTERN,
    APP_CATALOG_LIST_PATTERN,
    APP_CATALOG_SEARCH_PATTERN,
    LOCAL_CONTROLS_GUIDE_PATTERN,
    APP_CONTROLS_GUIDE_PATTERN,
    ACTIVE_WINDOW_CONTROL_PATTERN,
    NAMED_WINDOW_CONTROL_PATTERN,
    NAMED_WINDOW_CLOSE_PATTERN,
    CONFIRM_NAMED_WINDOW_CLOSE_PATTERN,
    CANCEL_NAMED_WINDOW_CLOSE_PATTERN,
)


def is_explicit_local_skill_request(user_input: str) -> bool:
    """Return whether text has an explicit local-skill grammar match.

    This function is intentionally side-effect free. It must not resolve
    apps, open windows, create close confirmations, or execute a skill.
    """
    if not isinstance(user_input, str):
        return False

    return any(
        pattern.match(user_input) is not None
        for pattern in LOCAL_SKILL_REQUEST_PATTERNS
    )

def _clean_target(target: str) -> str:
    """Remove trailing politeness without guessing an app name."""
    return re.sub(
        r"\bplease\b\s*$",
        "",
        target,
        flags=re.IGNORECASE,
    ).strip()

def _clean_close_target(
    target: str,
    *,
    close_all: bool,
) -> str:
    """Remove close-only trailing words without weakening app matching."""
    cleaned = _clean_target(target)

    if close_all:
        cleaned = re.sub(
            r"\s+windows?\s*$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()

    return cleaned


def _close_confirmation_phrase(
    requested_name: str,
    *,
    close_all: bool,
) -> str:
    """Return the exact phrase required for one destructive action."""
    scope = "all " if close_all else ""
    suffix = " windows" if close_all else ""

    return (
        f"Confirm close {scope}{requested_name}{suffix}"
    )

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
    inspect_app_windows: Callable[
        [CatalogApp],
        NamedWindowMatchResult,
    ] = inspect_named_app_windows,
    close_app_windows: Callable[
        [CatalogApp, bool],
        NamedWindowResult,
    ] = close_named_app_windows,
    close_confirmations: CloseConfirmationStore = (
        close_confirmation_store
    ),
    catalog_snapshot: Callable[[], tuple[CatalogApp, ...]] = (
        get_catalog_snapshot
    ),
    get_aliases: Callable[[], dict[str, str]] = load_app_aliases,
    write_report: Callable[[CatalogReport, Path], Path] = (
        write_catalog_report
    ),
    console_output: Callable[[str], None] = print,
    catalog_report_path: Path = APP_CATALOG_REPORT_PATH,
) -> SkillResult | None:
    """Handle explicit local skills before AI or legacy tools."""
    confirm_close_match = CONFIRM_NAMED_WINDOW_CLOSE_PATTERN.match(
        user_input
    )

    if confirm_close_match is not None:
        close_all = bool(
            confirm_close_match.group("close_all")
        )
        requested_name = _clean_close_target(
            confirm_close_match.group("target"),
            close_all=close_all,
        )
        decision = close_confirmations.confirm(
            requested_name,
            close_all=close_all,
        )

        if decision.status == "none":
            return SkillResult(
                handled=True,
                skill_name=NAMED_WINDOW_CLOSE_SKILL.name,
                message=(
                    "There is no pending close request to confirm, "
                    "sir."
                ),
                offline=NAMED_WINDOW_CLOSE_SKILL.offline,
                requires_confirmation=(
                    NAMED_WINDOW_CLOSE_SKILL.requires_confirmation
                ),
            )

        if decision.status == "expired":
            return SkillResult(
                handled=True,
                skill_name=NAMED_WINDOW_CLOSE_SKILL.name,
                message=(
                    "That close confirmation expired. Ask me to close "
                    f"{decision.request.display_name} again, sir."
                ),
                offline=NAMED_WINDOW_CLOSE_SKILL.offline,
                requires_confirmation=(
                    NAMED_WINDOW_CLOSE_SKILL.requires_confirmation
                ),
            )

        if decision.status == "mismatch":
            return SkillResult(
                handled=True,
                skill_name=NAMED_WINDOW_CLOSE_SKILL.name,
                message=(
                    "That confirmation did not match the pending close "
                    "request, so I cancelled it, sir."
                ),
                offline=NAMED_WINDOW_CLOSE_SKILL.offline,
                requires_confirmation=(
                    NAMED_WINDOW_CLOSE_SKILL.requires_confirmation
                ),
            )

        pending_request = decision.request
        matches = resolve_app(pending_request.requested_name)

        if not matches:
            return SkillResult(
                handled=True,
                skill_name=NAMED_WINDOW_CLOSE_SKILL.name,
                message=(
                    f"I could not find an exact local app named "
                    f"{pending_request.requested_name}, sir."
                ),
                offline=NAMED_WINDOW_CLOSE_SKILL.offline,
                requires_confirmation=(
                    NAMED_WINDOW_CLOSE_SKILL.requires_confirmation
                ),
            )

        if len(matches) > 1:
            return SkillResult(
                handled=True,
                skill_name=NAMED_WINDOW_CLOSE_SKILL.name,
                message=(
                    f"I found {len(matches)} exact local apps named "
                    f"{matches[0].display_name}. I will not guess "
                    "which one to close, sir."
                ),
                offline=NAMED_WINDOW_CLOSE_SKILL.offline,
                requires_confirmation=(
                    NAMED_WINDOW_CLOSE_SKILL.requires_confirmation
                ),
            )

        close_result = close_app_windows(
            matches[0],
            pending_request.close_all,
        )

        return SkillResult(
            handled=True,
            skill_name=NAMED_WINDOW_CLOSE_SKILL.name,
            message=close_result.message,
            offline=NAMED_WINDOW_CLOSE_SKILL.offline,
            requires_confirmation=(
                NAMED_WINDOW_CLOSE_SKILL.requires_confirmation
            ),
        )

    if CANCEL_NAMED_WINDOW_CLOSE_PATTERN.match(user_input):
        cancelled_request = close_confirmations.cancel()

        if cancelled_request is not None:
            return SkillResult(
                handled=True,
                skill_name=NAMED_WINDOW_CLOSE_SKILL.name,
                message="Pending close request cancelled, sir.",
                offline=NAMED_WINDOW_CLOSE_SKILL.offline,
                requires_confirmation=(
                    NAMED_WINDOW_CLOSE_SKILL.requires_confirmation
                ),
            )

    close_match = NAMED_WINDOW_CLOSE_PATTERN.match(user_input)

    if close_match is not None:
        close_all = bool(close_match.group("close_all"))
        requested_name = _clean_close_target(
            close_match.group("target"),
            close_all=close_all,
        )

        if requested_name.casefold() == "this":
            return None

        matches = resolve_app(requested_name)

        if not matches:
            display_name = requested_name or "that app"

            return SkillResult(
                handled=True,
                skill_name=NAMED_WINDOW_CLOSE_SKILL.name,
                message=(
                    f"I could not find an exact local app named "
                    f"{display_name}, sir."
                ),
                offline=NAMED_WINDOW_CLOSE_SKILL.offline,
                requires_confirmation=(
                    NAMED_WINDOW_CLOSE_SKILL.requires_confirmation
                ),
            )

        if len(matches) > 1:
            return SkillResult(
                handled=True,
                skill_name=NAMED_WINDOW_CLOSE_SKILL.name,
                message=(
                    f"I found {len(matches)} exact local apps named "
                    f"{matches[0].display_name}. I will not guess "
                    "which one to close, sir."
                ),
                offline=NAMED_WINDOW_CLOSE_SKILL.offline,
                requires_confirmation=(
                    NAMED_WINDOW_CLOSE_SKILL.requires_confirmation
                ),
            )

        match_result = inspect_app_windows(matches[0])

        if match_result.error_message is not None:
            return SkillResult(
                handled=True,
                skill_name=NAMED_WINDOW_CLOSE_SKILL.name,
                message=match_result.error_message,
                offline=NAMED_WINDOW_CLOSE_SKILL.offline,
                requires_confirmation=(
                    NAMED_WINDOW_CLOSE_SKILL.requires_confirmation
                ),
            )

        window_count = len(match_result.window_handles)

        if not window_count:
            return SkillResult(
                handled=True,
                skill_name=NAMED_WINDOW_CLOSE_SKILL.name,
                message=(
                    f"{match_result.display_name} is not currently "
                    "open, sir."
                ),
                offline=NAMED_WINDOW_CLOSE_SKILL.offline,
                requires_confirmation=(
                    NAMED_WINDOW_CLOSE_SKILL.requires_confirmation
                ),
            )

        if not close_all and window_count > 1:
            return SkillResult(
                handled=True,
                skill_name=NAMED_WINDOW_CLOSE_SKILL.name,
                message=(
                    f"I found {window_count} "
                    f"{match_result.display_name} windows. I will not "
                    "guess which one to close, sir. Ask me to close "
                    "all matching windows instead."
                ),
                offline=NAMED_WINDOW_CLOSE_SKILL.offline,
                requires_confirmation=(
                    NAMED_WINDOW_CLOSE_SKILL.requires_confirmation
                ),
            )

        close_confirmations.begin(
            requested_name,
            match_result.display_name,
            close_all=close_all,
        )

        window_word = (
            "window"
            if window_count == 1
            else "windows"
        )
        confirmation_phrase = _close_confirmation_phrase(
            requested_name,
            close_all=close_all,
        )

        return SkillResult(
            handled=True,
            skill_name=NAMED_WINDOW_CLOSE_SKILL.name,
            message=(
                f"I found {window_count} "
                f"{match_result.display_name} {window_word}. Say "
                f'"{confirmation_phrase}" to continue, sir.'
            ),
            offline=NAMED_WINDOW_CLOSE_SKILL.offline,
            requires_confirmation=(
                NAMED_WINDOW_CLOSE_SKILL.requires_confirmation
            ),
        )

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
    list_catalog_match = APP_CATALOG_LIST_PATTERN.match(user_input)

    if list_catalog_match is not None:
        report = build_catalog_report(
            catalog_snapshot(),
            get_aliases(),
        )
        saved_report_path = write_report(
            report,
            catalog_report_path,
        )

        console_output(report.text)
        console_output(
            f"Saved app catalog report: {saved_report_path}"
        )

        return SkillResult(
            handled=True,
            skill_name=LIST_APP_CATALOG_SKILL.name,
            message=(
                f"I found {report.entry_count} local catalog entries "
                f"and {report.alias_count} aliases. I printed the "
                "full list and saved it in my local reports folder, "
                "sir."
            ),
            offline=LIST_APP_CATALOG_SKILL.offline,
            requires_confirmation=(
                LIST_APP_CATALOG_SKILL.requires_confirmation
            ),
        )

    search_catalog_match = APP_CATALOG_SEARCH_PATTERN.match(user_input)

    if search_catalog_match is not None:
        query = _clean_target(
            search_catalog_match.group("query")
        )
        search_result = search_catalog(
            query,
            catalog_snapshot(),
            get_aliases(),
        )

        console_output(
            format_catalog_search_result(search_result)
        )

        match_count = len(search_result.apps)
        alias_count = len(search_result.aliases)

        if not match_count and not alias_count:
            message = (
                f"I found no local catalog or alias matches for "
                f"{query}, sir."
            )
        else:
            message = (
                f"I found {match_count} catalog entries and "
                f"{alias_count} aliases matching {query}. I printed "
                "the details, sir."
            )

        return SkillResult(
            handled=True,
            skill_name=SEARCH_APP_CATALOG_SKILL.name,
            message=message,
            offline=SEARCH_APP_CATALOG_SKILL.offline,
            requires_confirmation=(
                SEARCH_APP_CATALOG_SKILL.requires_confirmation
            ),
        )

    local_controls_match = LOCAL_CONTROLS_GUIDE_PATTERN.match(
        user_input
    )

    if local_controls_match is not None:
        console_output(build_supported_controls_guide())

        return SkillResult(
            handled=True,
            skill_name=SHOW_LOCAL_CONTROLS_SKILL.name,
            message=(
                "I printed the full safe local-control guide, sir."
            ),
            offline=SHOW_LOCAL_CONTROLS_SKILL.offline,
            requires_confirmation=(
                SHOW_LOCAL_CONTROLS_SKILL.requires_confirmation
            ),
        )

    app_controls_match = APP_CONTROLS_GUIDE_PATTERN.match(user_input)

    if app_controls_match is not None:
        requested_name = _clean_target(
            app_controls_match.group("target")
        )
        matches = resolve_app(requested_name)

        if not matches:
            display_name = requested_name or "that app"

            return SkillResult(
                handled=True,
                skill_name=SHOW_APP_CONTROLS_SKILL.name,
                message=(
                    f"I could not find an exact local app named "
                    f"{display_name}, sir. Use Search apps "
                    f"{display_name} to inspect similar entries."
                ),
                offline=SHOW_APP_CONTROLS_SKILL.offline,
                requires_confirmation=(
                    SHOW_APP_CONTROLS_SKILL.requires_confirmation
                ),
            )

        if len(matches) > 1:
            return SkillResult(
                handled=True,
                skill_name=SHOW_APP_CONTROLS_SKILL.name,
                message=(
                    f"I found {len(matches)} exact local apps named "
                    f"{matches[0].display_name}. I will not guess "
                    "which one to inspect, sir."
                ),
                offline=SHOW_APP_CONTROLS_SKILL.offline,
                requires_confirmation=(
                    SHOW_APP_CONTROLS_SKILL.requires_confirmation
                ),
            )

        console_output(
            build_app_controls_guide(matches[0])
        )

        return SkillResult(
            handled=True,
            skill_name=SHOW_APP_CONTROLS_SKILL.name,
            message=(
                f"I printed the safe controls for "
                f"{matches[0].display_name}, sir."
            ),
            offline=SHOW_APP_CONTROLS_SKILL.offline,
            requires_confirmation=(
                SHOW_APP_CONTROLS_SKILL.requires_confirmation
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