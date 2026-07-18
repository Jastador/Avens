from __future__ import annotations

import unittest

from core.generation_cancel import (
    GenerationCancellationController,
    GenerationCancellationToken,
)


class GenerationCancellationTokenTests(
    unittest.TestCase
):
    def test_new_token_is_not_cancelled(self):
        token = GenerationCancellationToken(
            generation_id=1
        )

        self.assertFalse(token.is_cancelled)
        self.assertEqual(token.reason, "")

    def test_invalid_generation_id_is_rejected(
        self,
    ):
        with self.assertRaises(ValueError):
            GenerationCancellationToken(
                generation_id=0
            )

    def test_cancel_sets_reason(self):
        token = GenerationCancellationToken(
            generation_id=1
        )

        changed = token.cancel(
            "directed interruption"
        )

        self.assertTrue(changed)
        self.assertTrue(token.is_cancelled)
        self.assertEqual(
            token.reason,
            "directed interruption",
        )

    def test_cancel_normalizes_reason(self):
        token = GenerationCancellationToken(
            generation_id=1
        )

        token.cancel(
            "  directed   user\nspeech  "
        )

        self.assertEqual(
            token.reason,
            "directed user speech",
        )

    def test_empty_reason_uses_default(self):
        token = GenerationCancellationToken(
            generation_id=1
        )

        token.cancel("   ")

        self.assertEqual(
            token.reason,
            "cancelled",
        )

    def test_second_cancel_preserves_first_reason(
        self,
    ):
        token = GenerationCancellationToken(
            generation_id=1
        )

        first = token.cancel(
            "first reason"
        )

        second = token.cancel(
            "second reason"
        )

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(
            token.reason,
            "first reason",
        )


class GenerationCancellationControllerTests(
    unittest.TestCase
):
    def test_new_controller_has_no_active_generation(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        self.assertFalse(
            controller.has_active_generation
        )
        self.assertIsNone(
            controller.active_token
        )
        self.assertIsNone(
            controller.active_generation_id
        )

    def test_begin_generation_activates_token(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        token = controller.begin_generation()

        self.assertTrue(
            controller.has_active_generation
        )
        self.assertIs(
            controller.active_token,
            token,
        )
        self.assertEqual(
            controller.active_generation_id,
            1,
        )

    def test_generation_ids_are_sequential(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        first = controller.begin_generation()
        second = controller.begin_generation()

        self.assertEqual(
            first.generation_id,
            1,
        )
        self.assertEqual(
            second.generation_id,
            2,
        )

    def test_new_generation_cancels_previous(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        first = controller.begin_generation()
        second = controller.begin_generation()

        self.assertTrue(first.is_cancelled)
        self.assertEqual(
            first.reason,
            "superseded_by_new_generation",
        )
        self.assertFalse(
            second.is_cancelled
        )
        self.assertIs(
            controller.active_token,
            second,
        )

    def test_cancel_active_without_generation_returns_false(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        self.assertFalse(
            controller.cancel_active(
                "directed interruption"
            )
        )

    def test_cancel_active_cancels_current_token(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        token = controller.begin_generation()

        changed = controller.cancel_active(
            "directed interruption"
        )

        self.assertTrue(changed)
        self.assertTrue(token.is_cancelled)
        self.assertEqual(
            token.reason,
            "directed interruption",
        )

    def test_finish_active_generation_clears_it(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        token = controller.begin_generation()

        cleared = (
            controller.finish_generation(
                token
            )
        )

        self.assertTrue(cleared)
        self.assertFalse(
            controller.has_active_generation
        )

    def test_stale_generation_cannot_clear_newer_token(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        first = controller.begin_generation()
        second = controller.begin_generation()

        cleared = (
            controller.finish_generation(
                first
            )
        )

        self.assertFalse(cleared)
        self.assertIs(
            controller.active_token,
            second,
        )

    def test_finished_generation_cannot_be_finished_twice(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        token = controller.begin_generation()

        first = controller.finish_generation(
            token
        )

        second = controller.finish_generation(
            token
        )

        self.assertTrue(first)
        self.assertFalse(second)


if __name__ == "__main__":
    unittest.main()