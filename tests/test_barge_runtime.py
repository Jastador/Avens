from __future__ import annotations

import unittest

from core.barge_intent import (
    BargeInIntent,
)
from core.barge_runtime import (
    BargeRuntimeAction,
    BargeRuntimeResolution,
    consume_queued_barge_action,
    queue_barge_resolution,
    read_barge_resolution,
    wait_for_barge_capture,
    wait_for_barge_resolution,
)


class FinishedThread:
    def is_alive(self) -> bool:
        return False

    def join(
        self,
        timeout=None,
    ) -> None:
        raise AssertionError(
            "A finished thread should not be joined."
        )

class CaptureProgressThread:
    def __init__(
        self,
        shared_state,
    ) -> None:
        self.shared_state = shared_state
        self.join_calls = 0

    def is_alive(self) -> bool:
        return True

    def join(
        self,
        timeout=None,
    ) -> None:
        del timeout

        self.join_calls += 1
        self.shared_state[
            "barge_in_status"
        ] = "captured"

class BargeRuntimeTests(
    unittest.TestCase
):
    def test_no_interrupt_has_no_action(
        self,
    ):
        result = read_barge_resolution(
            {
                "interrupt": False,
            }
        )

        self.assertEqual(
            result.action,
            BargeRuntimeAction.NONE,
        )
        self.assertFalse(
            result.has_action
        )

    def test_directed_transcript_becomes_input(
        self,
    ):
        result = read_barge_resolution(
            {
                "interrupt": True,
                "barge_in_ready": True,
                "barge_in_transcript": (
                    "Wait, what does that mean?"
                ),
                "barge_in_intent": "directed",
                "barge_in_reason": "question",
                "barge_in_confidence": 0.92,
            }
        )

        self.assertEqual(
            result.action,
            BargeRuntimeAction.DIRECTED,
        )
        self.assertEqual(
            result.transcript,
            "Wait, what does that mean?",
        )

    def test_directed_without_transcript_resumes(
        self,
    ):
        result = read_barge_resolution(
            {
                "interrupt": True,
                "barge_in_ready": True,
                "barge_in_transcript": "",
                "barge_in_intent": "directed",
            }
        )

        self.assertEqual(
            result.action,
            BargeRuntimeAction.RESUME,
        )

    def test_acknowledgement_resumes(
        self,
    ):
        result = read_barge_resolution(
            {
                "interrupt": True,
                "barge_in_ready": True,
                "barge_in_transcript": "Hmm.",
                "barge_in_intent": (
                    "acknowledgement"
                ),
            }
        )

        self.assertEqual(
            result.action,
            BargeRuntimeAction.RESUME,
        )
        self.assertEqual(
            result.intent,
            BargeInIntent.ACKNOWLEDGEMENT,
        )

    def test_unknown_intent_resumes_safely(
        self,
    ):
        result = read_barge_resolution(
            {
                "interrupt": True,
                "barge_in_ready": True,
                "barge_in_transcript": (
                    "unrecognised noise"
                ),
                "barge_in_intent": (
                    "not-a-real-intent"
                ),
            }
        )

        self.assertEqual(
            result.action,
            BargeRuntimeAction.RESUME,
        )
        self.assertEqual(
            result.intent,
            BargeInIntent.UNCLEAR,
        )

    def test_confidence_is_clamped(
        self,
    ):
        result = read_barge_resolution(
            {
                "interrupt": True,
                "barge_in_ready": True,
                "barge_in_transcript": "Avens stop",
                "barge_in_intent": "directed",
                "barge_in_confidence": 4.5,
            }
        )

        self.assertEqual(
            result.confidence,
            1.0,
        )

    def test_directed_resolution_is_queued(
        self,
    ):
        shared_state = {
            "paused_response": (
                "The unfinished answer."
            ),
        }

        resolution = BargeRuntimeResolution(
            action=(
                BargeRuntimeAction.DIRECTED
            ),
            transcript="Open Discord.",
            intent=BargeInIntent.DIRECTED,
            reason="command",
            confidence=0.93,
        )

        queue_barge_resolution(
            shared_state,
            resolution,
        )

        self.assertEqual(
            shared_state[
                "pending_barge_input"
            ],
            "Open Discord.",
        )
        self.assertFalse(
            shared_state[
                "auto_resume_paused_response"
            ]
        )
        self.assertEqual(
            shared_state[
                "pending_barge_action"
            ],
            "directed",
        )
        self.assertEqual(
            shared_state[
                "pending_barge_intent"
            ],
            "directed",
        )
        self.assertEqual(
            shared_state[
                "pending_barge_reason"
            ],
            "command",
        )
        self.assertEqual(
            shared_state[
                "pending_barge_confidence"
            ],
            0.93,
        )

    def test_resume_is_queued_when_response_exists(
        self,
    ):
        shared_state = {
            "paused_response": (
                "Continue this response."
            ),
        }

        resolution = BargeRuntimeResolution(
            action=BargeRuntimeAction.RESUME,
            transcript="Hmm.",
            intent=(
                BargeInIntent.ACKNOWLEDGEMENT
            ),
            reason="short_acknowledgement",
            confidence=0.91,
        )

        queue_barge_resolution(
            shared_state,
            resolution,
        )

        self.assertTrue(
            shared_state[
                "auto_resume_paused_response"
            ]
        )
        self.assertEqual(
            shared_state[
                "pending_barge_input"
            ],
            "",
        )

    def test_resume_without_paused_text_is_not_queued(
        self,
    ):
        shared_state = {
            "paused_response": "",
        }

        resolution = BargeRuntimeResolution(
            action=BargeRuntimeAction.RESUME,
            transcript="",
            intent=BargeInIntent.UNCLEAR,
            reason="empty_transcript",
            confidence=0.0,
        )

        queue_barge_resolution(
            shared_state,
            resolution,
        )

        self.assertFalse(
            shared_state[
                "auto_resume_paused_response"
            ]
        )

    def test_consume_returns_and_clears_action(
        self,
    ):
        shared_state = {
            "pending_barge_input": (
                "  What do you mean?  "
            ),
            "auto_resume_paused_response": (
                False
            ),
            "pending_barge_action": (
                "directed"
            ),
            "pending_barge_intent": (
                "directed"
            ),
            "pending_barge_reason": (
                "question"
            ),
            "pending_barge_confidence": (
                0.92
            ),
        }

        queued = consume_queued_barge_action(
            shared_state
        )

        self.assertEqual(
            queued.transcript,
            "What do you mean?",
        )
        self.assertTrue(
            queued.has_directed_input
        )
        self.assertEqual(
            queued.action,
            BargeRuntimeAction.DIRECTED,
        )
        self.assertEqual(
            queued.intent,
            BargeInIntent.DIRECTED,
        )
        self.assertEqual(
            queued.reason,
            "question",
        )
        self.assertEqual(
            queued.confidence,
            0.92,
        )
        self.assertEqual(
            shared_state[
                "pending_barge_input"
            ],
            "",
        )
        self.assertFalse(
            shared_state[
                "auto_resume_paused_response"
            ]
        )
        self.assertEqual(
            shared_state[
                "pending_barge_action"
            ],
            "",
        )
        self.assertEqual(
            shared_state[
                "pending_barge_intent"
            ],
            "",
        )
        self.assertEqual(
            shared_state[
                "pending_barge_reason"
            ],
            "",
        )
        self.assertEqual(
            shared_state[
                "pending_barge_confidence"
            ],
            0.0,
        )

    def test_finished_listener_can_be_resolved(
        self,
    ):
        result = wait_for_barge_resolution(
            {
                "interrupt": True,
                "barge_in_ready": True,
                "barge_in_transcript": "Okay.",
                "barge_in_intent": (
                    "acknowledgement"
                ),
            },
            FinishedThread(),
        )

        self.assertEqual(
            result.action,
            BargeRuntimeAction.RESUME,
        )

    def test_existing_capture_status_returns_immediately(
        self,
    ):
        result = wait_for_barge_capture(
            {
                "barge_in_status": (
                    "captured"
                ),
            },
            FinishedThread(),
        )

        self.assertEqual(
            result,
            "captured",
        )

    def test_wait_for_capture_polls_until_captured(
        self,
    ):
        shared_state = {
            "barge_in_status": (
                "capturing"
            ),
        }

        listener = CaptureProgressThread(
            shared_state
        )

        result = wait_for_barge_capture(
            shared_state,
            listener,
            timeout_seconds=1.0,
            poll_seconds=0.01,
        )

        self.assertEqual(
            result,
            "captured",
        )
        self.assertEqual(
            listener.join_calls,
            1,
        )

    def test_capture_wait_rejects_invalid_timeout(
        self,
    ):
        with self.assertRaises(ValueError):
            wait_for_barge_capture(
                {},
                FinishedThread(),
                timeout_seconds=0.0,
            )

    def test_capture_wait_rejects_invalid_poll_interval(
        self,
    ):
        with self.assertRaises(ValueError):
            wait_for_barge_capture(
                {},
                FinishedThread(),
                poll_seconds=0.0,
            )

if __name__ == "__main__":
    unittest.main()