from __future__ import annotations

import unittest
from threading import Event
from core.generation_worker import (
    GenerationWorker,
    GenerationWorkerEventType,
)


class GenerationWorkerTests(
    unittest.TestCase
):
    def test_new_worker_has_not_started(self):
        worker = GenerationWorker(
            stream_factory=lambda: iter(())
        )

        self.assertFalse(
            worker.has_started
        )
        self.assertFalse(
            worker.is_alive
        )
        self.assertFalse(
            worker.is_finished
        )

    def test_next_event_before_start_is_rejected(
        self,
    ):
        worker = GenerationWorker(
            stream_factory=lambda: iter(())
        )

        with self.assertRaises(RuntimeError):
            worker.next_event(timeout=0.01)

    def test_worker_emits_items_in_order(self):
        worker = GenerationWorker(
            stream_factory=lambda: iter(
                [
                    ("text", "First"),
                    ("text", "Second"),
                ]
            )
        )

        worker.start()

        events = list(
            worker.iter_events(
                poll_timeout=0.01
            )
        )

        self.assertEqual(
            [
                event.event_type
                for event in events
            ],
            [
                GenerationWorkerEventType.ITEM,
                GenerationWorkerEventType.ITEM,
                GenerationWorkerEventType.COMPLETE,
            ],
        )

        self.assertEqual(
            [
                event.item
                for event in events
                if event.is_item
            ],
            [
                ("text", "First"),
                ("text", "Second"),
            ],
        )

    def test_empty_stream_emits_completion(
        self,
    ):
        worker = GenerationWorker(
            stream_factory=lambda: iter(())
        )

        worker.start()

        events = list(
            worker.iter_events(
                poll_timeout=0.01
            )
        )

        self.assertEqual(
            len(events),
            1,
        )
        self.assertTrue(
            events[0].is_complete
        )

    def test_worker_reports_stream_error(
        self,
    ):
        def failing_stream():
            yield ("text", "Before failure")
            raise RuntimeError(
                "generation failed"
            )

        worker = GenerationWorker(
            stream_factory=failing_stream
        )

        worker.start()

        events = list(
            worker.iter_events(
                poll_timeout=0.01
            )
        )

        self.assertTrue(
            events[0].is_item
        )
        self.assertTrue(
            events[1].is_error
        )
        self.assertIsInstance(
            events[1].error,
            RuntimeError,
        )
        self.assertEqual(
            str(events[1].error),
            "generation failed",
        )
        self.assertTrue(
            events[2].is_complete
        )

    def test_start_twice_is_rejected(self):
        worker = GenerationWorker(
            stream_factory=lambda: iter(())
        )

        worker.start()

        with self.assertRaises(RuntimeError):
            worker.start()

    def test_join_returns_false_before_start(
        self,
    ):
        worker = GenerationWorker(
            stream_factory=lambda: iter(())
        )

        self.assertFalse(
            worker.join(timeout=0.01)
        )

    def test_join_waits_for_completion(self):
        worker = GenerationWorker(
            stream_factory=lambda: iter(
                [
                    ("text", "Complete"),
                ]
            )
        )

        worker.start()

        joined = worker.join(
            timeout=1.0
        )

        self.assertTrue(joined)
        self.assertTrue(
            worker.is_finished
        )
        self.assertFalse(
            worker.is_alive
        )

    def test_negative_queue_capacity_is_rejected(
        self,
    ):
        with self.assertRaises(ValueError):
            GenerationWorker(
                stream_factory=lambda: iter(()),
                queue_capacity=-1,
            )

    def test_bounded_queue_applies_backpressure(
        self,
    ):
        second_created = Event()
        third_created = Event()

        def stream():
            yield "first"

            second_created.set()
            yield "second"

            third_created.set()
            yield "third"

        worker = GenerationWorker(
            stream_factory=stream,
            queue_capacity=1,
        )

        worker.start()

        self.assertTrue(
            second_created.wait(timeout=1.0)
        )

        # The producer has obtained the second item but cannot
        # request the third until queue space becomes available.
        self.assertFalse(
            third_created.wait(timeout=0.1)
        )

        first_event = worker.next_event(
            timeout=1.0
        )

        self.assertEqual(
            first_event.item,
            "first",
        )

        self.assertTrue(
            third_created.wait(timeout=1.0)
        )

        remaining_events = list(
            worker.iter_events(
                poll_timeout=0.01
            )
        )

        self.assertEqual(
            [
                event.item
                for event in remaining_events
                if event.is_item
            ],
            [
                "second",
                "third",
            ],
        )

    def test_stop_releases_blocked_producer_and_closes_stream(
        self,
    ):
        second_created = Event()
        stream_closed = Event()

        def stream():
            try:
                yield "first"

                second_created.set()
                yield "second"

                while True:
                    yield "extra"
            finally:
                stream_closed.set()

        worker = GenerationWorker(
            stream_factory=stream,
            queue_capacity=1,
        )

        worker.start()

        self.assertTrue(
            second_created.wait(timeout=1.0)
        )

        worker.request_stop()

        self.assertTrue(
            worker.join(timeout=1.0)
        )
        self.assertTrue(
            stream_closed.wait(timeout=1.0)
        )
        self.assertTrue(
            worker.is_stop_requested
        )
        self.assertTrue(
            worker.is_finished
        )

    def test_invalid_poll_timeout_is_rejected(
        self,
    ):
        worker = GenerationWorker(
            stream_factory=lambda: iter(())
        )

        worker.start()

        with self.assertRaises(ValueError):
            list(
                worker.iter_events(
                    poll_timeout=0.0
                )
            )


if __name__ == "__main__":
    unittest.main()