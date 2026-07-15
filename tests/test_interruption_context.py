from __future__ import annotations

import unittest

from core.interruption_context import (
    InterruptedResponse,
    InterruptionContextStack,
)


class InterruptionContextStackTests(
    unittest.TestCase
):
    def test_new_stack_is_empty(self):
        stack = InterruptionContextStack()

        self.assertTrue(stack.is_empty)
        self.assertFalse(stack.can_resume)
        self.assertEqual(stack.depth, 0)
        self.assertIsNone(stack.current)

    def test_push_stores_response(self):
        stack = InterruptionContextStack()

        frame = stack.push(
            "The unfinished explanation.",
            interrupted_by=(
                "What does that mean?"
            ),
        )

        self.assertIsInstance(
            frame,
            InterruptedResponse,
        )
        self.assertEqual(stack.depth, 1)
        self.assertTrue(stack.can_resume)
        self.assertEqual(
            frame.response_text,
            "The unfinished explanation.",
        )
        self.assertEqual(
            frame.interrupted_by,
            "What does that mean?",
        )
        self.assertEqual(frame.depth, 1)

    def test_push_normalizes_whitespace(self):
        stack = InterruptionContextStack()

        frame = stack.push(
            "  One   unfinished\nresponse. ",
            interrupted_by=(
                "  Explain   that. "
            ),
        )

        self.assertEqual(
            frame.response_text,
            "One unfinished response.",
        )
        self.assertEqual(
            frame.interrupted_by,
            "Explain that.",
        )

    def test_empty_response_is_ignored(self):
        stack = InterruptionContextStack()

        frame = stack.push(
            "   ",
            interrupted_by="Why?",
        )

        self.assertIsNone(frame)
        self.assertTrue(stack.is_empty)

    def test_nested_responses_are_lifo(self):
        stack = InterruptionContextStack()

        stack.push(
            "Original explanation.",
            interrupted_by=(
                "First clarification."
            ),
        )

        stack.push(
            "Clarification answer.",
            interrupted_by=(
                "Second clarification."
            ),
        )

        self.assertEqual(stack.depth, 2)
        self.assertEqual(
            stack.peek().response_text,
            "Clarification answer.",
        )

        first = stack.pop()
        second = stack.pop()

        self.assertEqual(
            first.response_text,
            "Clarification answer.",
        )
        self.assertEqual(
            second.response_text,
            "Original explanation.",
        )
        self.assertTrue(stack.is_empty)

    def test_peek_does_not_remove_frame(self):
        stack = InterruptionContextStack()

        stack.push(
            "Keep this response.",
            interrupted_by="Question.",
        )

        first = stack.peek()
        second = stack.peek()

        self.assertEqual(first, second)
        self.assertEqual(stack.depth, 1)

    def test_pop_empty_stack_returns_none(self):
        stack = InterruptionContextStack()

        self.assertIsNone(stack.pop())
        self.assertIsNone(
            stack.discard_current()
        )

    def test_discard_current_removes_latest_frame(
        self,
    ):
        stack = InterruptionContextStack()

        stack.push(
            "First response.",
            interrupted_by="First question.",
        )

        stack.push(
            "Second response.",
            interrupted_by="Second question.",
        )

        removed = stack.discard_current()

        self.assertEqual(
            removed.response_text,
            "Second response.",
        )
        self.assertEqual(stack.depth, 1)
        self.assertEqual(
            stack.current.response_text,
            "First response.",
        )

    def test_clear_returns_removed_frames(self):
        stack = InterruptionContextStack()

        stack.push(
            "First response.",
            interrupted_by="First question.",
        )

        stack.push(
            "Second response.",
            interrupted_by="Second question.",
        )

        removed = stack.clear()

        self.assertEqual(len(removed), 2)
        self.assertTrue(stack.is_empty)

    def test_maximum_depth_discards_oldest_frame(
        self,
    ):
        stack = InterruptionContextStack(
            maximum_depth=2,
        )

        stack.push(
            "Oldest response.",
            interrupted_by="Question one.",
        )

        stack.push(
            "Middle response.",
            interrupted_by="Question two.",
        )

        newest = stack.push(
            "Newest response.",
            interrupted_by="Question three.",
        )

        self.assertEqual(stack.depth, 2)
        self.assertEqual(
            stack.frames[0].response_text,
            "Middle response.",
        )
        self.assertEqual(
            stack.frames[1].response_text,
            "Newest response.",
        )
        self.assertEqual(newest.depth, 2)

    def test_invalid_maximum_depth_is_rejected(
        self,
    ):
        with self.assertRaises(ValueError):
            InterruptionContextStack(
                maximum_depth=0,
            )


if __name__ == "__main__":
    unittest.main()