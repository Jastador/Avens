from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class InterruptionReturnAction(str, Enum):
    """How a directed interruption affects the paused response."""

    PRESERVE = "preserve"
    REPLACE = "replace"


@dataclass(frozen=True)
class InterruptionReturnDecision:
    """Return policy for one directed interruption."""

    action: InterruptionReturnAction
    reason: str

    @property
    def should_preserve(self) -> bool:
        return (
            self.action
            is InterruptionReturnAction.PRESERVE
        )


COMMAND_STARTERS = (
    "open ",
    "close ",
    "search ",
    "find ",
    "play ",
    "pause",
    "stop",
    "continue",
    "set ",
    "turn ",
    "switch ",
    "start ",
    "run ",
    "cancel ",
    "remind ",
    "show ",
    "go to sleep",
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

CORRECTION_STARTERS = (
    "no ",
    "nope ",
    "wait ",
    "hold on",
    "that is wrong",
    "that's wrong",
    "that is not correct",
    "that's not correct",
    "you are wrong",
    "you're wrong",
)

DIRECT_ADDRESS_PREFIXES = (
    "avens ",
    "evans ",
    "hey avens ",
    "hey evans ",
    "okay avens ",
    "listen avens ",
)


def normalise_interruption_text(
    value: object,
) -> str:
    """Normalise interruption text for deterministic policy checks."""

    cleaned = re.sub(
        r"[^a-z0-9\s']+",
        " ",
        str(value).casefold(),
    )

    return " ".join(cleaned.split())


def _remove_direct_address(
    text: str,
) -> str:
    """Remove one leading Avens address before checking intent."""

    for prefix in DIRECT_ADDRESS_PREFIXES:
        if text.startswith(prefix):
            return text[
                len(prefix):
            ].strip()

    return text


def decide_interruption_return(
    transcript: object,
    *,
    classification_reason: object = "",
) -> InterruptionReturnDecision:
    """Decide whether to return to the paused response afterward.

    Explicit commands replace the paused response. Questions and
    corrections preserve it. Ambiguous interruptions default to replacing
    it so Avens does not unexpectedly revive an unrelated old answer.
    """

    normalized = normalise_interruption_text(
        transcript
    )

    reason = normalise_interruption_text(
        classification_reason
    )

    if not normalized:
        return InterruptionReturnDecision(
            action=InterruptionReturnAction.REPLACE,
            reason="empty_transcript",
        )

    without_address = _remove_direct_address(
        normalized
    )

    if without_address.startswith(
        COMMAND_STARTERS
    ):
        return InterruptionReturnDecision(
            action=InterruptionReturnAction.REPLACE,
            reason="explicit_command",
        )

    if without_address.startswith(
        CORRECTION_STARTERS
    ):
        return InterruptionReturnDecision(
            action=InterruptionReturnAction.PRESERVE,
            reason="correction",
        )

    if without_address.startswith(
        QUESTION_STARTERS
    ):
        return InterruptionReturnDecision(
            action=InterruptionReturnAction.PRESERVE,
            reason="question",
        )

    if reason in {
        "question",
        "correction",
    }:
        return InterruptionReturnDecision(
            action=InterruptionReturnAction.PRESERVE,
            reason=reason,
        )

    return InterruptionReturnDecision(
        action=InterruptionReturnAction.REPLACE,
        reason="new_or_ambiguous_request",
    )