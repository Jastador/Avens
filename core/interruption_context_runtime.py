from __future__ import annotations

from dataclasses import dataclass, field

from core.interruption_context import (
    InterruptedResponse,
    InterruptionContextStack,
)
from core.interruption_return_policy import (
    InterruptionReturnDecision,
    decide_interruption_return,
)


@dataclass(frozen=True)
class InterruptionContextUpdate:
    """Result of applying one directed interruption."""

    decision: InterruptionReturnDecision
    stored_frame: InterruptedResponse | None
    discarded_frames: tuple[
        InterruptedResponse,
        ...,
    ]

    @property
    def preserved(self) -> bool:
        return (
            self.decision.should_preserve
            and self.stored_frame is not None
        )

    @property
    def replaced(self) -> bool:
        return not self.decision.should_preserve

    @property
    def discarded_count(self) -> int:
        return len(self.discarded_frames)


@dataclass
class InterruptionContextCoordinator:
    """Coordinate interrupted-response preservation and return order."""

    stack: InterruptionContextStack = field(
        default_factory=(
            InterruptionContextStack
        )
    )

    @property
    def depth(self) -> int:
        return self.stack.depth

    @property
    def has_pending_return(self) -> bool:
        return self.stack.can_resume

    @property
    def current(self) -> InterruptedResponse | None:
        return self.stack.current

    def handle_directed_interruption(
        self,
        *,
        paused_response: object,
        transcript: object,
        classification_reason: object = "",
    ) -> InterruptionContextUpdate:
        """Preserve or replace context for one directed interruption."""

        decision = decide_interruption_return(
            transcript,
            classification_reason=(
                classification_reason
            ),
        )

        if decision.should_preserve:
            frame = self.stack.push(
                paused_response,
                interrupted_by=transcript,
            )

            return InterruptionContextUpdate(
                decision=decision,
                stored_frame=frame,
                discarded_frames=(),
            )

        discarded = self.stack.clear()

        return InterruptionContextUpdate(
            decision=decision,
            stored_frame=None,
            discarded_frames=discarded,
        )

    def take_next_response(
        self,
    ) -> InterruptedResponse | None:
        """Remove and return the newest response awaiting resumption."""

        return self.stack.pop()

    def peek_next_response(
        self,
    ) -> InterruptedResponse | None:
        """Read the newest resumable response without removing it."""

        return self.stack.peek()

    def clear(
        self,
    ) -> tuple[InterruptedResponse, ...]:
        """Discard all pending interrupted responses."""

        return self.stack.clear()