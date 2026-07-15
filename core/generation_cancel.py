from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event, Lock


@dataclass
class GenerationCancellationToken:
    """Thread-safe cancellation state for one brain generation."""

    generation_id: int

    _cancel_event: Event = field(
        default_factory=Event,
        init=False,
        repr=False,
        compare=False,
    )

    _reason: str = field(
        default="",
        init=False,
        repr=False,
        compare=False,
    )

    _reason_lock: Lock = field(
        default_factory=Lock,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if self.generation_id < 1:
            raise ValueError(
                "generation_id must be at least one."
            )

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    @property
    def reason(self) -> str:
        with self._reason_lock:
            return self._reason

    def cancel(
        self,
        reason: object = "",
    ) -> bool:
        """Cancel this generation once.

        Returns True only when this call performs the cancellation.
        Later cancellation attempts preserve the original reason.
        """

        normalized_reason = " ".join(
            str(reason).split()
        )

        if not normalized_reason:
            normalized_reason = "cancelled"

        with self._reason_lock:
            if self._cancel_event.is_set():
                return False

            self._reason = normalized_reason
            self._cancel_event.set()
            return True


@dataclass
class GenerationCancellationController:
    """Own the cancellation token for the active brain generation."""

    _lock: Lock = field(
        default_factory=Lock,
        init=False,
        repr=False,
        compare=False,
    )

    _next_generation_id: int = field(
        default=1,
        init=False,
        repr=False,
    )

    _active_token: (
        GenerationCancellationToken | None
    ) = field(
        default=None,
        init=False,
        repr=False,
    )

    @property
    def active_token(
        self,
    ) -> GenerationCancellationToken | None:
        with self._lock:
            return self._active_token

    @property
    def active_generation_id(
        self,
    ) -> int | None:
        token = self.active_token

        if token is None:
            return None

        return token.generation_id

    @property
    def has_active_generation(self) -> bool:
        return self.active_token is not None

    def begin_generation(
        self,
    ) -> GenerationCancellationToken:
        """Create and activate a new generation token.

        Any older active token is cancelled before the new generation
        becomes active.
        """

        with self._lock:
            previous_token = self._active_token

            if previous_token is not None:
                previous_token.cancel(
                    "superseded_by_new_generation"
                )

            token = GenerationCancellationToken(
                generation_id=(
                    self._next_generation_id
                )
            )

            self._next_generation_id += 1
            self._active_token = token

            return token

    def cancel_active(
        self,
        reason: object = "",
    ) -> bool:
        """Cancel the currently active generation."""

        with self._lock:
            token = self._active_token

            if token is None:
                return False

            return token.cancel(reason)

    def finish_generation(
        self,
        token: GenerationCancellationToken,
    ) -> bool:
        """Clear the token only if it is still the active generation.

        A stale generation finishing late cannot clear a newer token.
        """

        with self._lock:
            if self._active_token is not token:
                return False

            self._active_token = None
            return True