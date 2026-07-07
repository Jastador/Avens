from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from config import LOCAL_DATA_DIR


REMINDERS_FILE = LOCAL_DATA_DIR / "reminders.json"
REMINDERS_SCHEMA_VERSION = 1
MAX_REMINDER_TEXT_LENGTH = 1_000

REMINDER_KIND_TIMER = "timer"
REMINDER_KIND_REMINDER = "reminder"

REMINDER_STATUS_PENDING = "pending"
REMINDER_STATUS_DELIVERED = "delivered"
REMINDER_STATUS_CANCELLED = "cancelled"

VALID_REMINDER_KINDS = frozenset(
    {
        REMINDER_KIND_TIMER,
        REMINDER_KIND_REMINDER,
    }
)

VALID_REMINDER_STATUSES = frozenset(
    {
        REMINDER_STATUS_PENDING,
        REMINDER_STATUS_DELIVERED,
        REMINDER_STATUS_CANCELLED,
    }
)

_reminder_store_lock = threading.RLock()


class LocalRemindersError(RuntimeError):
    """Raised when local reminder storage cannot be handled safely."""


@dataclass(frozen=True)
class LocalReminder:
    """One persistent offline timer or reminder."""

    reminder_id: int
    text: str
    kind: str
    due_at_utc: str
    created_at_utc: str
    status: str
    delivered_at_utc: str | None = None
    cancelled_at_utc: str | None = None


@dataclass(frozen=True)
class _LocalReminderStore:
    """Internal persisted reminders and the next monotonic identifier."""

    reminders: tuple[LocalReminder, ...]
    next_id: int


def _utc_now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(timezone.utc)


def _validate_reminder_id(value: int) -> int:
    """Accept only one positive integer reminder identifier."""
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 1
    ):
        raise LocalRemindersError(
            "A local reminder id must be a positive integer."
        )

    return value


def _normalise_reminder_text(value: str) -> str:
    """Keep reminder text readable without changing its meaning."""
    if not isinstance(value, str):
        raise LocalRemindersError("A reminder must contain text.")

    text = " ".join(value.split())

    if not text:
        raise LocalRemindersError("A reminder cannot be empty.")

    if len(text) > MAX_REMINDER_TEXT_LENGTH:
        raise LocalRemindersError(
            "A reminder cannot exceed "
            f"{MAX_REMINDER_TEXT_LENGTH} characters."
        )

    return text


def _validate_reminder_kind(value: str) -> str:
    """Accept only one declared deterministic reminder kind."""
    if not isinstance(value, str):
        raise LocalRemindersError("A reminder kind is invalid.")

    kind = value.casefold().strip()

    if kind not in VALID_REMINDER_KINDS:
        raise LocalRemindersError("A reminder kind is invalid.")

    return kind


def _validate_reminder_status(value: str) -> str:
    """Accept only one declared persistent reminder status."""
    if not isinstance(value, str):
        raise LocalRemindersError("A reminder status is invalid.")

    status = value.casefold().strip()

    if status not in VALID_REMINDER_STATUSES:
        raise LocalRemindersError("A reminder status is invalid.")

    return status


def _format_utc_timestamp(value: datetime) -> str:
    """Store one timezone-aware datetime in stable UTC form."""
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise LocalRemindersError(
            "A reminder timestamp must include a timezone."
        )

    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_utc_timestamp(
    value: object,
    *,
    label: str,
) -> datetime:
    """Read one stored timezone-aware timestamp without repairing it."""
    if not isinstance(value, str):
        raise LocalRemindersError(
            f"{label} has an invalid timestamp."
        )

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise LocalRemindersError(
            f"{label} has an invalid timestamp."
        ) from error

    if parsed.tzinfo is None:
        raise LocalRemindersError(
            f"{label} has an invalid timestamp."
        )

    return parsed.astimezone(timezone.utc).replace(
        microsecond=0
    )


def _parse_optional_utc_timestamp(
    value: object,
    *,
    label: str,
) -> str | None:
    """Read one optional stored UTC timestamp."""
    if value is None:
        return None

    return _format_utc_timestamp(
        _parse_utc_timestamp(
            value,
            label=label,
        )
    )


