from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from skills.local_notes import LocalNote


NOTE_DELETE_CONFIRMATION_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True)
class PendingNoteDeleteRequest:
    """One exact local note deletion waiting for spoken confirmation."""

    note_id: int
    note_text: str
    created_at_utc: str
    expires_at: float


@dataclass(frozen=True)
class NoteDeleteConfirmationDecision:
    """The result of one exact note-delete confirmation attempt."""

    status: str
    request: PendingNoteDeleteRequest | None


class NoteDeleteConfirmationStore:
    """Keep one short-lived note-delete confirmation in memory."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        timeout_seconds: float = (
            NOTE_DELETE_CONFIRMATION_TIMEOUT_SECONDS
        ),
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(
                "Note-delete confirmation timeout must be positive."
            )

        self._clock = clock
        self._timeout_seconds = timeout_seconds
        self._pending: PendingNoteDeleteRequest | None = None

    def begin(
        self,
        note: LocalNote,
    ) -> PendingNoteDeleteRequest:
        """Replace any prior pending note deletion with this exact note."""
        request = PendingNoteDeleteRequest(
            note_id=note.note_id,
            note_text=note.text,
            created_at_utc=note.created_at_utc,
            expires_at=(
                self._clock()
                + self._timeout_seconds
            ),
        )
        self._pending = request

        return request

    def confirm(
        self,
        note_id: int,
    ) -> NoteDeleteConfirmationDecision:
        """Confirm only the exact pending note id, then clear it."""
        request = self._pending

        if request is None:
            return NoteDeleteConfirmationDecision(
                status="none",
                request=None,
            )

        self._pending = None

        if self._clock() >= request.expires_at:
            return NoteDeleteConfirmationDecision(
                status="expired",
                request=request,
            )

        if note_id != request.note_id:
            return NoteDeleteConfirmationDecision(
                status="mismatch",
                request=request,
            )

        return NoteDeleteConfirmationDecision(
            status="confirmed",
            request=request,
        )

    def cancel(self) -> PendingNoteDeleteRequest | None:
        """Cancel and return the current pending note deletion."""
        request = self._pending
        self._pending = None

        return request


note_delete_confirmation_store = NoteDeleteConfirmationStore()