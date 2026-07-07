from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from skills.local_reminders import LocalReminder


REMINDER_CANCEL_CONFIRMATION_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True)
class PendingReminderCancelRequest:
    """One exact pending reminder cancellation awaiting confirmation."""

    reminder_id: int
    reminder_text: str
    kind: str
    due_at_utc: str
    created_at_utc: str
    status: str
    expires_at: float


@dataclass(frozen=True)
class ReminderCancelConfirmationDecision:
    """The result of one exact reminder-cancel confirmation."""

    status: str
    request: PendingReminderCancelRequest | None


class ReminderCancelConfirmationStore:
    """Keep one short-lived reminder cancellation in memory."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        timeout_seconds: float = (
            REMINDER_CANCEL_CONFIRMATION_TIMEOUT_SECONDS
        ),
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(
                "Reminder-cancel confirmation timeout must be positive."
            )

        self._clock = clock
        self._timeout_seconds = timeout_seconds
        self._pending: PendingReminderCancelRequest | None = None

    def begin(
        self,
        reminder: LocalReminder,
    ) -> PendingReminderCancelRequest:
        """Replace any previous pending cancellation with this reminder."""
        request = PendingReminderCancelRequest(
            reminder_id=reminder.reminder_id,
            reminder_text=reminder.text,
            kind=reminder.kind,
            due_at_utc=reminder.due_at_utc,
            created_at_utc=reminder.created_at_utc,
            status=reminder.status,
            expires_at=(
                self._clock()
                + self._timeout_seconds
            ),
        )
        self._pending = request

        return request

    def confirm(
        self,
        reminder_id: int,
    ) -> ReminderCancelConfirmationDecision:
        """Confirm only the exact pending reminder id, then clear it."""
        request = self._pending

        if request is None:
            return ReminderCancelConfirmationDecision(
                status="none",
                request=None,
            )

        self._pending = None

        if self._clock() >= request.expires_at:
            return ReminderCancelConfirmationDecision(
                status="expired",
                request=request,
            )

        if reminder_id != request.reminder_id:
            return ReminderCancelConfirmationDecision(
                status="mismatch",
                request=request,
            )

        return ReminderCancelConfirmationDecision(
            status="confirmed",
            request=request,
        )

    def cancel(self) -> PendingReminderCancelRequest | None:
        """Cancel and return the current pending reminder cancellation."""
        request = self._pending
        self._pending = None

        return request


reminder_cancel_confirmation_store = (
    ReminderCancelConfirmationStore()
)