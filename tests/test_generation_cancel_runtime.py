from __future__ import annotations

import unittest

from core.generation_cancel import (
    GenerationCancellationController,
)
from core.generation_cancel_runtime import (
    cancel_generation_from_shared_state,
    iter_managed_generation,
    should_cancel_generation_for_voiced_speech,
)


class ManagedGenerationTests(
    unittest.TestCase
):
    def test_managed_stream_forwards_token(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )
        received_tokens = []

        def stream_factory(
            prompt,
            *,
            cancellation_token,
        ):
            received_tokens.append(
                cancellation_token
            )

            yield (
                "text",
                f"Response to {prompt}",
            )

        events = list(
            iter_managed_generation(
                controller,
                stream_factory,
                "Test prompt",
            )
        )

        self.assertEqual(
            events,
            [
                (
                    "text",
                    "Response to Test prompt",
                )
            ],
        )
        self.assertEqual(
            len(received_tokens),
            1,
        )
        self.assertEqual(
            received_tokens[
                0
            ].generation_id,
            1,
        )

    def test_controller_is_active_during_stream(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )
        observed_active_ids = []

        def stream_factory(
            prompt,
            *,
            cancellation_token,
        ):
            observed_active_ids.append(
                controller
                .active_generation_id
            )

            yield ("text", prompt)

        list(
            iter_managed_generation(
                controller,
                stream_factory,
                "Hello",
            )
        )

        self.assertEqual(
            observed_active_ids,
            [1],
        )

    def test_controller_is_cleared_after_stream(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        def stream_factory(
            prompt,
            *,
            cancellation_token,
        ):
            yield ("text", prompt)

        list(
            iter_managed_generation(
                controller,
                stream_factory,
                "Hello",
            )
        )

        self.assertFalse(
            controller.has_active_generation
        )

    def test_controller_is_cleared_after_error(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        def stream_factory(
            prompt,
            *,
            cancellation_token,
        ):
            yield ("text", prompt)
            raise RuntimeError(
                "stream failed"
            )

        with self.assertRaises(RuntimeError):
            list(
                iter_managed_generation(
                    controller,
                    stream_factory,
                    "Hello",
                )
            )

        self.assertFalse(
            controller.has_active_generation
        )

class VoicedSpeechCancellationPolicyTests(
    unittest.TestCase
):
    def test_short_speech_stays_within_grace(
        self,
    ):
        should_cancel = (
            should_cancel_generation_for_voiced_speech(
                10,
                block_duration_seconds=0.05,
            )
        )

        self.assertFalse(should_cancel)

    def test_sustained_speech_reaches_threshold(
        self,
    ):
        should_cancel = (
            should_cancel_generation_for_voiced_speech(
                11,
                block_duration_seconds=0.05,
            )
        )

        self.assertTrue(should_cancel)

    def test_invalid_block_count_returns_false(
        self,
    ):
        should_cancel = (
            should_cancel_generation_for_voiced_speech(
                "not-a-number",
                block_duration_seconds=0.05,
            )
        )

        self.assertFalse(should_cancel)

    def test_non_positive_block_duration_is_rejected(
        self,
    ):
        with self.assertRaises(ValueError):
            should_cancel_generation_for_voiced_speech(
                12,
                block_duration_seconds=0.0,
            )

    def test_non_positive_minimum_duration_is_rejected(
        self,
    ):
        with self.assertRaises(ValueError):
            should_cancel_generation_for_voiced_speech(
                12,
                block_duration_seconds=0.05,
                minimum_voiced_seconds=0.0,
            )

class SharedStateCancellationTests(
    unittest.TestCase
):
    def test_missing_controller_returns_false(
        self,
    ):
        changed = (
            cancel_generation_from_shared_state(
                {},
                reason=(
                    "provisional speech"
                ),
            )
        )

        self.assertFalse(changed)

    def test_shared_controller_is_cancelled(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        token = controller.begin_generation()

        changed = (
            cancel_generation_from_shared_state(
                {
                    "generation_cancel_controller": (
                        controller
                    )
                },
                reason=(
                    "provisional speech"
                ),
            )
        )

        self.assertTrue(changed)
        self.assertTrue(
            token.is_cancelled
        )
        self.assertEqual(
            token.reason,
            "provisional speech",
        )


if __name__ == "__main__":
    unittest.main()