from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import (
    datetime,
    timedelta,
    timezone,
)


class ReminderScheduleError(ValueError):
    """Raised when a deterministic reminder time is invalid."""


@dataclass(frozen=True)
class ReminderSchedule:
    """One validated future due time with a spoken description."""

    due_at_utc: datetime
    description: str


def _local_now() -> datetime:
    """Return the current local timezone-aware system time."""
    return datetime.now().astimezone()


def _require_aware_datetime(
    value: datetime,
    *,
    label: str,
) -> datetime:
    """Require one timezone-aware datetime."""
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ReminderScheduleError(
            f"{label} must include a timezone."
        )

    return value


def _validate_non_negative_int(
    value: int,
    *,
    label: str,
) -> int:
    """Validate one non-negative whole number."""
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise ReminderScheduleError(
            f"{label} must be a non-negative whole number."
        )

    return value

_DURATION_COMPONENT_PATTERN = re.compile(
    r"(?P<amount>[0-9]+)\s*"
    r"(?P<unit>hours?|minutes?|seconds?)",
    re.IGNORECASE,
)

_DURATION_SEPARATOR_PATTERN = re.compile(
    r"\s*(?:,\s*)?(?:and\s*)?\s*",
    re.IGNORECASE,
)


def parse_duration_components(
    value: str,
) -> tuple[int, int, int]:
    """Parse one explicit hours/minutes/seconds duration."""
    if not isinstance(value, str):
        raise ReminderScheduleError(
            "A reminder duration must contain text."
        )

    text = " ".join(value.split())

    if not text:
        raise ReminderScheduleError(
            "A reminder duration must contain text."
        )

    matches = list(
        _DURATION_COMPONENT_PATTERN.finditer(text)
    )

    if not matches:
        raise ReminderScheduleError(
            "A reminder duration must use hours, minutes, or seconds."
        )

    values = {
        "hour": 0,
        "minute": 0,
        "second": 0,
    }
    seen_units: set[str] = set()
    cursor = 0

    for match in matches:
        separator = text[cursor:match.start()]

        if cursor == 0:
            if separator:
                raise ReminderScheduleError(
                    "A reminder duration contains invalid text."
                )
        elif _DURATION_SEPARATOR_PATTERN.fullmatch(
            separator
        ) is None:
            raise ReminderScheduleError(
                "A reminder duration contains invalid text."
            )

        amount = int(match.group("amount"))
        unit = match.group("unit").casefold().rstrip("s")

        if unit in seen_units:
            raise ReminderScheduleError(
                "A reminder duration cannot repeat a unit."
            )

        seen_units.add(unit)
        values[unit] = amount
        cursor = match.end()

    if text[cursor:].strip():
        raise ReminderScheduleError(
            "A reminder duration contains invalid text."
        )

    format_duration(
        hours=values["hour"],
        minutes=values["minute"],
        seconds=values["second"],
    )

    return (
        values["hour"],
        values["minute"],
        values["second"],
    )

def format_duration(
    *,
    hours: int = 0,
    minutes: int = 0,
    seconds: int = 0,
) -> str:
    """Format one non-zero duration for a spoken acknowledgement."""
    safe_hours = _validate_non_negative_int(
        hours,
        label="Hours",
    )
    safe_minutes = _validate_non_negative_int(
        minutes,
        label="Minutes",
    )
    safe_seconds = _validate_non_negative_int(
        seconds,
        label="Seconds",
    )

    parts = []

    if safe_hours:
        parts.append(
            f"{safe_hours} hour"
            f"{'' if safe_hours == 1 else 's'}"
        )

    if safe_minutes:
        parts.append(
            f"{safe_minutes} minute"
            f"{'' if safe_minutes == 1 else 's'}"
        )

    if safe_seconds:
        parts.append(
            f"{safe_seconds} second"
            f"{'' if safe_seconds == 1 else 's'}"
        )

    if not parts:
        raise ReminderScheduleError(
            "A reminder duration must be greater than zero."
        )

    if len(parts) == 1:
        return parts[0]

    if len(parts) == 2:
        return " and ".join(parts)

    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def schedule_after_duration(
    *,
    hours: int = 0,
    minutes: int = 0,
    seconds: int = 0,
    now: Callable[[], datetime] = _local_now,
) -> ReminderSchedule:
    """Schedule one reminder after an explicit positive duration."""
    safe_hours = _validate_non_negative_int(
        hours,
        label="Hours",
    )
    safe_minutes = _validate_non_negative_int(
        minutes,
        label="Minutes",
    )
    safe_seconds = _validate_non_negative_int(
        seconds,
        label="Seconds",
    )

    description = format_duration(
        hours=safe_hours,
        minutes=safe_minutes,
        seconds=safe_seconds,
    )

    current_time = _require_aware_datetime(
        now(),
        label="Current time",
    )

    due_at_utc = (
        current_time.astimezone(timezone.utc)
        + timedelta(
            hours=safe_hours,
            minutes=safe_minutes,
            seconds=safe_seconds,
        )
    )

    return ReminderSchedule(
        due_at_utc=due_at_utc,
        description=f"in {description}",
    )


def schedule_tomorrow_at(
    *,
    hour: int,
    minute: int,
    meridiem: str,
    now: Callable[[], datetime] = _local_now,
) -> ReminderSchedule:
    """Schedule one reminder tomorrow at an explicit local clock time."""
    if (
        not isinstance(hour, int)
        or isinstance(hour, bool)
        or hour < 1
        or hour > 12
    ):
        raise ReminderScheduleError(
            "Hour must be between 1 and 12."
        )

    if (
        not isinstance(minute, int)
        or isinstance(minute, bool)
        or minute < 0
        or minute > 59
    ):
        raise ReminderScheduleError(
            "Minute must be between 0 and 59."
        )

    if not isinstance(meridiem, str):
        raise ReminderScheduleError(
            "Meridiem must be AM or PM."
        )

    clean_meridiem = meridiem.casefold().strip()

    if clean_meridiem not in {"am", "pm"}:
        raise ReminderScheduleError(
            "Meridiem must be AM or PM."
        )

    local_now = _require_aware_datetime(
        now(),
        label="Current time",
    ).astimezone()

    hour_24 = hour % 12

    if clean_meridiem == "pm":
        hour_24 += 12

    tomorrow_date = (
        local_now + timedelta(days=1)
    ).date()

    due_at_local = datetime(
        tomorrow_date.year,
        tomorrow_date.month,
        tomorrow_date.day,
        hour_24,
        minute,
        tzinfo=local_now.tzinfo,
    )

    due_at_utc = due_at_local.astimezone(timezone.utc)

    return ReminderSchedule(
        due_at_utc=due_at_utc,
        description=(
            "tomorrow at "
            f"{hour}:{minute:02d} {clean_meridiem.upper()}"
        ),
    )