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

def find_chunk_span(
    text: str,
    chunk_text: str,
    *,
    start_offset: int = 0,
) -> tuple[int, int]:
    """Locate one generated TTS text chunk inside its segment.

    Kokoro returns the text associated with each generated audio chunk.
    The search begins after previously completed chunks so repeated words
    earlier in the segment do not select the wrong position.
    """

    source = str(text)
    chunk = " ".join(
        str(chunk_text).split()
    )

    if not (
        0 <= start_offset <= len(source)
    ):
        raise ValueError(
            "start_offset must be inside the source text."
        )

    if not chunk:
        return (
            start_offset,
            start_offset,
        )

    chunk_start = source.find(
        chunk,
        start_offset,
    )

    if chunk_start < 0:
        chunk_start = source.casefold().find(
            chunk.casefold(),
            start_offset,
        )

    if chunk_start < 0:
        # Safe fallback when Kokoro normalises punctuation or spacing.
        chunk_start = start_offset
        chunk_end = min(
            len(source),
            chunk_start + len(chunk),
        )

        return (
            chunk_start,
            chunk_end,
        )

    return (
        chunk_start,
        chunk_start + len(chunk),
    )


def estimate_resume_offset(
    text: str,
    *,
    chunk_start: int,
    chunk_end: int,
    elapsed_seconds: float,
    duration_seconds: float,
    replay_words: int = 1,
) -> int:
    """Estimate a conservative word boundary for interrupted playback.

    The estimate uses the fraction of the current audio chunk that finished.
    One previously spoken word is replayed by default so resumption does not
    begin halfway through a phrase or accidentally omit meaning.
    """

    source = str(text)

    if not (
        0 <= chunk_start
        <= chunk_end
        <= len(source)
    ):
        raise ValueError(
            "Chunk boundaries must be inside the source text."
        )

    if replay_words < 0:
        raise ValueError(
            "replay_words cannot be negative."
        )

    if chunk_start == chunk_end:
        return chunk_end

    if duration_seconds <= 0:
        return chunk_start

    progress = max(
        0.0,
        min(
            1.0,
            elapsed_seconds
            / duration_seconds,
        ),
    )

    chunk = source[
        chunk_start:chunk_end
    ]

    word_matches = list(
        re.finditer(
            r"\S+",
            chunk,
        )
    )

    if not word_matches:
        return chunk_end

    spoken_word_count = min(
        len(word_matches),
        int(
            progress
            * len(word_matches)
        ),
    )

    resume_word_index = max(
        0,
        spoken_word_count
        - replay_words,
    )

    if (
        resume_word_index
        >= len(word_matches)
    ):
        return chunk_end

    return (
        chunk_start
        + word_matches[
            resume_word_index
        ].start()
    )

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

    def remaining_text_from_offset(
        self,
        offset: int,
    ) -> str:
        """Return remaining speech from an offset in the active segment."""

        current = self.current_segment

        if current is None:
            return ""

        if not (
            0 <= offset <= len(current)
        ):
            raise ValueError(
                "offset must be inside the current segment."
            )

        pieces: list[str] = []

        current_remainder = current[
            offset:
        ].strip()

        if current_remainder:
            pieces.append(
                current_remainder
            )

        pieces.extend(
            self.segments[
                self.current_index + 1:
            ]
        )

        return " ".join(pieces)

    def mark_current_complete(
        self,
    ) -> None:
        if self.is_complete:
            raise RuntimeError(
                "Cannot complete a speech plan "
                "that is already complete."
            )

        self.current_index += 1