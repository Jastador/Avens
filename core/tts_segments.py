from __future__ import annotations

import re
from dataclasses import dataclass


_PERIOD_PLACEHOLDER = "\u2024"

_ALWAYS_PROTECTED_ABBREVIATIONS = (
    "mr.",
    "mrs.",
    "ms.",
    "dr.",
    "prof.",
    "sr.",
    "jr.",
    "st.",
    "e.g.",
    "i.e.",
)

_CONTEXTUAL_ABBREVIATIONS = (
    "vs.",
    "etc.",
    "a.m.",
    "p.m.",
)


def _replace_periods(
    match: re.Match[str],
) -> str:
    return match.group(0).replace(
        ".",
        _PERIOD_PLACEHOLDER,
    )


def _protect_non_terminal_periods(
    text: str,
) -> str:
    protected = re.sub(
        r"(?<=\d)\.(?=\d)",
        _PERIOD_PLACEHOLDER,
        text,
    )

    for abbreviation in (
        _ALWAYS_PROTECTED_ABBREVIATIONS
    ):
        protected = re.sub(
            rf"(?i:{re.escape(abbreviation)})",
            _replace_periods,
            protected,
        )

    for abbreviation in (
        _CONTEXTUAL_ABBREVIATIONS
    ):
        protected = re.sub(
            (
                rf"(?i:{re.escape(abbreviation)})"
                r"(?=\s+[a-z0-9])"
            ),
            _replace_periods,
            protected,
        )

    return protected


def _restore_periods(
    text: str,
) -> str:
    return text.replace(
        _PERIOD_PLACEHOLDER,
        ".",
    )


def _split_by_word_limit(
    text: str,
    max_characters: int,
) -> list[str]:
    pieces: list[str] = []
    current_words: list[str] = []
    current_length = 0

    for word in text.split():
        candidate_length = (
            len(word)
            if not current_words
            else current_length + 1 + len(word)
        )

        if (
            current_words
            and candidate_length > max_characters
        ):
            pieces.append(
                " ".join(current_words)
            )
            current_words = [word]
            current_length = len(word)
            continue

        current_words.append(word)
        current_length = candidate_length

    if current_words:
        pieces.append(
            " ".join(current_words)
        )

    return pieces


def _split_long_segment(
    segment: str,
    max_characters: int,
) -> list[str]:
    if len(segment) <= max_characters:
        return [segment]

    clauses = re.split(
        r"(?<=[,;:])\s+",
        segment,
    )
    grouped_clauses: list[str] = []
    current = ""

    for clause in clauses:
        candidate = (
            f"{current} {clause}".strip()
        )

        if (
            current
            and len(candidate) > max_characters
        ):
            grouped_clauses.append(current)
            current = clause
        else:
            current = candidate

    if current:
        grouped_clauses.append(current)

    segments: list[str] = []

    for clause_group in grouped_clauses:
        if (
            len(clause_group)
            <= max_characters
        ):
            segments.append(clause_group)
        else:
            segments.extend(
                _split_by_word_limit(
                    clause_group,
                    max_characters,
                )
            )

    return segments


def split_response_segments(
    text: str,
    max_characters: int = 240,
) -> tuple[str, ...]:
    """Split response text into resumable TTS segments."""

    if max_characters < 40:
        raise ValueError(
            "max_characters must be at least 40."
        )

    normalized = " ".join(
        str(text).split()
    )

    if not normalized:
        return ()

    protected = _protect_non_terminal_periods(
        normalized
    )
    sentence_candidates = re.findall(
        (
            r".+?"
            r"(?:[.!?]+(?:[\"')\]]+)?"
            r"(?=\s|$)|$)"
        ),
        protected,
    )

    segments: list[str] = []

    for sentence in sentence_candidates:
        restored = _restore_periods(
            sentence
        ).strip()

        if not restored:
            continue

        segments.extend(
            _split_long_segment(
                restored,
                max_characters,
            )
        )

    return tuple(segments)


@dataclass
class ResumableSpeechPlan:
    """Track completed and remaining response segments."""

    segments: tuple[str, ...]
    current_index: int = 0

    @classmethod
    def from_text(
        cls,
        text: str,
        max_characters: int = 240,
    ) -> "ResumableSpeechPlan":
        return cls(
            segments=split_response_segments(
                text,
                max_characters=max_characters,
            )
        )

    def __post_init__(self) -> None:
        self.segments = tuple(
            str(segment).strip()
            for segment in self.segments
            if str(segment).strip()
        )

        if not (
            0
            <= self.current_index
            <= len(self.segments)
        ):
            raise ValueError(
                "current_index must refer to the "
                "current segment or the completed "
                "position after the final segment."
            )

    @property
    def is_complete(self) -> bool:
        return self.current_index >= len(
            self.segments
        )

    @property
    def current_segment(
        self,
    ) -> str | None:
        if self.is_complete:
            return None

        return self.segments[
            self.current_index
        ]

    @property
    def completed_segments(
        self,
    ) -> tuple[str, ...]:
        return self.segments[
            : self.current_index
        ]

    @property
    def remaining_segments(
        self,
    ) -> tuple[str, ...]:
        return self.segments[
            self.current_index :
        ]

    @property
    def remaining_text(self) -> str:
        return " ".join(
            self.remaining_segments
        )

    def mark_current_complete(
        self,
    ) -> None:
        if self.is_complete:
            raise RuntimeError(
                "Cannot complete a speech plan "
                "that is already complete."
            )

        self.current_index += 1