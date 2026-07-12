from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Final

from skills.local_routine_settings import RoutineSettings
from skills.app_launcher import (
    LaunchResult,
    launch_catalog_app,
)
from skills.app_process_wait import (
    AppProcessWaitResult,
    wait_for_app_process,
)
from skills.app_window_focus import (
    AppWindowFocusResult,
    focus_app_window,
)
from skills.discord_voice_config import (
    DiscordVoiceConfigError,
    DiscordVoiceTarget,
    get_discord_voice_target,
)
from skills.discord_quick_switcher_join import (
    DiscordQuickSwitcherJoinResult,
    send_discord_quick_switcher_join_command,
)
from skills.app_window_wait import (
    AppWindowWaitResult,
    wait_for_app_window,
)
from skills.local_reminders import (
    LocalReminder,
    LocalRemindersError,
    REMINDER_KIND_TIMER,
    save_reminder,
)
from skills.local_routine_urls import (
    LocalRoutineUrlError,
    LocalRoutineUrlNotConfiguredError,
    UrlGroupOpenReport,
    open_approved_url_group,
)
from skills.reminder_schedule import (
    ReminderSchedule,
    ReminderScheduleError,
    schedule_after_duration,
)
from skills.system_controls import (
    BrightnessState,
    SystemControlError,
    VolumeState,
    open_night_light_settings,
    set_master_volume,
    set_primary_brightness,
)


ACTION_PREVIEW_ONLY: Final = "preview_only"
ACTION_LAUNCH_APP: Final = "launch_app"
ACTION_WAIT_FOR_APP_WINDOW: Final = "wait_for_app_window"
ACTION_WAIT_FOR_APP_PROCESS: Final = "wait_for_app_process"
ACTION_BRING_APP_WINDOW_TO_FRONT: Final = (
    "bring_app_window_to_front"
)
ACTION_RESOLVE_DISCORD_VOICE_TARGET: Final = (
    "resolve_discord_voice_target"
)
ACTION_JOIN_DISCORD_VOICE_TARGET: Final = (
    "join_discord_voice_target"
)
ACTION_APPROVED_URL_GROUP: Final = "approved_url_group"
ACTION_SET_BRIGHTNESS: Final = "set_brightness"
ACTION_SET_VOLUME: Final = "set_volume"
ACTION_START_TIMER: Final = "start_timer"
ACTION_OPEN_NIGHT_LIGHT_SETTINGS: Final = "open_night_light_settings"
ACTION_NITROSENSE_CONFIRMATION: Final = "nitrosense_confirmation"

ROUTINE_STEP_DONE: Final = "done"
ROUTINE_STEP_SKIPPED: Final = "skipped"
ROUTINE_STEP_NEEDS_CONFIRMATION: Final = "needs_confirmation"
ROUTINE_STEP_FAILED: Final = "failed"


class LocalRoutineError(ValueError):
    """Raised when a local routine cannot be resolved safely."""


@dataclass(frozen=True)
class RoutineAction:
    """One planned routine action."""

    label: str
    detail: str
    requires_confirmation: bool = False
    action_type: str = ACTION_PREVIEW_ONLY
    argument: str = ""


@dataclass(frozen=True)
class LocalRoutine:
    """A deterministic local routine definition."""

    routine_id: str
    display_name: str
    spoken_names: tuple[str, ...]
    description: str
    actions: tuple[RoutineAction, ...]


@dataclass(frozen=True)
class RoutineStepResult:
    """Result of executing or deliberately skipping one routine action."""

    action: RoutineAction
    status: str
    message: str


