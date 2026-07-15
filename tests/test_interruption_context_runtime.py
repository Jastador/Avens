from __future__ import annotations

import unittest

from core.interruption_context import (
    InterruptionContextStack,
)
from core.interruption_context_runtime import (
    InterruptionContextCoordinator,
)


class InterruptionContextCoordinatorTests(
    unittest.TestCase
):
    def test_new_coordinator_has_no_pending_return(
        self,
    ):
        coordinator = (
            InterruptionContextCoordinator()
        )

        self.assertEqual(
            coordinator.depth,
            0,
        )
        self.assertFalse(
            coordinator.has_pending_return
        )
        self.assertIsNone(
            coordinator.current
        )

    def test_question_preserves_paused_response(
        self,
    ):
        coordinator = (
            InterruptionContextCoordinator()
        )

        update = (
            coordinator
            .handle_directed_interruption(
                paused_response=(
                    "The unfinished explanation."
                ),
                transcript=(
                    "What does that mean?"
                ),
                classification_reason=(
                    "question"
                ),
            )
        )

        self.assertTrue(
            update.preserved
        )
        self.assertFalse(
            update.replaced
        )
        self.assertEqual(
            coordinator.depth,
            1,
        )
        self.assertEqual(
            update.stored_frame.response_text,
            "The unfinished explanation.",
        )

    def test_correction_preserves_response(
        self,
    ):
        coordinator = (
            InterruptionContextCoordinator()
        )

        update = (
            coordinator
            .handle_directed_interruption(
                paused_response=(
                    "The original answer."
                ),
                transcript=(
                    "No, that is not correct."
                ),
                classification_reason=(
                    "correction"
                ),
            )
        )

        self.assertTrue(
            update.preserved
        )
        self.assertEqual(
            update.decision.reason,
            "correction",
        )

    def test_empty_paused_response_is_not_stored(
        self,
    ):
        coordinator = (
            InterruptionContextCoordinator()
        )

        update = (
            coordinator
            .handle_directed_interruption(
                paused_response="",
                transcript=(
                    "What does that mean?"
                ),
                classification_reason=(
                    "question"
                ),
            )
        )

        self.assertFalse(
            update.preserved
        )
        self.assertEqual(
            coordinator.depth,
            0,
        )

    def test_command_replaces_and_clears_context(
        self,
    ):
        coordinator = (
            InterruptionContextCoordinator()
        )

        coordinator.handle_directed_interruption(
            paused_response=(
                "Original explanation."
            ),
            transcript="What does that mean?",
            classification_reason="question",
        )

        update = (
            coordinator
            .handle_directed_interruption(
                paused_response=(
                    "Clarification answer."
                ),
                transcript="Open Discord.",
                classification_reason="command",
            )
        )

        self.assertTrue(
            update.replaced
        )
        self.assertEqual(
            update.discarded_count,
            1,
        )
        self.assertFalse(
            coordinator.has_pending_return
        )

    def test_ambiguous_request_clears_context(
        self,
    ):
        coordinator = (
            InterruptionContextCoordinator()
        )

        coordinator.handle_directed_interruption(
            paused_response=(
                "Old explanation."
            ),
            transcript="Why is that?",
            classification_reason="question",
        )

        update = (
            coordinator
            .handle_directed_interruption(
                paused_response=(
                    "Current answer."
                ),
                transcript=(
                    "The package arrived today."
                ),
            )
        )

        self.assertTrue(
            update.replaced
        )
        self.assertEqual(
            update.discarded_count,
            1,
        )
        self.assertEqual(
            coordinator.depth,
            0,
        )

    def test_nested_context_returns_lifo(
        self,
    ):
        coordinator = (
            InterruptionContextCoordinator()
        )

        coordinator.handle_directed_interruption(
            paused_response=(
                "Original explanation."
            ),
            transcript=(
                "First clarification?"
            ),
            classification_reason="question",
        )

        coordinator.handle_directed_interruption(
            paused_response=(
                "First clarification answer."
            ),
            transcript=(
                "Second clarification?"
            ),
            classification_reason="question",
        )

        first = (
            coordinator.take_next_response()
        )
        second = (
            coordinator.take_next_response()
        )

        self.assertEqual(
            first.response_text,
            "First clarification answer.",
        )
        self.assertEqual(
            second.response_text,
            "Original explanation.",
        )
        self.assertFalse(
            coordinator.has_pending_return
        )

    def test_peek_does_not_remove_response(
        self,
    ):
        coordinator = (
            InterruptionContextCoordinator()
        )

        coordinator.handle_directed_interruption(
            paused_response=(
                "Keep this response."
            ),
            transcript="Why?",
            classification_reason="question",
        )

        frame = (
            coordinator.peek_next_response()
        )

        self.assertEqual(
            frame.response_text,
            "Keep this response.",
        )
        self.assertEqual(
            coordinator.depth,
            1,
        )

    def test_custom_stack_depth_is_respected(
        self,
    ):
        coordinator = (
            InterruptionContextCoordinator(
                stack=InterruptionContextStack(
                    maximum_depth=2,
                )
            )
        )

        for index in range(3):
            coordinator.handle_directed_interruption(
                paused_response=(
                    f"Response {index}."
                ),
                transcript=(
                    f"Why {index}?"
                ),
                classification_reason=(
                    "question"
                ),
            )

        self.assertEqual(
            coordinator.depth,
            2,
        )
        self.assertEqual(
            coordinator.stack.frames[
                0
            ].response_text,
            "Response 1.",
        )
        self.assertEqual(
            coordinator.stack.frames[
                1
            ].response_text,
            "Response 2.",
        )


if __name__ == "__main__":
    unittest.main()