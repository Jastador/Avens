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

from skills.local_file_discovery import (
    LocalFileDiscoveryError,
    LocalFileSearchReport,
    format_local_file_search,
    format_local_file_search_scope,
    search_local_files,
)

from skills.local_notes import (
    LocalNote,
    LocalNotesError,
    format_note_search,
    format_notes,
    load_notes,
    save_note,
    search_notes,
    delete_note,
)

from skills.note_delete_confirmation import (
    NoteDeleteConfirmationStore,
    note_delete_confirmation_store,
)

from skills.local_reminders import (
    LocalReminder,
    LocalRemindersError,
    REMINDER_KIND_REMINDER,
    REMINDER_KIND_TIMER,
    REMINDER_STATUS_PENDING,
    cancel_reminder,
    format_reminders,
    load_reminders,
    save_reminder,
)

from skills.reminder_cancel_confirmation import (
    ReminderCancelConfirmationStore,
    reminder_cancel_confirmation_store,
)

from skills.reminder_schedule import (
    ReminderSchedule,
    ReminderScheduleError,
    parse_duration_components,
    schedule_after_duration,
    schedule_tomorrow_at,
)

from skills.system_controls import (
    BrightnessState,
    DEFAULT_BRIGHTNESS_STEP,
    DEFAULT_VOLUME_STEP,
    ReadingModeResult,
    SystemControlError,
    VolumeState,
    adjust_master_volume,
    adjust_primary_brightness,
    get_master_volume,
    get_primary_brightness,
    open_night_light_settings,
    set_master_mute,
    set_master_volume,
    set_primary_brightness,
    start_reading_mode,
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

SEARCH_LOCAL_FILES_SKILL = LocalSkillDefinition(
    name="search_local_files",
    allowed_arguments=("filename_query",),
    offline=True,
    requires_confirmation=False,
)

SHOW_LOCAL_FILE_SEARCH_SCOPE_SKILL = LocalSkillDefinition(
    name="show_local_file_search_scope",
    allowed_arguments=(),
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

CREATE_LOCAL_NOTE_SKILL = LocalSkillDefinition(
    name="create_local_note",
    allowed_arguments=("note_text",),
    offline=True,
    requires_confirmation=False,
)

LIST_LOCAL_NOTES_SKILL = LocalSkillDefinition(
    name="list_local_notes",
    allowed_arguments=(),
    offline=True,
    requires_confirmation=False,
)

SEARCH_LOCAL_NOTES_SKILL = LocalSkillDefinition(
    name="search_local_notes",
    allowed_arguments=("query",),
    offline=True,
    requires_confirmation=False,
)

DELETE_LOCAL_NOTE_SKILL = LocalSkillDefinition(
    name="delete_local_note",
    allowed_arguments=("note_id",),
    offline=True,
    requires_confirmation=True,
)

CREATE_LOCAL_TIMER_SKILL = LocalSkillDefinition(
    name="create_local_timer",
    allowed_arguments=(
        "duration_hours",
        "duration_minutes",
        "duration_seconds",
    ),
    offline=True,
    requires_confirmation=False,
)

CREATE_LOCAL_REMINDER_SKILL = LocalSkillDefinition(
    name="create_local_reminder",
    allowed_arguments=(
        "text",
        "due_at_utc",
    ),
    offline=True,
    requires_confirmation=False,
)

LIST_LOCAL_REMINDERS_SKILL = LocalSkillDefinition(
    name="list_local_reminders",
    allowed_arguments=(),
    offline=True,
    requires_confirmation=False,
)

CANCEL_LOCAL_REMINDER_SKILL = LocalSkillDefinition(
    name="cancel_local_reminder",
    allowed_arguments=("reminder_id",),
    offline=True,
    requires_confirmation=True,
)

MASTER_VOLUME_SKILL = LocalSkillDefinition(
    name="control_master_volume",
    allowed_arguments=(
        "set_level_percent",
        "adjust_percent",
        "mute_state",
        "read_state",
    ),
    offline=True,
    requires_confirmation=False,
)

PRIMARY_BRIGHTNESS_SKILL = LocalSkillDefinition(
    name="control_primary_brightness",
    allowed_arguments=(
        "set_level_percent",
        "adjust_percent",
        "read_state",
    ),
    offline=True,
    requires_confirmation=False,
)

OPEN_NIGHT_LIGHT_SETTINGS_SKILL = LocalSkillDefinition(
    name="open_night_light_settings",
    allowed_arguments=(),
    offline=True,
    requires_confirmation=False,
)

START_READING_SETUP_SKILL = LocalSkillDefinition(
    name="start_reading_setup",
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

LOCAL_FILE_SEARCH_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:find|search)\s+"
    r"(?:my\s+)?"
    r"files?"
    r"(?:\s+for)?\s+"
    r"(?P<query>.+?)"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

LOCAL_FILE_SEARCH_SCOPE_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"what\s+files?\s+can\s+(?:you|i)\s+search"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

LOCAL_NOTE_CREATE_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:take|add)\s+"
    r"(?:a\s+)?"
    r"note"
    r"(?:\s+|[,:;.!?]+\s*)"
    r"(?P<text>.+?)"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

LOCAL_NOTE_LIST_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:show|list)\s+"
    r"(?:my\s+)?"
    r"notes"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

LOCAL_NOTE_SEARCH_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:search|find)\s+"
    r"(?:my\s+)?"
    r"notes?"
    r"\s+"
    r"(?:for\s+)?"
    r"(?P<query>.+?)"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

LOCAL_NOTE_DELETE_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"delete\s+"
    r"(?:my\s+)?"
    r"note\s+"
    r"(?P<note_id>[0-9]+)"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

CONFIRM_LOCAL_NOTE_DELETE_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"confirm(?:\s+|[,:;.!?]+\s*)delete\s+"
    r"(?:my\s+)?"
    r"note\s+"
    r"(?P<note_id>[0-9]+)"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

CANCEL_LOCAL_NOTE_DELETE_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:"
    r"cancel\s+(?:delete\s+)?(?:my\s+)?note"
    r"|cancel\s+note\s+deletion"
    r")"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

LOCAL_TIMER_CREATE_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:set|start)\s+"
    r"(?:a\s+)?"
    r"timer\s+for\s+"
    r"(?P<duration>.+?)"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

LOCAL_REMINDER_AFTER_DURATION_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"remind\s+me\s+to\s+"
    r"(?P<text>.+)"
    r"\s+in\s+"
    r"(?P<duration>.+?)"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