def _parse_reminder(
    raw_reminder: object,
    *,
    index: int,
) -> LocalReminder:
    """Validate one stored reminder without silently fixing corruption."""
    if not isinstance(raw_reminder, dict):
        raise LocalRemindersError(
            f"Saved reminder {index} is not a valid object."
        )

    try:
        reminder_id = _validate_reminder_id(
            raw_reminder.get("id")
        )
    except LocalRemindersError as error:
        raise LocalRemindersError(
            f"Saved reminder {index} has an invalid id."
        ) from error

    text = _normalise_reminder_text(
        raw_reminder.get("text")
    )
    kind = _validate_reminder_kind(
        raw_reminder.get("kind")
    )
    status = _validate_reminder_status(
        raw_reminder.get("status")
    )

    due_at_utc = _format_utc_timestamp(
        _parse_utc_timestamp(
            raw_reminder.get("due_at_utc"),
            label=f"Saved reminder {index}",
        )
    )
    created_at_utc = _format_utc_timestamp(
        _parse_utc_timestamp(
            raw_reminder.get("created_at_utc"),
            label=f"Saved reminder {index}",
        )
    )
    delivered_at_utc = _parse_optional_utc_timestamp(
        raw_reminder.get("delivered_at_utc"),
        label=f"Saved reminder {index}",
    )
    cancelled_at_utc = _parse_optional_utc_timestamp(
        raw_reminder.get("cancelled_at_utc"),
        label=f"Saved reminder {index}",
    )

    if status == REMINDER_STATUS_PENDING:
        if (
            delivered_at_utc is not None
            or cancelled_at_utc is not None
        ):
            raise LocalRemindersError(
                f"Saved reminder {index} has invalid pending state."
            )

    if status == REMINDER_STATUS_DELIVERED:
        if (
            delivered_at_utc is None
            or cancelled_at_utc is not None
        ):
            raise LocalRemindersError(
                f"Saved reminder {index} has invalid delivered state."
            )

    if status == REMINDER_STATUS_CANCELLED:
        if (
            cancelled_at_utc is None
            or delivered_at_utc is not None
        ):
            raise LocalRemindersError(
                f"Saved reminder {index} has invalid cancelled state."
            )

    return LocalReminder(
        reminder_id=reminder_id,
        text=text,
        kind=kind,
        due_at_utc=due_at_utc,
        created_at_utc=created_at_utc,
        status=status,
        delivered_at_utc=delivered_at_utc,
        cancelled_at_utc=cancelled_at_utc,
    )


def _parse_next_id(
    raw_next_id: object,
    reminders: tuple[LocalReminder, ...],
) -> int:
    """Keep identifiers monotonic even after cancellation."""
    minimum_next_id = max(
        (
            reminder.reminder_id
            for reminder in reminders
        ),
        default=0,
    ) + 1

    if raw_next_id is None:
        return minimum_next_id

    try:
        next_id = _validate_reminder_id(raw_next_id)
    except LocalRemindersError as error:
        raise LocalRemindersError(
            "Local reminders have an invalid next_id value."
        ) from error

    if next_id < minimum_next_id:
        raise LocalRemindersError(
            "Local reminders have an invalid next_id value."
        )

    return next_id


def _load_reminder_store(
    *,
    reminder_file: Path,
) -> _LocalReminderStore:
    """Load one validated reminder store without modifying it."""
    path = reminder_file.expanduser()

    if not path.exists():
        return _LocalReminderStore(
            reminders=(),
            next_id=1,
        )

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )
    except OSError as error:
        raise LocalRemindersError(
            f"Could not read local reminders: {error}"
        ) from error
    except json.JSONDecodeError as error:
        raise LocalRemindersError(
            "Local reminders are not valid JSON. "
            "They were left unchanged."
        ) from error

    if not isinstance(payload, dict):
        raise LocalRemindersError(
            "Local reminders have an invalid storage format."
        )

    if payload.get("version") != REMINDERS_SCHEMA_VERSION:
        raise LocalRemindersError(
            "Local reminders use an unsupported storage version."
        )

    raw_reminders = payload.get("reminders")

    if not isinstance(raw_reminders, list):
        raise LocalRemindersError(
            "Local reminders have an invalid reminders list."
        )

    reminders = tuple(
        _parse_reminder(
            raw_reminder,
            index=index,
        )
        for index, raw_reminder in enumerate(
            raw_reminders,
            start=1,
        )
    )

    reminder_ids = [
        reminder.reminder_id
        for reminder in reminders
    ]

    if len(reminder_ids) != len(set(reminder_ids)):
        raise LocalRemindersError(
            "Local reminders contain duplicate ids."
        )

    ordered_reminders = tuple(
        sorted(
            reminders,
            key=lambda reminder: reminder.reminder_id,
        )
    )

    return _LocalReminderStore(
        reminders=ordered_reminders,
        next_id=_parse_next_id(
            payload.get("next_id"),
            ordered_reminders,
        ),
    )


