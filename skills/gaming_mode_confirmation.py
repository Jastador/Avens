from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Final


GAMING_MODE_CONFIRMATION_TIMEOUT_SECONDS: Final = 120.0


@dataclass(frozen=True)
class GamingModeConfirmationRequest:
    """One pending Gaming Mode continuation request."""

    requested_at_seconds: float


@dataclass(frozen=True)
class GamingModeConfirmationDecision:
    """Result of confirming a pending Gaming Mode request."""

    status: str
    request: GamingModeConfirmationRequest | None = None


class GamingModeConfirmationStore:
    """In-memory confirmation store for one pending Gaming Mode run."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = monotonic,
        timeout_seconds: float = GAMING_MODE_CONFIRMATION_TIMEOUT_SECONDS,
    ) -> None:
        self._clock = clock
        self._timeout_seconds = timeout_seconds
        self._pending_request: GamingModeConfirmationRequest | None = None
        self._lock = Lock()

    def begin(self) -> GamingModeConfirmationRequest:
        """Start or replace one pending Gaming Mode confirmation."""
        with self._lock:
            request = GamingModeConfirmationRequest(
                requested_at_seconds=self._clock()
            )
            self._pending_request = request
            return request

    def confirm(self) -> GamingModeConfirmationDecision:
        """Confirm the pending request if it still exists and is fresh."""
        with self._lock:
            request = self._pending_request

            if request is None:
                return GamingModeConfirmationDecision(status="none")

            self._pending_request = None

            if (
                self._clock() - request.requested_at_seconds
                > self._timeout_seconds
            ):
                return GamingModeConfirmationDecision(
                    status="expired",
                    request=request,
                )

            return GamingModeConfirmationDecision(
                status="confirmed",
                request=request,
            )

    def cancel(self) -> GamingModeConfirmationRequest | None:
        """Cancel the pending request, if one exists."""
        with self._lock:
            request = self._pending_request
            self._pending_request = None
            return request


gaming_mode_confirmation_store = GamingModeConfirmationStore()