LOCAL_REMINDER_TOMORROW_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"remind\s+me\s+tomorrow\s+at\s+"
    r"(?P<hour>[0-9]{1,2})"
    r"(?::(?P<minute>[0-9]{2}))?"
    r"\s*"
    r"(?P<meridiem>[A-Za-z.]+)"
    r"\s+to\s+"
    r"(?P<text>.+?)"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

LOCAL_REMINDER_LIST_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:show|list)\s+"
    r"(?:my\s+)?"
    r"(?:local\s+)?"
    r"reminders"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

LOCAL_REMINDER_CANCEL_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"cancel\s+"
    r"(?:my\s+)?"
    r"(?:local\s+)?"
    r"(?:timer|reminder)\s+"
    r"(?P<reminder_id>[0-9]+)"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

CONFIRM_LOCAL_REMINDER_CANCEL_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"confirm(?:\s+|[,:;.!?]+\s*)"
    r"cancel\s+"
    r"(?:my\s+)?"
    r"(?:local\s+)?"
    r"(?:timer|reminder)\s+"
    r"(?P<reminder_id>[0-9]+)"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

CANCEL_LOCAL_REMINDER_CANCEL_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"cancel\s+"
    r"(?:the\s+)?"
    r"(?:local\s+)?"
    r"(?:timer|reminder)\s+"
    r"cancellation"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

MASTER_VOLUME_SET_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:set|change)\s+"
    r"(?:the\s+)?"
    r"(?:master\s+)?"
    r"volume"
    r"(?:\s+to)?\s+"
    r"(?P<level>[0-9]{1,3})"
    r"\s*(?:%|percent)?"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

MASTER_VOLUME_ADJUST_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?P<action>increase|raise|decrease|lower)\s+"
    r"(?:the\s+)?"
    r"(?:master\s+)?"
    r"volume"
    r"(?:\s+by\s+(?P<amount>[0-9]{1,3})"
    r"\s*(?:%|percent)?)?"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

MASTER_VOLUME_MUTE_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:mute|silence)\s+"
    r"(?:the\s+)?"
    r"(?:master\s+)?"
    r"(?:volume|audio|sound)"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

MASTER_VOLUME_UNMUTE_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"unmute\s+"
    r"(?:the\s+)?"
    r"(?:master\s+)?"
    r"(?:volume|audio|sound)"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

MASTER_VOLUME_GET_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:what(?:\s+is|'s)|tell\s+me)\s+"
    r"(?:the\s+)?"
    r"(?:master\s+)?"
    r"volume"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

PRIMARY_BRIGHTNESS_SET_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:set|change)\s+"
    r"(?:the\s+)?"
    r"(?:screen\s+|display\s+)?"
    r"brightness"
    r"(?:\s+to)?\s+"
    r"(?P<level>[0-9]{1,3})"
    r"\s*(?:%|percent)?"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

PRIMARY_BRIGHTNESS_ADJUST_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?P<action>increase|raise|decrease|lower)\s+"
    r"(?:the\s+)?"
    r"(?:screen\s+|display\s+)?"
    r"brightness"
    r"(?:\s+by\s+(?P<amount>[0-9]{1,3})"
    r"\s*(?:%|percent)?)?"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

PRIMARY_BRIGHTNESS_GET_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:what(?:\s+is|'s)|tell\s+me)\s+"
    r"(?:the\s+)?"
    r"(?:screen\s+|display\s+)?"
    r"brightness"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

NIGHT_LIGHT_SETTINGS_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:open|show)\s+"
    r"(?:the\s+)?"
    r"night(?:\s|-)?light\s+settings"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)

READING_SETUP_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:and|or|then)\s+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:start|open)\s+"
    r"reading\s+(?:setup|mode)"
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
    LOCAL_TIMER_CREATE_PATTERN,
    LOCAL_REMINDER_AFTER_DURATION_PATTERN,
    LOCAL_REMINDER_TOMORROW_PATTERN,
    LOCAL_REMINDER_LIST_PATTERN,
    LOCAL_REMINDER_CANCEL_PATTERN,
    CONFIRM_LOCAL_REMINDER_CANCEL_PATTERN,
    CANCEL_LOCAL_REMINDER_CANCEL_PATTERN,
    APP_LAUNCH_PATTERN,
    APP_CATALOG_REFRESH_PATTERN,
    APP_CATALOG_LIST_PATTERN,
    APP_CATALOG_SEARCH_PATTERN,
    LOCAL_FILE_SEARCH_PATTERN,
    LOCAL_FILE_SEARCH_SCOPE_PATTERN,
    LOCAL_NOTE_CREATE_PATTERN,
    LOCAL_NOTE_LIST_PATTERN,
    LOCAL_NOTE_SEARCH_PATTERN,
    LOCAL_NOTE_DELETE_PATTERN,
    CONFIRM_LOCAL_NOTE_DELETE_PATTERN,
    CANCEL_LOCAL_NOTE_DELETE_PATTERN,
    MASTER_VOLUME_SET_PATTERN,
    MASTER_VOLUME_ADJUST_PATTERN,
    MASTER_VOLUME_MUTE_PATTERN,
    MASTER_VOLUME_UNMUTE_PATTERN,
    MASTER_VOLUME_GET_PATTERN,
    PRIMARY_BRIGHTNESS_SET_PATTERN,
    PRIMARY_BRIGHTNESS_ADJUST_PATTERN,
    PRIMARY_BRIGHTNESS_GET_PATTERN,
    NIGHT_LIGHT_SETTINGS_PATTERN,
    READING_SETUP_PATTERN,
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

