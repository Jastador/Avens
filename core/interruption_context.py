from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class InterruptedResponse:
    """One assistant response paused by directed user speech."""

    response_text: str
    interrupted_by: str
    depth: int


@dataclass
class InterruptionContextStack:
    """Track unfinished responses across nested interruptions."""

    maximum_depth: int = 5
    _frames: list[InterruptedResponse] = field(
        default_factory=list,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.maximum_depth < 1:
            raise ValueError(
                "maximum_depth must be at least one."
            )

    @property
    def depth(self) -> int:
        return len(self._frames)

    @property
    def is_empty(self) -> bool:
        return not self._frames

    @property
    def can_resume(self) -> bool:
        return not self.is_empty

    @property
    def current(self) -> InterruptedResponse | None:
        if self.is_empty:
            return None

        return self._frames[-1]

    @property
    def frames(self) -> tuple[InterruptedResponse, ...]:
        return tuple(self._frames)

    def push(
        self,
        response_text: object,
        *,
        interrupted_by: object,
    ) -> InterruptedResponse | None:
        """Store one unfinished response.

        Empty responses are ignored because there is nothing useful to
        resume after the interruption has been answered.
        """

        normalized_response = " ".join(
            str(response_text).split()
        )

        normalized_interruption = " ".join(
            str(interrupted_by).split()
        )

        if not normalized_response:
            return None

        if self.depth >= self.maximum_depth:
            # Discard the oldest frame while retaining the most recent
            # conversational context.
            self._frames.pop(0)

        frame = InterruptedResponse(
            response_text=normalized_response,
            interrupted_by=normalized_interruption,
            depth=self.depth + 1,
        )

        self._frames.append(frame)
        return frame

    def peek(self) -> InterruptedResponse | None:
        """Return the newest paused response without removing it."""

        return self.current

    def pop(self) -> InterruptedResponse | None:
        """Remove and return the newest paused response."""

        if self.is_empty:
            return None

        return self._frames.pop()

    def discard_current(self) -> InterruptedResponse | None:
        """Discard the newest paused response."""

        return self.pop()

    def clear(self) -> tuple[InterruptedResponse, ...]:
        """Discard every paused response and return what was removed."""

        removed = tuple(self._frames)
        self._frames.clear()
        return removed