def load_reminders(
    *,
    reminder_file: Path = REMINDERS_FILE,
) -> tuple[LocalReminder, ...]:
    """Load local reminders without changing missing or damaged data."""
    with _reminder_store_lock:
        return _load_reminder_store(
            reminder_file=reminder_file
        ).reminders


def _write_reminder_store(
    store: _LocalReminderStore,
    *,
    reminder_file: Path,
) -> None:
    """Atomically replace storage only after one complete safe write."""
    destination = reminder_file.expanduser()
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    next_id = _parse_next_id(
        store.next_id,
        store.reminders,
    )

    payload = {
        "version": REMINDERS_SCHEMA_VERSION,
        "next_id": next_id,
        "reminders": [
            {
                "id": reminder.reminder_id,
                "text": reminder.text,
                "kind": reminder.kind,
                "due_at_utc": reminder.due_at_utc,
                "created_at_utc": reminder.created_at_utc,
                "status": reminder.status,
                "delivered_at_utc": (
                    reminder.delivered_at_utc
                ),
                "cancelled_at_utc": (
                    reminder.cancelled_at_utc
                ),
            }
            for reminder in store.reminders
        ],
    }

    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=destination.parent,
            suffix=".tmp",
        ) as temporary_file:
            json.dump(
                payload,
                temporary_file,
                indent=2,
            )
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)

        os.replace(temporary_path, destination)
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

        raise LocalRemindersError(
            f"Could not save local reminders: {error}"
        ) from error


def save_reminder(
    text: str,
    *,
    kind: str,
    due_at: datetime,
    reminder_file: Path = REMINDERS_FILE,
    now: Callable[[], datetime] = _utc_now,
) -> LocalReminder:
    """Create one persistent timer or reminder with an atomic update."""
    reminder_text = _normalise_reminder_text(text)
    reminder_kind = _validate_reminder_kind(kind)

    created_at = now()
    created_at_utc = _format_utc_timestamp(created_at)
    due_at_utc = _format_utc_timestamp(due_at)

    if (
        _parse_utc_timestamp(
            due_at_utc,
            label="Reminder",
        )
        <= _parse_utc_timestamp(
            created_at_utc,
            label="Reminder",
        )
    ):
        raise LocalRemindersError(
            "A reminder due time must be in the future."
        )

    with _reminder_store_lock:
        store = _load_reminder_store(
            reminder_file=reminder_file
        )

        reminder = LocalReminder(
            reminder_id=store.next_id,
            text=reminder_text,
            kind=reminder_kind,
            due_at_utc=due_at_utc,
            created_at_utc=created_at_utc,
            status=REMINDER_STATUS_PENDING,
        )

        _write_reminder_store(
            _LocalReminderStore(
                reminders=(
                    *store.reminders,
                    reminder,
                ),
                next_id=reminder.reminder_id + 1,
            ),
            reminder_file=reminder_file,
        )

    return reminder


def cancel_reminder(
    reminder_id: int,
    *,
    expected_reminder: LocalReminder | None = None,
    reminder_file: Path = REMINDERS_FILE,
    now: Callable[[], datetime] = _utc_now,
) -> LocalReminder:
    """Cancel one exact pending reminder without reusing its id."""
    requested_id = _validate_reminder_id(reminder_id)

    with _reminder_store_lock:
        store = _load_reminder_store(
            reminder_file=reminder_file
        )

        target = next(
            (
                reminder
                for reminder in store.reminders
                if reminder.reminder_id == requested_id
            ),
            None,
        )

        if target is None:
            raise LocalRemindersError(
                f"Local reminder {requested_id} does not exist."
            )

        if expected_reminder is not None:
            if not isinstance(expected_reminder, LocalReminder):
                raise LocalRemindersError(
                    "Expected local reminder data is invalid."
                )

            if target != expected_reminder:
                raise LocalRemindersError(
                    "Local reminder changed since the cancel request."
                )

        if target.status == REMINDER_STATUS_DELIVERED:
            raise LocalRemindersError(
                f"Local reminder {requested_id} was already delivered."
            )

        if target.status == REMINDER_STATUS_CANCELLED:
            raise LocalRemindersError(
                f"Local reminder {requested_id} was already cancelled."
            )

        cancelled = replace(
            target,
            status=REMINDER_STATUS_CANCELLED,
            cancelled_at_utc=_format_utc_timestamp(now()),
        )

        updated_reminders = tuple(
            (
                cancelled
                if reminder.reminder_id == requested_id
                else reminder
            )
            for reminder in store.reminders
        )

        _write_reminder_store(
            _LocalReminderStore(
                reminders=updated_reminders,
                next_id=store.next_id,
            ),
            reminder_file=reminder_file,
        )

    return cancelled