def _parse_system_adjustment(
    raw_amount: str | None,
    *,
    default_step: int,
    label: str,
) -> int:
    """Parse one explicit safe percentage adjustment."""
    if raw_amount is None:
        return default_step

    amount = int(raw_amount)

    if amount < 1 or amount > 100:
        raise SystemControlError(
            f"{label} adjustment must be between 1 and 100."
        )

    return amount

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
    find_local_files: Callable[
        [str],
        LocalFileSearchReport,
    ] = search_local_files,
    format_local_file_search_report: Callable[
        [LocalFileSearchReport],
        str,
    ] = format_local_file_search,
    describe_local_file_search_scope: Callable[
        [],
        str,
    ] = format_local_file_search_scope,
    save_local_note: Callable[[str], LocalNote] = save_note,
    load_local_notes: Callable[[], tuple[LocalNote, ...]] = (
        load_notes
    ),
    find_local_notes: Callable[[str], tuple[LocalNote, ...]] = (
        search_notes
    ),
    delete_local_note: Callable[..., LocalNote] = delete_note,
    note_delete_confirmations: NoteDeleteConfirmationStore = (
        note_delete_confirmation_store
    ),
    save_local_reminder: Callable[..., LocalReminder] = (
        save_reminder
    ),
    load_local_reminders: Callable[
        [],
        tuple[LocalReminder, ...],
    ] = load_reminders,
    cancel_local_reminder: Callable[..., LocalReminder] = (
        cancel_reminder
    ),
    format_local_reminders: Callable[
        [tuple[LocalReminder, ...]],
        str,
    ] = format_reminders,
    parse_reminder_duration: Callable[
        [str],
        tuple[int, int, int],
    ] = parse_duration_components,
    schedule_reminder_after: Callable[..., ReminderSchedule] = (
        schedule_after_duration
    ),
    schedule_reminder_tomorrow: Callable[..., ReminderSchedule] = (
        schedule_tomorrow_at
    ),
    reminder_cancel_confirmations: ReminderCancelConfirmationStore = (
        reminder_cancel_confirmation_store
    ),
    get_volume: Callable[[], VolumeState] = get_master_volume,
    set_volume: Callable[[int], VolumeState] = set_master_volume,
    adjust_volume: Callable[[int], VolumeState] = (
        adjust_master_volume
    ),
    set_volume_mute: Callable[[bool], VolumeState] = (
        set_master_mute
    ),
    get_brightness: Callable[[], BrightnessState] = (
        get_primary_brightness
    ),
    set_brightness: Callable[[int], BrightnessState] = (
        set_primary_brightness
    ),
    adjust_brightness: Callable[[int], BrightnessState] = (
        adjust_primary_brightness
    ),
    open_night_light: Callable[[], None] = (
        open_night_light_settings
    ),
    start_reading_setup: Callable[[], ReadingModeResult] = (
        start_reading_mode
    ),
) -> SkillResult | None:
    """Handle explicit local skills before AI or legacy tools."""
    file_search_scope_match = (
        LOCAL_FILE_SEARCH_SCOPE_PATTERN.match(user_input)
    )

    if file_search_scope_match is not None:
        try:
            scope_text = describe_local_file_search_scope()
        except LocalFileDiscoveryError as error:
            console_output(
                f"Local file discovery error: {error}"
            )

            return SkillResult(
                handled=True,
                skill_name=(
                    SHOW_LOCAL_FILE_SEARCH_SCOPE_SKILL.name
                ),
                message=(
                    "I could not read the approved local "
                    "file-search scope safely, sir."
                ),
                offline=(
                    SHOW_LOCAL_FILE_SEARCH_SCOPE_SKILL.offline
                ),
                requires_confirmation=(
                    SHOW_LOCAL_FILE_SEARCH_SCOPE_SKILL
                    .requires_confirmation
                ),
            )

        console_output(scope_text)

        return SkillResult(
            handled=True,
            skill_name=SHOW_LOCAL_FILE_SEARCH_SCOPE_SKILL.name,
            message=(
                "I printed the approved local file-search scope, sir."
            ),
            offline=SHOW_LOCAL_FILE_SEARCH_SCOPE_SKILL.offline,
            requires_confirmation=(
                SHOW_LOCAL_FILE_SEARCH_SCOPE_SKILL
                .requires_confirmation
            ),
        )

    file_search_match = LOCAL_FILE_SEARCH_PATTERN.match(user_input)

    if file_search_match is not None:
        query = _clean_target(
            file_search_match.group("query")
        )

        try:
            report = find_local_files(query)
            formatted_report = format_local_file_search_report(
                report
            )
        except LocalFileDiscoveryError as error:
            console_output(
                f"Local file discovery error: {error}"
            )

            return SkillResult(
                handled=True,
                skill_name=SEARCH_LOCAL_FILES_SKILL.name,
                message=(
                    "I could not safely search the configured local "
                    "folders, sir."
                ),
                offline=SEARCH_LOCAL_FILES_SKILL.offline,
                requires_confirmation=(
                    SEARCH_LOCAL_FILES_SKILL
                    .requires_confirmation
                ),
            )

        console_output(formatted_report)
        match_count = len(report.matches)

        if match_count == 0:
            message = (
                f'I found no approved local files matching '
                f'"{report.query}", sir.'
            )
        elif report.result_limit_reached:
            message = (
                f"I printed the first {match_count} approved local "
                "file matches, sir."
            )
        elif match_count == 1:
            message = "I printed 1 approved local file match, sir."
        else:
            message = (
                f"I printed {match_count} approved local file "
                "matches, sir."
            )

        return SkillResult(
            handled=True,
            skill_name=SEARCH_LOCAL_FILES_SKILL.name,
            message=message,
            offline=SEARCH_LOCAL_FILES_SKILL.offline,
            requires_confirmation=(
                SEARCH_LOCAL_FILES_SKILL.requires_confirmation
            ),
        )
    confirm_reminder_cancel_match = (
        CONFIRM_LOCAL_REMINDER_CANCEL_PATTERN.match(user_input)
    )

    if confirm_reminder_cancel_match is not None:
        requested_id = int(
            confirm_reminder_cancel_match.group("reminder_id")
        )
        decision = reminder_cancel_confirmations.confirm(
            requested_id
        )

        if decision.status == "none":
            return SkillResult(
                handled=True,
                skill_name=CANCEL_LOCAL_REMINDER_SKILL.name,
                message=(
                    "There is no pending local reminder cancellation "
                    "to confirm, sir."
                ),
                offline=CANCEL_LOCAL_REMINDER_SKILL.offline,
                requires_confirmation=(
                    CANCEL_LOCAL_REMINDER_SKILL
                    .requires_confirmation
                ),
            )

        if decision.status == "expired":
            return SkillResult(
                handled=True,
                skill_name=CANCEL_LOCAL_REMINDER_SKILL.name,
                message=(
                    "That local reminder cancellation expired. Ask me "
                    f"to cancel reminder {decision.request.reminder_id} "
                    "again, sir."
                ),
                offline=CANCEL_LOCAL_REMINDER_SKILL.offline,
                requires_confirmation=(
                    CANCEL_LOCAL_REMINDER_SKILL
                    .requires_confirmation
                ),
            )

        if decision.status == "mismatch":
            return SkillResult(
                handled=True,
                skill_name=CANCEL_LOCAL_REMINDER_SKILL.name,
                message=(
                    "That confirmation did not match the pending local "
                    "reminder cancellation, so I cancelled it, sir."
                ),
                offline=CANCEL_LOCAL_REMINDER_SKILL.offline,
                requires_confirmation=(
                    CANCEL_LOCAL_REMINDER_SKILL
                    .requires_confirmation
                ),
            )

        pending_request = decision.request
        expected_reminder = LocalReminder(
            reminder_id=pending_request.reminder_id,
            text=pending_request.reminder_text,
            kind=pending_request.kind,
            due_at_utc=pending_request.due_at_utc,
            created_at_utc=pending_request.created_at_utc,
            status=pending_request.status,
        )

        try:
            cancelled_reminder = cancel_local_reminder(
                pending_request.reminder_id,
                expected_reminder=expected_reminder,
            )
        except LocalRemindersError as error:
            console_output(f"Local reminders error: {error}")

            return SkillResult(
                handled=True,
                skill_name=CANCEL_LOCAL_REMINDER_SKILL.name,
                message=(
                    "I could not cancel that local reminder safely, sir."
                ),
                offline=CANCEL_LOCAL_REMINDER_SKILL.offline,
                requires_confirmation=(
                    CANCEL_LOCAL_REMINDER_SKILL
                    .requires_confirmation
                ),
            )

        console_output(
            f"Cancelled local reminder "
            f"{cancelled_reminder.reminder_id}: "
            f"{cancelled_reminder.text}"
        )

        return SkillResult(
            handled=True,
            skill_name=CANCEL_LOCAL_REMINDER_SKILL.name,
            message=(
                f"Cancelled local reminder "
                f"{cancelled_reminder.reminder_id}, sir."
            ),
            offline=CANCEL_LOCAL_REMINDER_SKILL.offline,
            requires_confirmation=(
                CANCEL_LOCAL_REMINDER_SKILL.requires_confirmation
            ),
        )

    cancel_reminder_cancellation_match = (
        CANCEL_LOCAL_REMINDER_CANCEL_PATTERN.match(user_input)
    )

    if cancel_reminder_cancellation_match is not None:
        cancelled_request = reminder_cancel_confirmations.cancel()

        if cancelled_request is None:
            message = (
                "There is no pending local reminder cancellation to "
                "cancel, sir."
            )
        else:
            message = (
                "Pending cancellation of local reminder "
                f"{cancelled_request.reminder_id} cancelled, sir."
            )

        return SkillResult(
            handled=True,
            skill_name=CANCEL_LOCAL_REMINDER_SKILL.name,
            message=message,
            offline=CANCEL_LOCAL_REMINDER_SKILL.offline,
            requires_confirmation=(
                CANCEL_LOCAL_REMINDER_SKILL.requires_confirmation
            ),
        )

    cancel_reminder_match = LOCAL_REMINDER_CANCEL_PATTERN.match(
        user_input
    )

    if cancel_reminder_match is not None:
        requested_id = int(
            cancel_reminder_match.group("reminder_id")
        )

        try:
            reminders = load_local_reminders()
        except LocalRemindersError as error:
            console_output(f"Local reminders error: {error}")

            return SkillResult(
                handled=True,
                skill_name=CANCEL_LOCAL_REMINDER_SKILL.name,
                message=(
                    "I could not read local reminders safely, sir."
                ),
                offline=CANCEL_LOCAL_REMINDER_SKILL.offline,
                requires_confirmation=(
                    CANCEL_LOCAL_REMINDER_SKILL
                    .requires_confirmation
                ),
            )

        target_reminder = next(
            (
                reminder
                for reminder in reminders
                if reminder.reminder_id == requested_id
            ),
            None,
        )

        if target_reminder is None:
            return SkillResult(
                handled=True,
                skill_name=CANCEL_LOCAL_REMINDER_SKILL.name,
                message=(
                    f"I could not find local reminder "
                    f"{requested_id}, sir."
                ),
                offline=CANCEL_LOCAL_REMINDER_SKILL.offline,
                requires_confirmation=(
                    CANCEL_LOCAL_REMINDER_SKILL
                    .requires_confirmation
                ),
            )

        if target_reminder.status != REMINDER_STATUS_PENDING:
            return SkillResult(
                handled=True,
                skill_name=CANCEL_LOCAL_REMINDER_SKILL.name,
                message=(
                    f"Local reminder {requested_id} is not pending and "
                    "cannot be cancelled, sir."
                ),
                offline=CANCEL_LOCAL_REMINDER_SKILL.offline,
                requires_confirmation=(
                    CANCEL_LOCAL_REMINDER_SKILL
                    .requires_confirmation
                ),
            )

        reminder_cancel_confirmations.begin(target_reminder)

        return SkillResult(
            handled=True,
            skill_name=CANCEL_LOCAL_REMINDER_SKILL.name,
            message=(
                f'I found local reminder '
                f'{target_reminder.reminder_id}: '
                f'"{target_reminder.text}". Say '
                f'"Confirm cancel reminder '
                f'{target_reminder.reminder_id}" to cancel it, sir.'
            ),
            offline=CANCEL_LOCAL_REMINDER_SKILL.offline,
            requires_confirmation=(
                CANCEL_LOCAL_REMINDER_SKILL.requires_confirmation
            ),
        )

    list_reminders_match = LOCAL_REMINDER_LIST_PATTERN.match(
        user_input
    )

    if list_reminders_match is not None:
        try:
            reminders = load_local_reminders()
        except LocalRemindersError as error:
            console_output(f"Local reminders error: {error}")

            return SkillResult(
                handled=True,
                skill_name=LIST_LOCAL_REMINDERS_SKILL.name,
                message=(
                    "I could not read local reminders safely, sir."
                ),
                offline=LIST_LOCAL_REMINDERS_SKILL.offline,
                requires_confirmation=(
                    LIST_LOCAL_REMINDERS_SKILL
                    .requires_confirmation
                ),
            )

        console_output(format_local_reminders(reminders))

        if not reminders:
            message = "You have no saved local reminders, sir."
        else:
            message = (
                f"I printed {len(reminders)} local reminders, sir."
            )

        return SkillResult(
            handled=True,
            skill_name=LIST_LOCAL_REMINDERS_SKILL.name,
            message=message,
            offline=LIST_LOCAL_REMINDERS_SKILL.offline,
            requires_confirmation=(
                LIST_LOCAL_REMINDERS_SKILL.requires_confirmation
            ),
        )

    timer_create_match = LOCAL_TIMER_CREATE_PATTERN.match(user_input)

    if timer_create_match is not None:
        duration_text = _clean_target(
            timer_create_match.group("duration")
        )

        try:
            hours, minutes, seconds = parse_reminder_duration(
                duration_text
            )
            schedule = schedule_reminder_after(
                hours=hours,
                minutes=minutes,
                seconds=seconds,
            )
        except ReminderScheduleError as error:
            console_output(
                f"Local reminder schedule error: {error}"
            )

            return SkillResult(
                handled=True,
                skill_name=CREATE_LOCAL_TIMER_SKILL.name,
                message=(
                    "I need a numeric timer duration, such as "
                    "5 minutes, sir."
                ),
                offline=CREATE_LOCAL_TIMER_SKILL.offline,
                requires_confirmation=(
                    CREATE_LOCAL_TIMER_SKILL.requires_confirmation
                ),
            )

        try:
            reminder = save_local_reminder(
                "Timer",
                kind=REMINDER_KIND_TIMER,
                due_at=schedule.due_at_utc,
            )
        except LocalRemindersError as error:
            console_output(f"Local reminders error: {error}")

            return SkillResult(
                handled=True,
                skill_name=CREATE_LOCAL_TIMER_SKILL.name,
                message=(
                    "I could not save that local timer safely, sir."
                ),
                offline=CREATE_LOCAL_TIMER_SKILL.offline,
                requires_confirmation=(
                    CREATE_LOCAL_TIMER_SKILL.requires_confirmation
                ),
            )

        console_output(
            f"Saved local timer {reminder.reminder_id}: "
            f"{reminder.text} | due {reminder.due_at_utc}"
        )

        duration_description = schedule.description.removeprefix(
            "in "
        )

        return SkillResult(
            handled=True,
            skill_name=CREATE_LOCAL_TIMER_SKILL.name,
            message=(
                f"Set local timer {reminder.reminder_id} for "
                f"{duration_description}, sir."
            ),
            offline=CREATE_LOCAL_TIMER_SKILL.offline,
            requires_confirmation=(
                CREATE_LOCAL_TIMER_SKILL.requires_confirmation
            ),
        )

    tomorrow_reminder_match = (
        LOCAL_REMINDER_TOMORROW_PATTERN.match(user_input)
    )

    if tomorrow_reminder_match is not None:
        reminder_text = _clean_target(
            tomorrow_reminder_match.group("text")
        )
        hour = int(tomorrow_reminder_match.group("hour"))
        minute = int(
            tomorrow_reminder_match.group("minute") or "0"
        )
        meridiem = (
            tomorrow_reminder_match.group("meridiem")
            .replace(".", "")
        )

        try:
            schedule = schedule_reminder_tomorrow(
                hour=hour,
                minute=minute,
                meridiem=meridiem,
            )
        except ReminderScheduleError as error:
            console_output(
                f"Local reminder schedule error: {error}"
            )

            return SkillResult(
                handled=True,
                skill_name=CREATE_LOCAL_REMINDER_SKILL.name,
                message=(
                    "I need a valid tomorrow time, such as 8 PM, sir."
                ),
                offline=CREATE_LOCAL_REMINDER_SKILL.offline,
                requires_confirmation=(
                    CREATE_LOCAL_REMINDER_SKILL
                    .requires_confirmation
                ),
            )

        try:
            reminder = save_local_reminder(
                reminder_text,
                kind=REMINDER_KIND_REMINDER,
                due_at=schedule.due_at_utc,
            )
        except LocalRemindersError as error:
            console_output(f"Local reminders error: {error}")

            return SkillResult(
                handled=True,
                skill_name=CREATE_LOCAL_REMINDER_SKILL.name,
                message=(
                    "I could not save that local reminder safely, sir."
                ),
                offline=CREATE_LOCAL_REMINDER_SKILL.offline,
                requires_confirmation=(
                    CREATE_LOCAL_REMINDER_SKILL
                    .requires_confirmation
                ),
            )

        console_output(
            f"Saved local reminder {reminder.reminder_id}: "
            f"{reminder.text} | due {reminder.due_at_utc}"
        )

        return SkillResult(
            handled=True,
            skill_name=CREATE_LOCAL_REMINDER_SKILL.name,
            message=(
                f"Saved local reminder {reminder.reminder_id}. "
                f"I will remind you to {reminder.text} "
                f"{schedule.description}, sir."
            ),
            offline=CREATE_LOCAL_REMINDER_SKILL.offline,
            requires_confirmation=(
                CREATE_LOCAL_REMINDER_SKILL.requires_confirmation
            ),
        )

    duration_reminder_match = (
        LOCAL_REMINDER_AFTER_DURATION_PATTERN.match(user_input)
    )

    if duration_reminder_match is not None:
        reminder_text = _clean_target(
            duration_reminder_match.group("text")
        )
        duration_text = _clean_target(
            duration_reminder_match.group("duration")
        )

        try:
            hours, minutes, seconds = parse_reminder_duration(
                duration_text
            )
            schedule = schedule_reminder_after(
                hours=hours,
                minutes=minutes,
                seconds=seconds,
            )
        except ReminderScheduleError as error:
            console_output(
                f"Local reminder schedule error: {error}"
            )

            return SkillResult(
                handled=True,
                skill_name=CREATE_LOCAL_REMINDER_SKILL.name,
                message=(
                    "I need a numeric reminder duration, such as "
                    "30 minutes, sir."
                ),
                offline=CREATE_LOCAL_REMINDER_SKILL.offline,
                requires_confirmation=(
                    CREATE_LOCAL_REMINDER_SKILL
                    .requires_confirmation
                ),
            )

        try:
            reminder = save_local_reminder(
                reminder_text,
                kind=REMINDER_KIND_REMINDER,
                due_at=schedule.due_at_utc,
            )
        except LocalRemindersError as error:
            console_output(f"Local reminders error: {error}")

            return SkillResult(
                handled=True,
                skill_name=CREATE_LOCAL_REMINDER_SKILL.name,
                message=(
                    "I could not save that local reminder safely, sir."
                ),
                offline=CREATE_LOCAL_REMINDER_SKILL.offline,
                requires_confirmation=(
                    CREATE_LOCAL_REMINDER_SKILL
                    .requires_confirmation
                ),
            )

        console_output(
            f"Saved local reminder {reminder.reminder_id}: "
            f"{reminder.text} | due {reminder.due_at_utc}"
        )

        return SkillResult(
            handled=True,
            skill_name=CREATE_LOCAL_REMINDER_SKILL.name,
            message=(
                f"Saved local reminder {reminder.reminder_id}. "
                f"I will remind you to {reminder.text} "
                f"{schedule.description}, sir."
            ),
            offline=CREATE_LOCAL_REMINDER_SKILL.offline,
            requires_confirmation=(
                CREATE_LOCAL_REMINDER_SKILL.requires_confirmation
            ),
        )
    volume_set_match = MASTER_VOLUME_SET_PATTERN.match(user_input)

    if volume_set_match is not None:
        level = int(volume_set_match.group("level"))

        try:
            state = set_volume(level)
        except SystemControlError as error:
            console_output(f"System controls error: {error}")

            return SkillResult(
                handled=True,
                skill_name=MASTER_VOLUME_SKILL.name,
                message="I could not set master volume safely, sir.",
                offline=MASTER_VOLUME_SKILL.offline,
                requires_confirmation=(
                    MASTER_VOLUME_SKILL.requires_confirmation
                ),
            )

        if state.muted:
            message = (
                f"Master volume set to {state.level}%, but audio "
                "remains muted, sir."
            )
        else:
            message = f"Master volume set to {state.level}%, sir."

        return SkillResult(
            handled=True,
            skill_name=MASTER_VOLUME_SKILL.name,
            message=message,
            offline=MASTER_VOLUME_SKILL.offline,
            requires_confirmation=(
                MASTER_VOLUME_SKILL.requires_confirmation
            ),
        )

    volume_adjust_match = MASTER_VOLUME_ADJUST_PATTERN.match(
        user_input
    )

    if volume_adjust_match is not None:
        action = volume_adjust_match.group("action").casefold()

        try:
            amount = _parse_system_adjustment(
                volume_adjust_match.group("amount"),
                default_step=DEFAULT_VOLUME_STEP,
                label="Volume",
            )
            change = amount if action in {"increase", "raise"} else -amount
            state = adjust_volume(change)
        except SystemControlError as error:
            console_output(f"System controls error: {error}")

            return SkillResult(
                handled=True,
                skill_name=MASTER_VOLUME_SKILL.name,
                message="I could not adjust master volume safely, sir.",
                offline=MASTER_VOLUME_SKILL.offline,
                requires_confirmation=(
                    MASTER_VOLUME_SKILL.requires_confirmation
                ),
            )

        action_word = (
            "increased"
            if change > 0
            else "decreased"
        )

        if state.muted:
            message = (
                f"Master volume {action_word} to {state.level}%, "
                "but audio remains muted, sir."
            )
        else:
            message = (
                f"Master volume {action_word} to {state.level}%, sir."
            )

        return SkillResult(
            handled=True,
            skill_name=MASTER_VOLUME_SKILL.name,
            message=message,
            offline=MASTER_VOLUME_SKILL.offline,
            requires_confirmation=(
                MASTER_VOLUME_SKILL.requires_confirmation
            ),
        )

    volume_mute_match = MASTER_VOLUME_MUTE_PATTERN.match(user_input)

    if volume_mute_match is not None:
        try:
            state = set_volume_mute(True)
        except SystemControlError as error:
            console_output(f"System controls error: {error}")

            return SkillResult(
                handled=True,
                skill_name=MASTER_VOLUME_SKILL.name,
                message="I could not mute master volume safely, sir.",
                offline=MASTER_VOLUME_SKILL.offline,
                requires_confirmation=(
                    MASTER_VOLUME_SKILL.requires_confirmation
                ),
            )

        return SkillResult(
            handled=True,
            skill_name=MASTER_VOLUME_SKILL.name,
            message=(
                f"Master volume muted at {state.level}%, sir."
            ),
            offline=MASTER_VOLUME_SKILL.offline,
            requires_confirmation=(
                MASTER_VOLUME_SKILL.requires_confirmation
            ),
        )

    volume_unmute_match = MASTER_VOLUME_UNMUTE_PATTERN.match(user_input)

    if volume_unmute_match is not None:
        try:
            state = set_volume_mute(False)
        except SystemControlError as error:
            console_output(f"System controls error: {error}")

            return SkillResult(
                handled=True,
                skill_name=MASTER_VOLUME_SKILL.name,
                message="I could not unmute master volume safely, sir.",
                offline=MASTER_VOLUME_SKILL.offline,
                requires_confirmation=(
                    MASTER_VOLUME_SKILL.requires_confirmation
                ),
            )

        return SkillResult(
            handled=True,
            skill_name=MASTER_VOLUME_SKILL.name,
            message=(
                f"Master volume unmuted at {state.level}%, sir."
            ),
            offline=MASTER_VOLUME_SKILL.offline,
            requires_confirmation=(
                MASTER_VOLUME_SKILL.requires_confirmation
            ),
        )

    volume_get_match = MASTER_VOLUME_GET_PATTERN.match(user_input)

    if volume_get_match is not None:
        try:
            state = get_volume()
        except SystemControlError as error:
            console_output(f"System controls error: {error}")

            return SkillResult(
                handled=True,
                skill_name=MASTER_VOLUME_SKILL.name,
                message="I could not read master volume safely, sir.",
                offline=MASTER_VOLUME_SKILL.offline,
                requires_confirmation=(
                    MASTER_VOLUME_SKILL.requires_confirmation
                ),
            )

        mute_word = "muted" if state.muted else "unmuted"

        return SkillResult(
            handled=True,
            skill_name=MASTER_VOLUME_SKILL.name,
            message=(
                f"Master volume is {state.level}%, and audio is "
                f"{mute_word}, sir."
            ),
            offline=MASTER_VOLUME_SKILL.offline,
            requires_confirmation=(
                MASTER_VOLUME_SKILL.requires_confirmation
            ),
        )

    brightness_set_match = PRIMARY_BRIGHTNESS_SET_PATTERN.match(
        user_input
    )

    if brightness_set_match is not None:
        level = int(brightness_set_match.group("level"))

        try:
            state = set_brightness(level)
        except SystemControlError as error:
            console_output(f"System controls error: {error}")

            return SkillResult(
                handled=True,
                skill_name=PRIMARY_BRIGHTNESS_SKILL.name,
                message=(
                    "I could not set built-in display brightness "
                    "safely, sir."
                ),
                offline=PRIMARY_BRIGHTNESS_SKILL.offline,
                requires_confirmation=(
                    PRIMARY_BRIGHTNESS_SKILL.requires_confirmation
                ),
            )

        return SkillResult(
            handled=True,
            skill_name=PRIMARY_BRIGHTNESS_SKILL.name,
            message=(
                f"Built-in display brightness set to {state.level}%, "
                "sir."
            ),
            offline=PRIMARY_BRIGHTNESS_SKILL.offline,
            requires_confirmation=(
                PRIMARY_BRIGHTNESS_SKILL.requires_confirmation
            ),
        )

    brightness_adjust_match = PRIMARY_BRIGHTNESS_ADJUST_PATTERN.match(
        user_input
    )

    if brightness_adjust_match is not None:
        action = brightness_adjust_match.group("action").casefold()

        try:
            amount = _parse_system_adjustment(
                brightness_adjust_match.group("amount"),
                default_step=DEFAULT_BRIGHTNESS_STEP,
                label="Brightness",
            )
            change = amount if action in {"increase", "raise"} else -amount
            state = adjust_brightness(change)
        except SystemControlError as error:
            console_output(f"System controls error: {error}")

            return SkillResult(
                handled=True,
                skill_name=PRIMARY_BRIGHTNESS_SKILL.name,
                message=(
                    "I could not adjust built-in display brightness "
                    "safely, sir."
                ),
                offline=PRIMARY_BRIGHTNESS_SKILL.offline,
                requires_confirmation=(
                    PRIMARY_BRIGHTNESS_SKILL.requires_confirmation
                ),
            )

        action_word = (
            "increased"
            if change > 0
            else "decreased"
        )

        return SkillResult(
            handled=True,
            skill_name=PRIMARY_BRIGHTNESS_SKILL.name,
            message=(
                f"Built-in display brightness {action_word} to "
                f"{state.level}%, sir."
            ),
            offline=PRIMARY_BRIGHTNESS_SKILL.offline,
            requires_confirmation=(
                PRIMARY_BRIGHTNESS_SKILL.requires_confirmation
            ),
        )

    brightness_get_match = PRIMARY_BRIGHTNESS_GET_PATTERN.match(
        user_input
    )

    if brightness_get_match is not None:
        try:
            state = get_brightness()
        except SystemControlError as error:
            console_output(f"System controls error: {error}")

            return SkillResult(
                handled=True,
                skill_name=PRIMARY_BRIGHTNESS_SKILL.name,
                message=(
                    "I could not read built-in display brightness "
                    "safely, sir."
                ),
                offline=PRIMARY_BRIGHTNESS_SKILL.offline,
                requires_confirmation=(
                    PRIMARY_BRIGHTNESS_SKILL.requires_confirmation
                ),
            )

        return SkillResult(
            handled=True,
            skill_name=PRIMARY_BRIGHTNESS_SKILL.name,
            message=(
                f"Built-in display brightness is {state.level}%, sir."
            ),
            offline=PRIMARY_BRIGHTNESS_SKILL.offline,
            requires_confirmation=(
                PRIMARY_BRIGHTNESS_SKILL.requires_confirmation
            ),
        )

    night_light_match = NIGHT_LIGHT_SETTINGS_PATTERN.match(user_input)

    if night_light_match is not None:
        try:
            open_night_light()
        except SystemControlError as error:
            console_output(f"System controls error: {error}")

            return SkillResult(
                handled=True,
                skill_name=OPEN_NIGHT_LIGHT_SETTINGS_SKILL.name,
                message=(
                    "I could not open Night Light Settings safely, sir."
                ),
                offline=OPEN_NIGHT_LIGHT_SETTINGS_SKILL.offline,
                requires_confirmation=(
                    OPEN_NIGHT_LIGHT_SETTINGS_SKILL
                    .requires_confirmation
                ),
            )

        return SkillResult(
            handled=True,
            skill_name=OPEN_NIGHT_LIGHT_SETTINGS_SKILL.name,
            message="I opened Night Light Settings, sir.",
            offline=OPEN_NIGHT_LIGHT_SETTINGS_SKILL.offline,
            requires_confirmation=(
                OPEN_NIGHT_LIGHT_SETTINGS_SKILL
                .requires_confirmation
            ),
        )

    reading_setup_match = READING_SETUP_PATTERN.match(user_input)

    if reading_setup_match is not None:
        try:
            result = start_reading_setup()
        except SystemControlError as error:
            console_output(f"System controls error: {error}")

            return SkillResult(
                handled=True,
                skill_name=START_READING_SETUP_SKILL.name,
                message="I could not start reading setup safely, sir.",
                offline=START_READING_SETUP_SKILL.offline,
                requires_confirmation=(
                    START_READING_SETUP_SKILL.requires_confirmation
                ),
            )

        return SkillResult(
            handled=True,
            skill_name=START_READING_SETUP_SKILL.name,
            message=(
                "Reading setup is ready: built-in brightness is "
                f"{result.brightness.level}%. I opened Night Light "
                "Settings so you can enable Night Light there, sir."
            ),
            offline=START_READING_SETUP_SKILL.offline,
            requires_confirmation=(
                START_READING_SETUP_SKILL.requires_confirmation
            ),
        )
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

    confirm_note_delete_match = (
        CONFIRM_LOCAL_NOTE_DELETE_PATTERN.match(user_input)
    )

    if confirm_note_delete_match is not None:
        requested_id = int(
            confirm_note_delete_match.group("note_id")
        )
        decision = note_delete_confirmations.confirm(requested_id)

        if decision.status == "none":
            return SkillResult(
                handled=True,
                skill_name=DELETE_LOCAL_NOTE_SKILL.name,
                message=(
                    "There is no pending local note deletion to "
                    "confirm, sir."
                ),
                offline=DELETE_LOCAL_NOTE_SKILL.offline,
                requires_confirmation=(
                    DELETE_LOCAL_NOTE_SKILL.requires_confirmation
                ),
            )

        if decision.status == "expired":
            return SkillResult(
                handled=True,
                skill_name=DELETE_LOCAL_NOTE_SKILL.name,
                message=(
                    "That local note deletion confirmation expired. "
                    f"Ask me to delete note {decision.request.note_id} "
                    "again, sir."
                ),
                offline=DELETE_LOCAL_NOTE_SKILL.offline,
                requires_confirmation=(
                    DELETE_LOCAL_NOTE_SKILL.requires_confirmation
                ),
            )

        if decision.status == "mismatch":
            return SkillResult(
                handled=True,
                skill_name=DELETE_LOCAL_NOTE_SKILL.name,
                message=(
                    "That confirmation did not match the pending local "
                    "note deletion, so I cancelled it, sir."
                ),
                offline=DELETE_LOCAL_NOTE_SKILL.offline,
                requires_confirmation=(
                    DELETE_LOCAL_NOTE_SKILL.requires_confirmation
                ),
            )

        pending_request = decision.request
        expected_note = LocalNote(
            note_id=pending_request.note_id,
            text=pending_request.note_text,
            created_at_utc=pending_request.created_at_utc,
        )

        try:
            deleted_note = delete_local_note(
                pending_request.note_id,
                expected_note=expected_note,
            )
        except LocalNotesError as error:
            console_output(f"Local notes error: {error}")

            return SkillResult(
                handled=True,
                skill_name=DELETE_LOCAL_NOTE_SKILL.name,
                message=(
                    "I could not delete that local note safely, sir."
                ),
                offline=DELETE_LOCAL_NOTE_SKILL.offline,
                requires_confirmation=(
                    DELETE_LOCAL_NOTE_SKILL.requires_confirmation
                ),
            )

        console_output(
            f"Deleted local note {deleted_note.note_id}: "
            f"{deleted_note.text}"
        )

        return SkillResult(
            handled=True,
            skill_name=DELETE_LOCAL_NOTE_SKILL.name,
            message=(
                f"Deleted local note {deleted_note.note_id}, sir."
            ),
            offline=DELETE_LOCAL_NOTE_SKILL.offline,
            requires_confirmation=(
                DELETE_LOCAL_NOTE_SKILL.requires_confirmation
            ),
        )

    cancel_note_delete_match = (
        CANCEL_LOCAL_NOTE_DELETE_PATTERN.match(user_input)
    )

    if cancel_note_delete_match is not None:
        cancelled_request = note_delete_confirmations.cancel()

        if cancelled_request is None:
            message = (
                "There is no pending local note deletion to cancel, "
                "sir."
            )
        else:
            message = (
                f"Pending deletion of local note "
                f"{cancelled_request.note_id} cancelled, sir."
            )

        return SkillResult(
            handled=True,
            skill_name=DELETE_LOCAL_NOTE_SKILL.name,
            message=message,
            offline=DELETE_LOCAL_NOTE_SKILL.offline,
            requires_confirmation=(
                DELETE_LOCAL_NOTE_SKILL.requires_confirmation
            ),
        )

    delete_note_match = LOCAL_NOTE_DELETE_PATTERN.match(user_input)

    if delete_note_match is not None:
        requested_id = int(delete_note_match.group("note_id"))

        try:
            notes = load_local_notes()
        except LocalNotesError as error:
            console_output(f"Local notes error: {error}")

            return SkillResult(
                handled=True,
                skill_name=DELETE_LOCAL_NOTE_SKILL.name,
                message=(
                    "I could not read local notes safely, sir."
                ),
                offline=DELETE_LOCAL_NOTE_SKILL.offline,
                requires_confirmation=(
                    DELETE_LOCAL_NOTE_SKILL.requires_confirmation
                ),
            )

        target_note = next(
            (
                note
                for note in notes
                if note.note_id == requested_id
            ),
            None,
        )

        if target_note is None:
            return SkillResult(
                handled=True,
                skill_name=DELETE_LOCAL_NOTE_SKILL.name,
                message=(
                    f"I could not find local note {requested_id}, sir."
                ),
                offline=DELETE_LOCAL_NOTE_SKILL.offline,
                requires_confirmation=(
                    DELETE_LOCAL_NOTE_SKILL.requires_confirmation
                ),
            )

        note_delete_confirmations.begin(target_note)

        return SkillResult(
            handled=True,
            skill_name=DELETE_LOCAL_NOTE_SKILL.name,
            message=(
                f'I found local note {target_note.note_id}: '
                f'"{target_note.text}". Say '
                f'"Confirm delete note {target_note.note_id}" to '
                "permanently delete it, sir."
            ),
            offline=DELETE_LOCAL_NOTE_SKILL.offline,
            requires_confirmation=(
                DELETE_LOCAL_NOTE_SKILL.requires_confirmation
            ),
        )

    create_note_match = LOCAL_NOTE_CREATE_PATTERN.match(user_input)

    if create_note_match is not None:
        note_text = _clean_target(
            create_note_match.group("text")
        )

        try:
            note = save_local_note(note_text)
        except LocalNotesError as error:
            console_output(f"Local notes error: {error}")

            return SkillResult(
                handled=True,
                skill_name=CREATE_LOCAL_NOTE_SKILL.name,
                message=(
                    "I could not save that local note safely, sir."
                ),
                offline=CREATE_LOCAL_NOTE_SKILL.offline,
                requires_confirmation=(
                    CREATE_LOCAL_NOTE_SKILL.requires_confirmation
                ),
            )

        console_output(
            f"Saved local note {note.note_id}: {note.text}"
        )

        return SkillResult(
            handled=True,
            skill_name=CREATE_LOCAL_NOTE_SKILL.name,
            message=f"Saved local note {note.note_id}, sir.",
            offline=CREATE_LOCAL_NOTE_SKILL.offline,
            requires_confirmation=(
                CREATE_LOCAL_NOTE_SKILL.requires_confirmation
            ),
        )

    list_notes_match = LOCAL_NOTE_LIST_PATTERN.match(user_input)

    if list_notes_match is not None:
        try:
            notes = load_local_notes()
        except LocalNotesError as error:
            console_output(f"Local notes error: {error}")

            return SkillResult(
                handled=True,
                skill_name=LIST_LOCAL_NOTES_SKILL.name,
                message=(
                    "I could not read local notes safely, sir."
                ),
                offline=LIST_LOCAL_NOTES_SKILL.offline,
                requires_confirmation=(
                    LIST_LOCAL_NOTES_SKILL.requires_confirmation
                ),
            )

        console_output(format_notes(notes))

        if not notes:
            message = "You have no saved local notes, sir."
        else:
            message = (
                f"I printed {len(notes)} local notes, sir."
            )

        return SkillResult(
            handled=True,
            skill_name=LIST_LOCAL_NOTES_SKILL.name,
            message=message,
            offline=LIST_LOCAL_NOTES_SKILL.offline,
            requires_confirmation=(
                LIST_LOCAL_NOTES_SKILL.requires_confirmation
            ),
        )

    search_notes_match = LOCAL_NOTE_SEARCH_PATTERN.match(user_input)

    if search_notes_match is not None:
        query = _clean_target(
            search_notes_match.group("query")
        )

        try:
            notes = find_local_notes(query)
        except LocalNotesError as error:
            console_output(f"Local notes error: {error}")

            return SkillResult(
                handled=True,
                skill_name=SEARCH_LOCAL_NOTES_SKILL.name,
                message=(
                    "I could not search local notes safely, sir."
                ),
                offline=SEARCH_LOCAL_NOTES_SKILL.offline,
                requires_confirmation=(
                    SEARCH_LOCAL_NOTES_SKILL.requires_confirmation
                ),
            )

        console_output(format_note_search(query, notes))

        if not notes:
            message = (
                f"I found no local notes matching {query}, sir."
            )
        else:
            message = (
                f"I found {len(notes)} local notes matching "
                f"{query}. I printed the details, sir."
            )

        return SkillResult(
            handled=True,
            skill_name=SEARCH_LOCAL_NOTES_SKILL.name,
            message=message,
            offline=SEARCH_LOCAL_NOTES_SKILL.offline,
            requires_confirmation=(
                SEARCH_LOCAL_NOTES_SKILL.requires_confirmation
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