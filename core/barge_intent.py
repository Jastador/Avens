from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum

from core.attention import SIDE_TALK_PATTERNS


class BargeInIntent(str, Enum):
    """Possible meanings of speech detected while Avens is talking."""

    DIRECTED = "directed"
    ACKNOWLEDGEMENT = "acknowledgement"
    BACKGROUND = "background"
    ECHO = "echo"
    UNCLEAR = "unclear"


@dataclass(frozen=True)
class BargeInDecision:
    """Classification result for one possible interruption."""

    intent: BargeInIntent
    reason: str
    confidence: float

    @property
    def is_directed(self) -> bool:
        return self.intent is BargeInIntent.DIRECTED

    @property
    def should_resume(self) -> bool:
        return self.intent in {
            BargeInIntent.ACKNOWLEDGEMENT,
            BargeInIntent.BACKGROUND,
            BargeInIntent.ECHO,
            BargeInIntent.UNCLEAR,
        }


ACKNOWLEDGEMENT_PHRASES = {
    "hm",
    "hmm",
    "right",
    "okay",
    "ok",
    "yeah",
    "yes",
    "yep",
    "alright",
    "sure",
    "got it",
    "understood",
    "makes sense",
}

DIRECT_ADDRESS_PATTERNS = (
    r"\bavens\b",
    r"\bevans\b",
    r"\bhey avens\b",
    r"\bhey evans\b",
    r"\bokay avens\b",
    r"\blisten avens\b",
)

QUESTION_STARTERS = (
    "what ",
    "why ",
    "how ",
    "when ",
    "where ",
    "who ",
    "which ",
    "can ",
    "could ",
    "would ",
    "should ",
    "is ",
    "are ",
    "do ",
    "does ",
    "did ",
)

COMMAND_STARTERS = (
    "open ",
    "close ",
    "stop",
    "pause",
    "continue",
    "explain ",
    "tell me ",
    "show me ",
    "search ",
    "find ",
    "play ",
    "remind ",
    "set ",
    "turn ",
    "switch ",
    "run ",
    "start ",
    "cancel ",
)

CORRECTION_STARTERS = (
    "no ",
    "nope ",
    "that is wrong",
    "that's wrong",
    "that is not correct",
    "that's not correct",
    "you are wrong",
    "you're wrong",
    "wait ",
    "hold on",
)


def normalise_barge_text(text: object) -> str:
    """Normalise a transcript for deterministic intent checks."""

    cleaned = re.sub(
        r"[^a-z0-9\s']+",
        " ",
        str(text).casefold(),
    )

    return " ".join(cleaned.split())


def _echo_similarity(
    transcript: str,
    spoken_text: str,
) -> float:
    """Estimate whether the microphone captured Avens' own speech."""

    if not transcript or not spoken_text:
        return 0.0

    transcript_words = transcript.split()

    # Very short phrases are too ambiguous for echo matching.
    if len(transcript_words) < 3:
        return 0.0

    if transcript == spoken_text:
        return 1.0

    if (
        len(transcript) >= 18
        and transcript in spoken_text
    ):
        return 0.96

    transcript_tokens = set(transcript_words)
    spoken_tokens = set(spoken_text.split())

    if not transcript_tokens:
        return 0.0

    token_overlap = (
        len(transcript_tokens & spoken_tokens)
        / len(transcript_tokens)
    )

    sequence_similarity = SequenceMatcher(
        None,
        transcript,
        spoken_text,
    ).ratio()

    if token_overlap < 0.70:
        return 0.0

    return sequence_similarity


def classify_barge_in(
    transcript: object,
    *,
    spoken_text: object = "",
) -> BargeInDecision:
    """Classify speech captured while Avens is speaking.

    Unknown or ambiguous speech defaults to UNCLEAR so runtime logic can
    cautiously resume rather than discarding the paused response.
    """

    normalised = normalise_barge_text(transcript)
    normalised_spoken = normalise_barge_text(spoken_text)

    if not normalised:
        return BargeInDecision(
            intent=BargeInIntent.UNCLEAR,
            reason="empty_transcript",
            confidence=0.0,
        )

    if any(
        re.search(pattern, normalised)
        for pattern in DIRECT_ADDRESS_PATTERNS
    ):
        return BargeInDecision(
            intent=BargeInIntent.DIRECTED,
            reason="direct_address",
            confidence=0.98,
        )

    if normalised.startswith(CORRECTION_STARTERS):
        return BargeInDecision(
            intent=BargeInIntent.DIRECTED,
            reason="correction",
            confidence=0.94,
        )

    if normalised.startswith(QUESTION_STARTERS):
        return BargeInDecision(
            intent=BargeInIntent.DIRECTED,
            reason="question",
            confidence=0.92,
        )

    if normalised.startswith(COMMAND_STARTERS):
        return BargeInDecision(
            intent=BargeInIntent.DIRECTED,
            reason="command",
            confidence=0.93,
        )

    if any(
        re.search(pattern, normalised)
        for pattern in SIDE_TALK_PATTERNS
    ):
        return BargeInDecision(
            intent=BargeInIntent.BACKGROUND,
            reason="side_talk_pattern",
            confidence=0.90,
        )

    if normalised in ACKNOWLEDGEMENT_PHRASES:
        return BargeInDecision(
            intent=BargeInIntent.ACKNOWLEDGEMENT,
            reason="short_acknowledgement",
            confidence=0.91,
        )

    echo_similarity = _echo_similarity(
        normalised,
        normalised_spoken,
    )

    if echo_similarity >= 0.82:
        return BargeInDecision(
            intent=BargeInIntent.ECHO,
            reason="spoken_text_similarity",
            confidence=min(0.99, echo_similarity),
        )

    return BargeInDecision(
        intent=BargeInIntent.UNCLEAR,
        reason="no_confident_match",
        confidence=0.35,
    )