def claim_due_reminders(
    *,
    reminder_file: Path = REMINDERS_FILE,
    now: Callable[[], datetime] = _utc_now,
) -> tuple[LocalReminder, ...]:
    """Atomically mark due reminders delivered and return them once."""
    claim_time_utc = _format_utc_timestamp(now())
    claim_time = _parse_utc_timestamp(
        claim_time_utc,
        label="Reminder claim",
    )

    with _reminder_store_lock:
        store = _load_reminder_store(
            reminder_file=reminder_file
        )

        due_reminders = tuple(
            reminder
            for reminder in store.reminders
            if (
                reminder.status == REMINDER_STATUS_PENDING
                and _parse_utc_timestamp(
                    reminder.due_at_utc,
                    label=(
                        f"Local reminder "
                        f"{reminder.reminder_id}"
                    ),
                )
                <= claim_time
            )
        )

        if not due_reminders:
            return ()

        due_ids = {
            reminder.reminder_id
            for reminder in due_reminders
        }

        delivered_reminders = tuple(
            replace(
                reminder,
                status=REMINDER_STATUS_DELIVERED,
                delivered_at_utc=claim_time_utc,
            )
            for reminder in due_reminders
        )

        delivered_by_id = {
            reminder.reminder_id: reminder
            for reminder in delivered_reminders
        }

        updated_reminders = tuple(
            (
                delivered_by_id[reminder.reminder_id]
                if reminder.reminder_id in due_ids
                else reminder
            )
            for reminder in store.reminders
        )

        _write_reminder_store(
            _LocalReminderStore(
                reminders=updated_reminders,
                next_id=store.next_id,
            ),
            reminder_file=reminder_file,
        )

    return tuple(
        sorted(
            delivered_reminders,
            key=lambda reminder: (
                reminder.due_at_utc,
                reminder.reminder_id,
            ),
        )
    )

def format_reminders(
    reminders: tuple[LocalReminder, ...],
) -> str:
    """Format stable local reminder details for console output."""
    if not reminders:
        return "\n".join(
            (
                "Local reminders:",
                "- No local reminders saved.",
            )
        )

    lines = ["Local reminders:"]

    for reminder in reminders:
        if reminder.status == REMINDER_STATUS_PENDING:
            state = f"PENDING | due {reminder.due_at_utc}"
        elif reminder.status == REMINDER_STATUS_DELIVERED:
            state = (
                "DELIVERED | "
                f"{reminder.delivered_at_utc}"
            )
        else:
            state = (
                "CANCELLED | "
                f"{reminder.cancelled_at_utc}"
            )

        lines.append(
            f"{reminder.reminder_id}. "
            f"[{state}] {reminder.text}"
        )

    return "\n".join(lines)

def format_due_reminder_alert(
    reminder: LocalReminder,
) -> str:
    """Return one short spoken alert for a claimed reminder."""
    if not isinstance(reminder, LocalReminder):
        raise LocalRemindersError(
            "A due reminder must contain valid reminder data."
        )

    if reminder.status != REMINDER_STATUS_DELIVERED:
        raise LocalRemindersError(
            "Only a delivered reminder can be announced."
        )

    if reminder.kind == REMINDER_KIND_TIMER:
        return (
            f"Timer {reminder.reminder_id} is complete, sir."
        )

    if reminder.kind == REMINDER_KIND_REMINDER:
        return (
            f"Reminder {reminder.reminder_id}: "
            f"{reminder.text}, sir."
        )

    raise LocalRemindersError(
        "A due reminder has an unsupported kind."
    )