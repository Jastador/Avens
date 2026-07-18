from __future__ import annotations

from collections.abc import (
    Callable,
    Iterable,
    Iterator,
)
from dataclasses import dataclass, field
from enum import Enum
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from typing import Any


class GenerationWorkerEventType(str, Enum):
    """Events emitted by one background generation worker."""

    ITEM = "item"
    ERROR = "error"
    COMPLETE = "complete"


@dataclass(frozen=True)
class GenerationWorkerEvent:
    """One event passed from the producer thread to the consumer."""

    event_type: GenerationWorkerEventType
    item: Any = None
    error: BaseException | None = None

    @property
    def is_item(self) -> bool:
        return (
            self.event_type
            is GenerationWorkerEventType.ITEM
        )

    @property
    def is_error(self) -> bool:
        return (
            self.event_type
            is GenerationWorkerEventType.ERROR
        )

    @property
    def is_complete(self) -> bool:
        return (
            self.event_type
            is GenerationWorkerEventType.COMPLETE
        )


@dataclass
class GenerationWorker:
    """Produce generation events on a background thread."""

    stream_factory: Callable[
        [],
        Iterable[Any],
    ]

    thread_name: str = (
        "avens-generation-worker"
    )

    queue_capacity: int = 0

    _events: Queue[
        GenerationWorkerEvent
    ] = field(
        init=False,
        repr=False,
    )

    _stop_requested: Event = field(
        default_factory=Event,
        init=False,
        repr=False,
    )

    _finished: Event = field(
        default_factory=Event,
        init=False,
        repr=False,
    )

    _start_lock: Lock = field(
        default_factory=Lock,
        init=False,
        repr=False,
    )

    _thread: Thread | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.queue_capacity < 0:
            raise ValueError(
                "queue_capacity cannot be negative."
            )

        self._events = Queue(
            maxsize=self.queue_capacity
        )

    @property
    def has_started(self) -> bool:
        with self._start_lock:
            return self._thread is not None

    @property
    def is_finished(self) -> bool:
        return self._finished.is_set()

    @property
    def is_stop_requested(self) -> bool:
        return self._stop_requested.is_set()

    @property
    def is_alive(self) -> bool:
        with self._start_lock:
            thread = self._thread

        return (
            thread is not None
            and thread.is_alive()
        )

    def start(self) -> None:
        """Start the producer thread exactly once."""

        with self._start_lock:
            if self._thread is not None:
                raise RuntimeError(
                    "Generation worker has already started."
                )

            self._thread = Thread(
                target=self._run,
                name=self.thread_name,
                daemon=True,
            )

            self._thread.start()

    def request_stop(self) -> None:
        """Request that the producer stop publishing events."""

        self._stop_requested.set()

    def _publish_event(
        self,
        event: GenerationWorkerEvent,
    ) -> bool:
        """Publish an event while respecting bounded-queue shutdown."""

        while not self._stop_requested.is_set():
            try:
                self._events.put(
                    event,
                    timeout=0.05,
                )
                return True
            except Full:
                continue

        return False

    def _run(self) -> None:
        stream = None

        try:
            stream = iter(
                self.stream_factory()
            )

            for item in stream:
                if self._stop_requested.is_set():
                    break

                published = self._publish_event(
                    GenerationWorkerEvent(
                        event_type=(
                            GenerationWorkerEventType
                            .ITEM
                        ),
                        item=item,
                    )
                )

                if not published:
                    break

        except BaseException as error:
            self._publish_event(
                GenerationWorkerEvent(
                    event_type=(
                        GenerationWorkerEventType
                        .ERROR
                    ),
                    error=error,
                )
            )

        finally:
            if stream is not None:
                close_stream = getattr(
                    stream,
                    "close",
                    None,
                )

                if callable(close_stream):
                    try:
                        close_stream()
                    except BaseException as error:
                        self._publish_event(
                            GenerationWorkerEvent(
                                event_type=(
                                    GenerationWorkerEventType
                                    .ERROR
                                ),
                                error=error,
                            )
                        )

            self._publish_event(
                GenerationWorkerEvent(
                    event_type=(
                        GenerationWorkerEventType
                        .COMPLETE
                    ),
                )
            )

            self._finished.set()

    def next_event(
        self,
        *,
        timeout: float | None = None,
    ) -> GenerationWorkerEvent:
        """Wait for and return the next producer event."""

        if not self.has_started:
            raise RuntimeError(
                "Generation worker has not been started."
            )

        return self._events.get(
            timeout=timeout
        )

    def iter_events(
        self,
        *,
        poll_timeout: float = 0.1,
    ) -> Iterator[GenerationWorkerEvent]:
        """Yield events until the producer reports completion."""

        if poll_timeout <= 0:
            raise ValueError(
                "poll_timeout must be positive."
            )

        while True:
            try:
                event = self.next_event(
                    timeout=poll_timeout
                )
            except Empty:
                if self.is_finished:
                    return

                continue

            yield event

            if event.is_complete:
                return

    def join(
        self,
        *,
        timeout: float | None = None,
    ) -> bool:
        """Wait for the producer and return whether it finished."""

        with self._start_lock:
            thread = self._thread

        if thread is None:
            return False

        thread.join(timeout=timeout)
        return not thread.is_alive()