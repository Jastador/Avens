from __future__ import annotations

from collections.abc import Callable

from skills.local_reminders import (
    LocalReminder,
    LocalRemindersError,
    format_due_reminder_alert,
)


def play_windows_reminder_chime() -> None:
    """Play one native Windows notification sound when possible."""
    try:
        import winsound

        winsound.MessageBeep(
            winsound.MB_ICONEXCLAMATION
        )
    except Exception as error:
        print(
            f"Local reminder alert sound error: {error}"
        )


def deliver_due_reminders(
    reminders: tuple[LocalReminder, ...],
    *,
    announce: Callable[[str], object],
    play_alert: Callable[[], None] = (
        play_windows_reminder_chime
    ),
    error_output: Callable[[str], None] = print,
) -> tuple[str, ...]:
    """Play and announce queued reminders on the app-owned thread."""
    delivered_messages: list[str] = []

    for reminder in reminders:
        try:
            message = format_due_reminder_alert(reminder)
        except LocalRemindersError as error:
            error_output(
                f"Local reminder delivery error: {error}"
            )
            continue

        try:
            play_alert()
        except Exception as error:
            error_output(
                f"Local reminder alert sound error: {error}"
            )

        try:
            announce(message)
        except Exception as error:
            error_output(
                f"Local reminder announcement error: {error}"
            )
            continue

        delivered_messages.append(message)

    return tuple(delivered_messages)