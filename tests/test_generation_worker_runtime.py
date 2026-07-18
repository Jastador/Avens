from __future__ import annotations

import unittest
from threading import Event
from core.generation_cancel import (
    GenerationCancellationController,
)
from core.generation_cancel_runtime import (
    create_managed_generation_worker,
    iter_background_generation,
)


class ManagedGenerationWorkerTests(
    unittest.TestCase
):
    def test_factory_returns_unstarted_worker(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        worker = (
            create_managed_generation_worker(
                controller,
                lambda prompt, **kwargs: iter(
                    [("text", prompt)]
                ),
                "Hello",
            )
        )

        self.assertFalse(
            worker.has_started
        )
        self.assertEqual(
            worker.thread_name,
            "avens-managed-generation",
        )
        self.assertEqual(
            worker.queue_capacity,
            1,
        )

    def test_custom_thread_name_is_preserved(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        worker = (
            create_managed_generation_worker(
                controller,
                lambda prompt, **kwargs: iter(()),
                "Hello",
                thread_name=(
                    "custom-generation-thread"
                ),
            )
        )

        self.assertEqual(
            worker.thread_name,
            "custom-generation-thread",
        )

    def test_worker_forwards_cancellation_token(
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

        worker = (
            create_managed_generation_worker(
                controller,
                stream_factory,
                "Test prompt",
            )
        )

        worker.start()

        events = list(
            worker.iter_events(
                poll_timeout=0.01
            )
        )

        items = [
            event.item
            for event in events
            if event.is_item
        ]

        self.assertEqual(
            items,
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

    def test_controller_clears_after_worker_completion(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        worker = (
            create_managed_generation_worker(
                controller,
                lambda prompt, **kwargs: iter(
                    [("text", prompt)]
                ),
                "Hello",
            )
        )

        worker.start()

        list(
            worker.iter_events(
                poll_timeout=0.01
            )
        )

        self.assertFalse(
            controller.has_active_generation
        )

    def test_background_iterator_yields_items_in_order(
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
            yield (
                "text",
                f"{prompt} one",
            )
            yield (
                "text",
                f"{prompt} two",
            )

        items = list(
            iter_background_generation(
                controller,
                stream_factory,
                "Answer",
                poll_timeout=0.01,
            )
        )

        self.assertEqual(
            items,
            [
                (
                    "text",
                    "Answer one",
                ),
                (
                    "text",
                    "Answer two",
                ),
            ],
        )
        self.assertFalse(
            controller.has_active_generation
        )

    def test_background_iterator_propagates_error(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        def failing_stream(
            prompt,
            *,
            cancellation_token,
        ):
            yield ("text", prompt)
            raise RuntimeError(
                "background generation failed"
            )

        iterator = iter_background_generation(
            controller,
            failing_stream,
            "Hello",
            poll_timeout=0.01,
        )

        self.assertEqual(
            next(iterator),
            ("text", "Hello"),
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "background generation failed",
        ):
            next(iterator)

        self.assertFalse(
            controller.has_active_generation
        )

    def test_closing_background_iterator_stops_worker(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )
        stream_closed = Event()

        def endless_stream(
            prompt,
            *,
            cancellation_token,
        ):
            del prompt
            del cancellation_token

            try:
                index = 0

                while True:
                    yield (
                        "text",
                        str(index),
                    )
                    index += 1
            finally:
                stream_closed.set()

        iterator = iter_background_generation(
            controller,
            endless_stream,
            "Hello",
            poll_timeout=0.01,
            queue_capacity=1,
        )

        first_item = next(iterator)

        self.assertEqual(
            first_item,
            ("text", "0"),
        )

        iterator.close()

        self.assertTrue(
            stream_closed.wait(timeout=1.0)
        )
        self.assertFalse(
            controller.has_active_generation
        )

    def test_cancelled_stream_stops_producing_items(
        self,
    ):
        controller = (
            GenerationCancellationController()
        )

        def cancellable_stream(
            prompt,
            *,
            cancellation_token,
        ):
            yield ("text", "First")

            cancellation_token.cancel(
                "test cancellation"
            )

            if cancellation_token.is_cancelled:
                return

            yield ("text", "Second")

        items = list(
            iter_background_generation(
                controller,
                cancellable_stream,
                "Hello",
                poll_timeout=0.01,
            )
        )

        self.assertEqual(
            items,
            [
                ("text", "First"),
            ],
        )
        self.assertFalse(
            controller.has_active_generation
        )


if __name__ == "__main__":
    unittest.main()