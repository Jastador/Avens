from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


DEFAULT_NITROSENSE_CONFIRMATION_TTL_SECONDS = 60


@dataclass(frozen=True)
class NitroSenseGamingProfileConfirmationRequest:
    """One pending NitroSense gaming-profile confirmation."""

    created_at_utc: datetime
    expires_at_utc: datetime


@dataclass(frozen=True)
class NitroSenseGamingProfileConfirmationDecision:
    """Result of confirming a pending NitroSense request."""

    status: str
    request: NitroSenseGamingProfileConfirmationRequest | None


def utc_now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


class NitroSenseGamingProfileConfirmationStore:
    """In-memory confirmation store for one NitroSense hardware action."""

    def __init__(
        self,
        *,
        ttl_seconds: int = DEFAULT_NITROSENSE_CONFIRMATION_TTL_SECONDS,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """Create a confirmation store with a short expiry window."""
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be at least 1.")

        self._ttl = timedelta(seconds=ttl_seconds)
        self._clock = clock
        self._pending_request: (
            NitroSenseGamingProfileConfirmationRequest | None
        ) = None

    def begin(self) -> NitroSenseGamingProfileConfirmationRequest:
        """Start or replace the pending NitroSense confirmation."""
        created_at = self._clock()
        request = NitroSenseGamingProfileConfirmationRequest(
            created_at_utc=created_at,
            expires_at_utc=created_at + self._ttl,
        )
        self._pending_request = request

        return request

    def confirm(self) -> NitroSenseGamingProfileConfirmationDecision:
        """Confirm the pending request if it still exists and is fresh."""
        request = self._pending_request

        if request is None:
            return NitroSenseGamingProfileConfirmationDecision(
                status="none",
                request=None,
            )

        self._pending_request = None

        if self._clock() > request.expires_at_utc:
            return NitroSenseGamingProfileConfirmationDecision(
                status="expired",
                request=request,
            )

        return NitroSenseGamingProfileConfirmationDecision(
            status="confirmed",
            request=request,
        )

    def cancel(
        self,
    ) -> NitroSenseGamingProfileConfirmationRequest | None:
        """Cancel the pending request, if any."""
        request = self._pending_request
        self._pending_request = None

        return request


nitrosense_gaming_profile_confirmation_store = (
    NitroSenseGamingProfileConfirmationStore()
)