@dataclass(frozen=True)
class LocalRoutineRunReport:
    """Full result of one local routine run."""

    routine: LocalRoutine
    steps: tuple[RoutineStepResult, ...]

    @property
    def has_failed_steps(self) -> bool:
        """Return whether any routine step failed."""
        return any(
            step.status == ROUTINE_STEP_FAILED
            for step in self.steps
        )

    @property
    def requires_followup_confirmation(self) -> bool:
        """Return whether the routine left a confirmation pending."""
        return any(
            step.status == ROUTINE_STEP_NEEDS_CONFIRMATION
            for step in self.steps
        )


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
                action_type=ACTION_LAUNCH_APP,
                argument="Google Chrome",
            ),
            RoutineAction(
                label="Open approved URL group",
                detail="study URLs, configured privately later",
                action_type=ACTION_APPROVED_URL_GROUP,
                argument="study",
            ),
            RoutineAction(
                label="Set brightness",
                detail="100%",
                action_type=ACTION_SET_BRIGHTNESS,
                argument="100",
            ),
            RoutineAction(
                label="Set volume",
                detail="50%",
                action_type=ACTION_SET_VOLUME,
                argument="50",
            ),
            RoutineAction(
                label="Start timer",
                detail="50 minutes",
                action_type=ACTION_START_TIMER,
                argument="50",
            ),
            RoutineAction(
                label="Open settings",
                detail="Night Light Settings",
                action_type=ACTION_OPEN_NIGHT_LIGHT_SETTINGS,
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
                action_type=ACTION_LAUNCH_APP,
                argument="Visual Studio Code",
            ),
            RoutineAction(
                label="Launch app",
                detail="Android Studio",
                action_type=ACTION_LAUNCH_APP,
                argument="Android Studio",
            ),
            RoutineAction(
                label="Launch app",
                detail="Google Chrome",
                action_type=ACTION_LAUNCH_APP,
                argument="Google Chrome",
            ),
            RoutineAction(
                label="Open approved URL group",
                detail="project URLs, configured privately later",
                action_type=ACTION_APPROVED_URL_GROUP,
                argument="project",
            ),
            RoutineAction(
                label="Set brightness",
                detail="100%",
                action_type=ACTION_SET_BRIGHTNESS,
                argument="100",
            ),
            RoutineAction(
                label="Set volume",
                detail="50%",
                action_type=ACTION_SET_VOLUME,
                argument="50",
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
                detail="NitroSense",
                action_type=ACTION_LAUNCH_APP,
                argument="NitroSense",
            ),
            RoutineAction(
                label="Set NitroSense gaming profile",
                detail="Performance mode and Fan Max",
                requires_confirmation=True,
                action_type=ACTION_NITROSENSE_CONFIRMATION,
            ),
            RoutineAction(
                label="Launch app",
                detail="Discord",
                action_type=ACTION_LAUNCH_APP,
                argument="Discord",
            ),
            RoutineAction(
                label="Verify app window",
                detail="Discord",
                action_type=ACTION_WAIT_FOR_APP_WINDOW,
                argument="Discord",
            ),
            RoutineAction(
                label="Bring app window to foreground",
                detail="Discord",
                action_type=ACTION_BRING_APP_WINDOW_TO_FRONT,
                argument="Discord",
            ),
            RoutineAction(
                label="Resolve Discord voice target",
                detail="configured target",
                action_type=ACTION_RESOLVE_DISCORD_VOICE_TARGET,
            ),
            RoutineAction(
                label="Join Discord voice target",
                detail="configured target",
                action_type=ACTION_JOIN_DISCORD_VOICE_TARGET,
            ),
            RoutineAction(
                label="Launch app",
                detail="Steam",
                action_type=ACTION_LAUNCH_APP,
                argument="Steam",
            ),
            RoutineAction(
                label="Verify app process",
                detail="Steam",
                action_type=ACTION_WAIT_FOR_APP_PROCESS,
                argument="Steam",
            ),
            RoutineAction(
                label="Set brightness",
                detail="100%",
                action_type=ACTION_SET_BRIGHTNESS,
                argument="100",
            ),
            RoutineAction(
                label="Set volume",
                detail="50%",
                action_type=ACTION_SET_VOLUME,
                argument="50",
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
                action_type=ACTION_LAUNCH_APP,
                argument="Google Chrome",
            ),
            RoutineAction(
                label="Open approved URL group",
                detail="market URLs, configured privately later",
                action_type=ACTION_APPROVED_URL_GROUP,
                argument="market",
            ),
            RoutineAction(
                label="Set brightness",
                detail="100%",
                action_type=ACTION_SET_BRIGHTNESS,
                argument="100",
            ),
            RoutineAction(
                label="Set volume",
                detail="50%",
                action_type=ACTION_SET_VOLUME,
                argument="50",
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
            "",
            "Run commands:",
            "- Start study mode",
            "- Start project mode",
            "- Start gaming mode",
            "- Start market prep mode",
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

def _apply_routine_settings(
    action: RoutineAction,
    settings: RoutineSettings,
) -> RoutineAction:
    """Apply private brightness and volume overrides to one action."""
    if (
        action.action_type == ACTION_SET_BRIGHTNESS
        and settings.brightness is not None
    ):
        return replace(
            action,
            detail=f"{settings.brightness}%",
            argument=str(settings.brightness),
        )

    if (
        action.action_type == ACTION_SET_VOLUME
        and settings.volume is not None
    ):
        return replace(
            action,
            detail=f"{settings.volume}%",
            argument=str(settings.volume),
        )

    if (
        action.action_type
        in {
            ACTION_RESOLVE_DISCORD_VOICE_TARGET,
            ACTION_JOIN_DISCORD_VOICE_TARGET,
        }
        and settings.discord_voice_target_alias is not None
    ):
        return replace(
            action,
            detail=settings.discord_voice_target_alias,
            argument=settings.discord_voice_target_alias,
        )

    return action

def _run_launch_action(
    action: RoutineAction,
    *,
    launch_app: Callable[[str], LaunchResult],
) -> RoutineStepResult:
    """Run one exact app launch action."""
    result = launch_app(action.argument or action.detail)

    status = (
        ROUTINE_STEP_DONE
        if result.success
        else ROUTINE_STEP_FAILED
    )

    return RoutineStepResult(
        action=action,
        status=status,
        message=result.message,
    )


def _run_wait_for_app_window_action(
    action: RoutineAction,
    *,
    wait_for_window: Callable[[str], AppWindowWaitResult],
) -> RoutineStepResult:
    """Run one exact app-window verification action."""
    result = wait_for_window(action.argument or action.detail)

    status = (
        ROUTINE_STEP_DONE
        if result.success
        else ROUTINE_STEP_FAILED
    )

    return RoutineStepResult(
        action=action,
        status=status,
        message=result.message,
    )

def _run_wait_for_app_process_action(
    action: RoutineAction,
    *,
    wait_for_process: Callable[[str], AppProcessWaitResult],
) -> RoutineStepResult:
    """Run one exact app-process verification action."""
    result = wait_for_process(action.argument or action.detail)

    status = ROUTINE_STEP_DONE if result.success else ROUTINE_STEP_FAILED

    return RoutineStepResult(
        action=action,
        status=status,
        message=result.message,
    )

def _run_bring_app_window_to_front_action(
    action: RoutineAction,
    *,
    bring_window_to_front: Callable[[str], AppWindowFocusResult],
) -> RoutineStepResult:
    """Bring one exact app window to the foreground."""
    result = bring_window_to_front(action.argument or action.detail)

    status = ROUTINE_STEP_DONE if result.success else ROUTINE_STEP_FAILED

    return RoutineStepResult(
        action=action,
        status=status,
        message=result.message,
    )

def _run_resolve_discord_voice_target_action(
    action: RoutineAction,
    *,
    resolve_discord_voice_target: Callable[
        [str],
        DiscordVoiceTarget,
    ],
) -> RoutineStepResult:
    """Resolve one configured Discord voice target without joining."""
    target_alias = action.argument.strip()

    if not target_alias:
        return RoutineStepResult(
            action=action,
            status=ROUTINE_STEP_SKIPPED,
            message=(
                "Discord voice target is not configured for this "
                "routine, sir."
            ),
        )

    try:
        target = resolve_discord_voice_target(target_alias)
    except DiscordVoiceConfigError as error:
        return RoutineStepResult(
            action=action,
            status=ROUTINE_STEP_FAILED,
            message=str(error),
        )

    return RoutineStepResult(
        action=action,
        status=ROUTINE_STEP_DONE,
        message=(
            "Discord voice target resolved: "
            f"server '{target.server_name}', "
            f"channel '{target.channel_name}'. "
            "UI joining is not implemented yet, sir."
        ),
    )

def _run_join_discord_voice_target_action(
    action: RoutineAction,
    *,
    join_discord_voice_target: Callable[
        [str],
        DiscordQuickSwitcherJoinResult,
    ],
) -> RoutineStepResult:
    """Send one configured Discord Quick Switcher join command."""
    target_alias = action.argument.strip()

    if not target_alias:
        return RoutineStepResult(
            action=action,
            status=ROUTINE_STEP_SKIPPED,
            message=(
                "Discord voice target is not configured for this "
                "routine, sir."
            ),
        )

    result = join_discord_voice_target(target_alias)
    status = ROUTINE_STEP_DONE if result.success else ROUTINE_STEP_FAILED

    return RoutineStepResult(
        action=action,
        status=status,
        message=result.message,
    )

def _run_brightness_action(
    action: RoutineAction,
    *,
    set_brightness: Callable[[int], BrightnessState],
) -> RoutineStepResult:
    """Run one exact brightness action."""
    level = int(action.argument)
    state = set_brightness(level)

    return RoutineStepResult(
        action=action,
        status=ROUTINE_STEP_DONE,
        message=f"Brightness set to {state.level}%.",
    )


def _run_volume_action(
    action: RoutineAction,
    *,
    set_volume: Callable[[int], VolumeState],
) -> RoutineStepResult:
    """Run one exact volume action."""
    level = int(action.argument)
    state = set_volume(level)

    if state.muted:
        message = (
            f"Volume set to {state.level}%, but audio remains muted."
        )
    else:
        message = f"Volume set to {state.level}%."

    return RoutineStepResult(
        action=action,
        status=ROUTINE_STEP_DONE,
        message=message,
    )


def _run_timer_action(
    action: RoutineAction,
    *,
    schedule_timer_after: Callable[
        ...,
        ReminderSchedule,
    ],
    save_timer: Callable[..., LocalReminder],
) -> RoutineStepResult:
    """Run one local timer action."""
    minutes = int(action.argument)
    schedule = schedule_timer_after(
        hours=0,
        minutes=minutes,
        seconds=0,
    )
    reminder = save_timer(
        "Timer",
        kind=REMINDER_KIND_TIMER,
        due_at=schedule.due_at_utc,
    )

    return RoutineStepResult(
        action=action,
        status=ROUTINE_STEP_DONE,
        message=(
            f"Started local timer {reminder.reminder_id} for "
            f"{action.detail}."
        ),
    )

def _run_url_group_action(
    action: RoutineAction,
    *,
    open_url_group: Callable[[str], UrlGroupOpenReport],
) -> RoutineStepResult:
    """Run one approved private URL group action."""
    try:
        report = open_url_group(action.argument)
    except LocalRoutineUrlNotConfiguredError as error:
        return RoutineStepResult(
            action=action,
            status=ROUTINE_STEP_SKIPPED,
            message=str(error),
        )

    opened_count = len(report.opened_urls)
    url_word = "URL" if opened_count == 1 else "URLs"

    return RoutineStepResult(
        action=action,
        status=ROUTINE_STEP_DONE,
        message=(
            f"Opened {opened_count} approved {url_word} "
            f"for '{report.group_name}'."
        ),
    )

def _run_routine_action(
    action: RoutineAction,
    *,
    launch_app: Callable[[str], LaunchResult],
    wait_for_window: Callable[[str], AppWindowWaitResult],
    wait_for_process: Callable[[str], AppProcessWaitResult],
    bring_window_to_front: Callable[[str], AppWindowFocusResult],
    resolve_discord_voice_target: Callable[
        [str],
        DiscordVoiceTarget,
    ],
    join_discord_voice_target: Callable[
        [str],
        DiscordQuickSwitcherJoinResult,
    ],
    set_brightness: Callable[[int], BrightnessState],
    set_volume: Callable[[int], VolumeState],
    schedule_timer_after: Callable[
        ...,
        ReminderSchedule,
    ],
    save_timer: Callable[..., LocalReminder],
    open_night_light: Callable[[], None],
    open_url_group: Callable[[str], UrlGroupOpenReport],
    begin_nitrosense_confirmation: Callable[[], object] | None,
) -> RoutineStepResult:
    """Run one routine action using only approved local primitives."""
    if action.action_type == ACTION_LAUNCH_APP:
        return _run_launch_action(
            action,
            launch_app=launch_app,
        )

    if action.action_type == ACTION_WAIT_FOR_APP_WINDOW:
        return _run_wait_for_app_window_action(
            action,
            wait_for_window=wait_for_window,
        )

    if action.action_type == ACTION_WAIT_FOR_APP_PROCESS:
        return _run_wait_for_app_process_action(
            action,
            wait_for_process=wait_for_process,
        )

    if action.action_type == ACTION_BRING_APP_WINDOW_TO_FRONT:
        return _run_bring_app_window_to_front_action(
            action,
            bring_window_to_front=bring_window_to_front,
        )

    if action.action_type == ACTION_RESOLVE_DISCORD_VOICE_TARGET:
        return _run_resolve_discord_voice_target_action(
            action,
            resolve_discord_voice_target=resolve_discord_voice_target,
        )

    if action.action_type == ACTION_JOIN_DISCORD_VOICE_TARGET:
        return _run_join_discord_voice_target_action(
            action,
            join_discord_voice_target=join_discord_voice_target,
        )

    if action.action_type == ACTION_APPROVED_URL_GROUP:
        return _run_url_group_action(
            action,
            open_url_group=open_url_group,
        )

    if action.action_type == ACTION_SET_BRIGHTNESS:
        return _run_brightness_action(
            action,
            set_brightness=set_brightness,
        )

    if action.action_type == ACTION_SET_VOLUME:
        return _run_volume_action(
            action,
            set_volume=set_volume,
        )

    if action.action_type == ACTION_START_TIMER:
        return _run_timer_action(
            action,
            schedule_timer_after=schedule_timer_after,
            save_timer=save_timer,
        )

    if action.action_type == ACTION_OPEN_NIGHT_LIGHT_SETTINGS:
        open_night_light()

        return RoutineStepResult(
            action=action,
            status=ROUTINE_STEP_DONE,
            message="Opened Night Light Settings.",
        )

    if action.action_type == ACTION_NITROSENSE_CONFIRMATION:
        if begin_nitrosense_confirmation is not None:
            begin_nitrosense_confirmation()

        return RoutineStepResult(
            action=action,
            status=ROUTINE_STEP_NEEDS_CONFIRMATION,
            message=(
                "Gaming Mode confirmation requested. "
                'Say "Confirm gaming mode" to apply NitroSense '
                "and continue."
            ),
        )

    return RoutineStepResult(
        action=action,
        status=ROUTINE_STEP_SKIPPED,
        message="No approved runner exists for this action yet.",
    )


def run_local_routine(
    routine: LocalRoutine,
    *,
    launch_app: Callable[[str], LaunchResult] = launch_catalog_app,
    wait_for_window: Callable[[str], AppWindowWaitResult] = (
        wait_for_app_window
    ),
    wait_for_process: Callable[[str], AppProcessWaitResult] = (
        wait_for_app_process
    ),
    bring_window_to_front: Callable[[str], AppWindowFocusResult] = (
        focus_app_window
    ),
    resolve_discord_voice_target: Callable[
        [str],
        DiscordVoiceTarget,
    ] = get_discord_voice_target,
    join_discord_voice_target: Callable[
        [str],
        DiscordQuickSwitcherJoinResult,
    ] = send_discord_quick_switcher_join_command,
    set_brightness: Callable[[int], BrightnessState] = (
        set_primary_brightness
    ),
    set_volume: Callable[[int], VolumeState] = set_master_volume,
    schedule_timer_after: Callable[
        ...,
        ReminderSchedule,
    ] = schedule_after_duration,
    save_timer: Callable[..., LocalReminder] = save_reminder,
    open_night_light: Callable[[], None] = open_night_light_settings,
    open_url_group: Callable[[str], UrlGroupOpenReport] = (
        open_approved_url_group
    ),
    routine_settings: RoutineSettings | None = None,
    begin_nitrosense_confirmation: Callable[[], object] | None = None,
) -> LocalRoutineRunReport:
    """Run one deterministic local routine safely."""
    step_results = []
    settings = routine_settings or RoutineSettings()

    for action in routine.actions:
        effective_action = _apply_routine_settings(
            action,
            settings,
        )

        try:
            step_result = _run_routine_action(
                effective_action,
                launch_app=launch_app,
                wait_for_window=wait_for_window,
                wait_for_process=wait_for_process,
                bring_window_to_front=bring_window_to_front,
                resolve_discord_voice_target=(
                    resolve_discord_voice_target
                ),
                join_discord_voice_target=join_discord_voice_target,
                set_brightness=set_brightness,
                set_volume=set_volume,
                schedule_timer_after=schedule_timer_after,
                save_timer=save_timer,
                open_night_light=open_night_light,
                open_url_group=open_url_group,
                begin_nitrosense_confirmation=(
                    begin_nitrosense_confirmation
                ),
            )
        except (
            LocalRemindersError,
            LocalRoutineUrlError,
            ReminderScheduleError,
            SystemControlError,
            ValueError,
            RuntimeError,
        ) as error:
            step_result = RoutineStepResult(
                action=action,
                status=ROUTINE_STEP_FAILED,
                message=str(error),
            )

        step_results.append(step_result)

        if step_result.status == ROUTINE_STEP_NEEDS_CONFIRMATION:
            break

        if (
            step_result.status == ROUTINE_STEP_FAILED
            and effective_action.action_type
            in {
                ACTION_WAIT_FOR_APP_WINDOW,
                ACTION_WAIT_FOR_APP_PROCESS,
                ACTION_BRING_APP_WINDOW_TO_FRONT,
                ACTION_RESOLVE_DISCORD_VOICE_TARGET,
                ACTION_JOIN_DISCORD_VOICE_TARGET,
            }
        ):
            break

    return LocalRoutineRunReport(
        routine=routine,
        steps=tuple(step_results),
    )

def _confirmation_action_index(routine: LocalRoutine) -> int:
    """Return the first confirmation action index for a routine."""
    for index, action in enumerate(routine.actions):
        if action.action_type == ACTION_NITROSENSE_CONFIRMATION:
            return index

    raise LocalRoutineError(
        f"{routine.display_name} has no confirmation step to continue from."
    )


def continue_local_routine_after_confirmation(
    routine: LocalRoutine,
    *,
    confirmed_action_message: str,
    launch_app: Callable[[str], LaunchResult] = launch_catalog_app,
    wait_for_window: Callable[[str], AppWindowWaitResult] = (
        wait_for_app_window
    ),
    wait_for_process: Callable[[str], AppProcessWaitResult] = (
        wait_for_app_process
    ),
    bring_window_to_front: Callable[[str], AppWindowFocusResult] = (
        focus_app_window
    ),
    resolve_discord_voice_target: Callable[
        [str],
        DiscordVoiceTarget,
    ] = get_discord_voice_target,
    join_discord_voice_target: Callable[
        [str],
        DiscordQuickSwitcherJoinResult,
    ] = send_discord_quick_switcher_join_command,
    set_brightness: Callable[[int], BrightnessState] = (
        set_primary_brightness
    ),
    set_volume: Callable[[int], VolumeState] = set_master_volume,
    schedule_timer_after: Callable[
        ...,
        ReminderSchedule,
    ] = schedule_after_duration,
    save_timer: Callable[..., LocalReminder] = save_reminder,
    open_night_light: Callable[[], None] = open_night_light_settings,
    open_url_group: Callable[[str], UrlGroupOpenReport] = (
        open_approved_url_group
    ),
    routine_settings: RoutineSettings | None = None,
) -> LocalRoutineRunReport:
    """Continue one routine after its confirmation action is completed."""
    confirmation_index = _confirmation_action_index(routine)
    confirmation_action = routine.actions[confirmation_index]
    settings = routine_settings or RoutineSettings()

    step_results = [
        RoutineStepResult(
            action=confirmation_action,
            status=ROUTINE_STEP_DONE,
            message=confirmed_action_message,
        )
    ]

    for action in routine.actions[confirmation_index + 1:]:
        effective_action = _apply_routine_settings(
            action,
            settings,
        )

        try:
            step_result = _run_routine_action(
                effective_action,
                launch_app=launch_app,
                wait_for_window=wait_for_window,
                wait_for_process=wait_for_process,
                bring_window_to_front=bring_window_to_front,
                resolve_discord_voice_target=(
                    resolve_discord_voice_target
                ),
                join_discord_voice_target=join_discord_voice_target,
                set_brightness=set_brightness,
                set_volume=set_volume,
                schedule_timer_after=schedule_timer_after,
                save_timer=save_timer,
                open_night_light=open_night_light,
                open_url_group=open_url_group,
                begin_nitrosense_confirmation=None,
            )
        except (
            LocalRemindersError,
            LocalRoutineUrlError,
            ReminderScheduleError,
            SystemControlError,
            ValueError,
            RuntimeError,
        ) as error:
            step_result = RoutineStepResult(
                action=effective_action,
                status=ROUTINE_STEP_FAILED,
                message=str(error),
            )

        step_results.append(step_result)

        if step_result.status == ROUTINE_STEP_NEEDS_CONFIRMATION:
            break

        if (
            step_result.status == ROUTINE_STEP_FAILED
            and effective_action.action_type
            in {
                ACTION_WAIT_FOR_APP_WINDOW,
                ACTION_WAIT_FOR_APP_PROCESS,
                ACTION_BRING_APP_WINDOW_TO_FRONT,
                ACTION_RESOLVE_DISCORD_VOICE_TARGET,
                ACTION_JOIN_DISCORD_VOICE_TARGET,
            }
        ):
            break

    return LocalRoutineRunReport(
        routine=routine,
        steps=tuple(step_results),
    )

def format_routine_run_report(
    report: LocalRoutineRunReport,
) -> str:
    """Format the full routine execution report."""
    lines = [
        f"{report.routine.display_name} run result:",
        "",
    ]

    for index, step in enumerate(report.steps, start=1):
        lines.append(
            f"{index}. [{step.status}] "
            f"{step.action.label}: {step.action.detail}"
        )
        lines.append(f"   {step.message}")

    if report.has_failed_steps:
        lines.extend(
            (
                "",
                "Some routine actions failed. Completed actions were "
                "not rolled back.",
            )
        )
    elif report.requires_followup_confirmation:
        lines.extend(
            (
                "",
                "Routine paused before remaining actions.",
                'Follow-up required: say "Confirm gaming mode" '
                "to continue.",
            )
        )
    else:
        lines.extend(
            (
                "",
                "Routine completed.",
            )
        )

    if any(
        step.status == ROUTINE_STEP_SKIPPED
        for step in report.steps
    ):
        lines.append(
            "Skipped actions are either not configured privately yet "
            "or intentionally unavailable."
        )

    return "\n".join(lines)