from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic

from skills.app_catalog import normalise_name


CLOSE_CONFIRMATION_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True)
class PendingCloseRequest:
    """One short-lived, exact named-window close request."""

    requested_name: str
    normalized_name: str
    display_name: str
    close_all: bool
    expires_at: float


@dataclass(frozen=True)
class CloseConfirmationDecision:
    """Result of checking one explicit close confirmation."""

    status: str
    request: PendingCloseRequest | None


class CloseConfirmationStore:
    """Keep one short-lived close confirmation without window handles."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = monotonic,
        timeout_seconds: float = CLOSE_CONFIRMATION_TIMEOUT_SECONDS,
    ) -> None:
        self._clock = clock
        self._timeout_seconds = timeout_seconds
        self._pending: PendingCloseRequest | None = None

    def begin(
        self,
        requested_name: str,
        display_name: str,
        *,
        close_all: bool,
    ) -> PendingCloseRequest:
        """Replace any previous request with one new exact close request."""
        normalized_name = normalise_name(requested_name)

        if not normalized_name:
            raise ValueError(
                "A close confirmation needs a non-empty app name."
            )

        request = PendingCloseRequest(
            requested_name=requested_name.strip(),
            normalized_name=normalized_name,
            display_name=display_name.strip() or "that app",
            close_all=close_all,
            expires_at=(
                self._clock()
                + self._timeout_seconds
            ),
        )

        self._pending = request

        return request

    def cancel(self) -> PendingCloseRequest | None:
        """Forget the pending close request without sending any close."""
        request = self._pending
        self._pending = None

        return request

    def confirm(
        self,
        requested_name: str,
        *,
        close_all: bool,
    ) -> CloseConfirmationDecision:
        """Consume one pending request only when confirmation matches."""
        request = self._pending
        self._pending = None

        if request is None:
            return CloseConfirmationDecision(
                status="none",
                request=None,
            )

        if self._clock() >= request.expires_at:
            return CloseConfirmationDecision(
                status="expired",
                request=request,
            )

        if (
            normalise_name(requested_name)
            != request.normalized_name
            or close_all != request.close_all
        ):
            return CloseConfirmationDecision(
                status="mismatch",
                request=request,
            )

        return CloseConfirmationDecision(
            status="confirmed",
            request=request,
        )


close_confirmation_store = CloseConfirmationStore()