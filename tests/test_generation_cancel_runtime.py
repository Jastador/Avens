from __future__ import annotations

import unittest
from threading import Thread
from time import sleep
from core.generation_cancel import (
    GenerationCancellationController,
)
from core.generation_cancel_runtime import (
    cancel_generation_from_shared_state,
    iter_managed_generation,
    should_cancel_generation_for_voiced_speech,
    wait_for_generation_idle_from_shared_state,
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

class GenerationIdleWaitTests(
    unittest.TestCase
):
    def test_missing_controller_returns_false(
        self,
    ):
        result = (
            wait_for_generation_idle_from_shared_state(
                {},
                timeout_seconds=0.1,
                poll_seconds=0.01,
            )
        )

        self.assertFalse(result)

    def test_idle_controller_returns_true(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        result = (
            wait_for_generation_idle_from_shared_state(
                {
                    "generation_cancel_controller": (
                        controller
                    ),
                },
                timeout_seconds=0.1,
                poll_seconds=0.01,
            )
        )

        self.assertTrue(result)

    def test_wait_returns_after_generation_finishes(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        token = controller.begin_generation()

        def finish_generation():
            sleep(0.05)
            controller.finish_generation(token)

        thread = Thread(
            target=finish_generation,
            daemon=True,
        )
        thread.start()

        result = (
            wait_for_generation_idle_from_shared_state(
                {
                    "generation_cancel_controller": (
                        controller
                    ),
                },
                timeout_seconds=1.0,
                poll_seconds=0.01,
            )
        )

        thread.join(timeout=1.0)

        self.assertTrue(result)
        self.assertFalse(
            controller.has_active_generation
        )

    def test_active_generation_timeout_returns_false(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        controller.begin_generation()

        result = (
            wait_for_generation_idle_from_shared_state(
                {
                    "generation_cancel_controller": (
                        controller
                    ),
                },
                timeout_seconds=0.05,
                poll_seconds=0.01,
            )
        )

        self.assertFalse(result)

    def test_invalid_wait_values_are_rejected(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        shared_state = {
            "generation_cancel_controller": (
                controller
            ),
        }

        with self.assertRaises(ValueError):
            wait_for_generation_idle_from_shared_state(
                shared_state,
                timeout_seconds=0.0,
            )

        with self.assertRaises(ValueError):
            wait_for_generation_idle_from_shared_state(
                shared_state,
                poll_seconds=0.0,
            )

if __name__ == "__main__":
    unittest.main()