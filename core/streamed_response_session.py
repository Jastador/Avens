from __future__ import annotations

from dataclasses import dataclass, field


def _normalise_segment(text: object) -> str:
    """Collapse unnecessary whitespace in one generated text event."""

    return " ".join(str(text).split())


@dataclass
class StreamedResponseSession:
    """Track one streamed assistant response across multiple text events.

    The brain may generate several separate text events for one answer.
    This session keeps those events together so interruption handling can
    preserve the current unfinished event and any text generated later.
    """

    segments: list[str] = field(default_factory=list)
    completed_count: int = 0
    active_index: int | None = None
    generation_complete: bool = False
    interrupted: bool = False

    def __post_init__(self) -> None:
        self.segments = [
            normalized
            for segment in self.segments
            if (
                normalized
                := _normalise_segment(segment)
            )
        ]

        if not (
            0
            <= self.completed_count
            <= len(self.segments)
        ):
            raise ValueError(
                "completed_count must be between zero "
                "and the number of response segments."
            )

        if self.active_index is not None:
            if not (
                0
                <= self.active_index
                < len(self.segments)
            ):
                raise ValueError(
                    "active_index must refer to an "
                    "existing response segment."
                )

            if self.active_index != self.completed_count:
                raise ValueError(
                    "active_index must refer to the "
                    "next uncompleted response segment."
                )

    @property
    def completed_segments(
        self,
    ) -> tuple[str, ...]:
        """Return text events that finished playback."""

        return tuple(
            self.segments[: self.completed_count]
        )

    @property
    def current_segment(
        self,
    ) -> str | None:
        """Return the text event currently being spoken."""

        if self.active_index is None:
            return None

        return self.segments[self.active_index]

    @property
    def pending_segments(
        self,
    ) -> tuple[str, ...]:
        """Return the unfinished event and all later events."""

        return tuple(
            self.segments[self.completed_count :]
        )

    @property
    def completed_text(self) -> str:
        """Join text events that finished playback."""

        return " ".join(self.completed_segments)

    @property
    def remaining_text(self) -> str:
        """Join all text that has not finished playback."""

        return " ".join(self.pending_segments)

    @property
    def has_pending_text(self) -> bool:
        return self.completed_count < len(
            self.segments
        )

    @property
    def can_execute_generated_actions(
        self,
    ) -> bool:
        """Block later LLM-generated actions after interruption."""

        return not self.interrupted

    @property
    def is_complete(self) -> bool:
        """Return True only when generation and playback both finish."""

        return (
            self.generation_complete
            and not self.has_pending_text
            and self.active_index is None
        )

    def append_text(
        self,
        text: object,
    ) -> bool:
        """Append one generated text event.

        Empty events are ignored. New events may still arrive after an
        interruption while the brain stream is being safely drained.
        """

        if self.generation_complete:
            raise RuntimeError(
                "Cannot append text after generation "
                "has been marked complete."
            )

        normalized = _normalise_segment(text)

        if not normalized:
            return False

        self.segments.append(normalized)
        return True

    def begin_next_segment(
        self,
    ) -> str | None:
        """Mark the next pending text event as actively speaking."""

        if self.active_index is not None:
            raise RuntimeError(
                "A response segment is already active."
            )

        if self.interrupted:
            raise RuntimeError(
                "Cannot start another segment after "
                "the response was interrupted."
            )

        if not self.has_pending_text:
            return None

        self.active_index = self.completed_count
        return self.current_segment

    def mark_current_complete(
        self,
    ) -> None:
        """Record successful playback of the active event."""

        if self.active_index is None:
            raise RuntimeError(
                "No active response segment can be completed."
            )

        if self.active_index != self.completed_count:
            raise RuntimeError(
                "Active response state is inconsistent."
            )

        self.completed_count += 1
        self.active_index = None

    def mark_interrupted(
        self,
    ) -> None:
        """Record an interruption when no text segment is active."""

        if self.active_index is not None:
            raise RuntimeError(
                "Use mark_current_interrupted while "
                "a response segment is active."
            )

        self.interrupted = True

    def mark_current_interrupted(
        self,
        remaining_text: object | None = None,
    ) -> None:
        """Preserve the precise unfinished portion of the active event."""

        if self.active_index is None:
            raise RuntimeError(
                "No active response segment can be interrupted."
            )

        if self.active_index != self.completed_count:
            raise RuntimeError(
                "Active response state is inconsistent."
            )

        if remaining_text is not None:
            normalized = _normalise_segment(
                remaining_text
            )

            if normalized:
                self.segments[
                    self.active_index
                ] = normalized

        self.active_index = None
        self.interrupted = True

    def mark_generation_complete(
        self,
    ) -> None:
        """Record that the brain will emit no more events."""

        self.generation_complete = True