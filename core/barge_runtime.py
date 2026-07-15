from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

from core.barge_intent import BargeInIntent


class BargeRuntimeAction(str, Enum):
    """Action the voice loop should take after classification."""

    NONE = "none"
    DIRECTED = "directed"
    RESUME = "resume"


@dataclass(frozen=True)
class BargeRuntimeResolution:
    """Runtime interpretation of one completed barge-in capture."""

    action: BargeRuntimeAction
    transcript: str
    intent: BargeInIntent | None
    reason: str
    confidence: float

    @property
    def has_action(self) -> bool:
        return self.action is not BargeRuntimeAction.NONE


@dataclass(frozen=True)
class QueuedBargeAction:
    """One classified action consumed by the voice loop."""

    transcript: str
    auto_resume: bool
    action: BargeRuntimeAction
    intent: BargeInIntent | None
    reason: str
    confidence: float

    @property
    def has_directed_input(self) -> bool:
        return bool(self.transcript)


def _normalise_transcript(
    value: object,
) -> str:
    if not isinstance(value, str):
        return ""

    return " ".join(value.split())


def _coerce_confidence(
    value: object,
) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0

    return max(
        0.0,
        min(1.0, confidence),
    )

def _coerce_action(
    value: object,
) -> BargeRuntimeAction:
    try:
        return BargeRuntimeAction(
            str(value).strip().casefold()
        )
    except ValueError:
        return BargeRuntimeAction.NONE

def _coerce_intent(
    value: object,
) -> BargeInIntent | None:
    try:
        return BargeInIntent(
            str(value).strip().casefold()
        )
    except ValueError:
        return None


def read_barge_resolution(
    shared_state,
) -> BargeRuntimeResolution:
    """Read the latest classified interruption from shared state.

    An interruption without a usable directed transcript defaults to
    RESUME. This protects the paused answer from noise, echo, incomplete
    decoding, and classifier failures.
    """

    if not shared_state.get(
        "interrupt",
        False,
    ):
        return BargeRuntimeResolution(
            action=BargeRuntimeAction.NONE,
            transcript="",
            intent=None,
            reason="no_interrupt",
            confidence=0.0,
        )

    transcript = _normalise_transcript(
        shared_state.get(
            "barge_in_transcript",
            "",
        )
    )

    intent = _coerce_intent(
        shared_state.get(
            "barge_in_intent",
            "",
        )
    )

    reason = str(
        shared_state.get(
            "barge_in_reason",
            "",
        )
    ).strip()

    confidence = _coerce_confidence(
        shared_state.get(
            "barge_in_confidence",
            0.0,
        )
    )

    result_ready = bool(
        shared_state.get(
            "barge_in_ready",
            False,
        )
    )

    if (
        result_ready
        and intent is BargeInIntent.DIRECTED
        and transcript
    ):
        return BargeRuntimeResolution(
            action=BargeRuntimeAction.DIRECTED,
            transcript=transcript,
            intent=intent,
            reason=reason or "directed_transcript",
            confidence=confidence,
        )

    return BargeRuntimeResolution(
        action=BargeRuntimeAction.RESUME,
        transcript=transcript,
        intent=(
            intent
            if intent is not None
            else BargeInIntent.UNCLEAR
        ),
        reason=reason or "safe_resume_fallback",
        confidence=confidence,
    )


def wait_for_barge_resolution(
    shared_state,
    listener_thread,
    *,
    timeout_seconds: float = 12.0,
    poll_seconds: float = 0.05,
) -> BargeRuntimeResolution:
    """Wait briefly for capture and classification to finish."""

    if timeout_seconds <= 0:
        raise ValueError(
            "timeout_seconds must be positive."
        )

    if poll_seconds <= 0:
        raise ValueError(
            "poll_seconds must be positive."
        )

    deadline = (
        time.monotonic() + timeout_seconds
    )

    while listener_thread.is_alive():
        if shared_state.get(
            "barge_in_ready",
            False,
        ):
            break

        remaining = deadline - time.monotonic()

        if remaining <= 0:
            break

        listener_thread.join(
            timeout=min(
                poll_seconds,
                remaining,
            )
        )

    return read_barge_resolution(
        shared_state
    )


def queue_barge_resolution(
    shared_state,
    resolution: BargeRuntimeResolution,
) -> None:
    """Queue one resolved action for the next loop iteration."""

    if (
        resolution.action
        is BargeRuntimeAction.NONE
    ):
        return

    shared_state["pending_barge_input"] = ""
    shared_state[
        "auto_resume_paused_response"
    ] = False

    shared_state["pending_barge_action"] = (
        resolution.action.value
    )
    shared_state["pending_barge_intent"] = (
        resolution.intent.value
        if resolution.intent is not None
        else ""
    )
    shared_state["pending_barge_reason"] = (
        resolution.reason
    )
    shared_state[
        "pending_barge_confidence"
    ] = resolution.confidence

    if (
        resolution.action
        is BargeRuntimeAction.DIRECTED
    ):
        shared_state["pending_barge_input"] = (
            resolution.transcript
        )

    elif (
        resolution.action
        is BargeRuntimeAction.RESUME
    ):
        paused_response = _normalise_transcript(
            shared_state.get(
                "paused_response",
                "",
            )
        )

        shared_state[
            "auto_resume_paused_response"
        ] = bool(paused_response)

    shared_state["last_barge_action"] = (
        resolution.action.value
    )
    shared_state["last_barge_intent"] = (
        resolution.intent.value
        if resolution.intent is not None
        else ""
    )


def consume_queued_barge_action(
    shared_state,
) -> QueuedBargeAction:
    """Read and clear one queued classified barge action."""

    transcript = _normalise_transcript(
        shared_state.get(
            "pending_barge_input",
            "",
        )
    )

    auto_resume = bool(
        shared_state.get(
            "auto_resume_paused_response",
            False,
        )
    )

    action = _coerce_action(
        shared_state.get(
            "pending_barge_action",
            "",
        )
    )

    intent = _coerce_intent(
        shared_state.get(
            "pending_barge_intent",
            "",
        )
    )

    reason = str(
        shared_state.get(
            "pending_barge_reason",
            "",
        )
    ).strip()

    confidence = _coerce_confidence(
        shared_state.get(
            "pending_barge_confidence",
            0.0,
        )
    )

    shared_state["pending_barge_input"] = ""
    shared_state[
        "auto_resume_paused_response"
    ] = False
    shared_state["pending_barge_action"] = ""
    shared_state["pending_barge_intent"] = ""
    shared_state["pending_barge_reason"] = ""
    shared_state[
        "pending_barge_confidence"
    ] = 0.0

    return QueuedBargeAction(
        transcript=transcript,
        auto_resume=auto_resume,
        action=action,
        intent=intent,
        reason=reason,
        confidence=confidence,
    )