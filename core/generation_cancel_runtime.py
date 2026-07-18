from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Any

from core.generation_cancel import (
    GenerationCancellationController,
)
from core.generation_worker import (
    GenerationWorker,
)

DEFAULT_MINIMUM_VOICED_SECONDS = 0.55


def should_cancel_generation_for_voiced_speech(
    voiced_blocks: object,
    *,
    block_duration_seconds: float,
    minimum_voiced_seconds: float = (
        DEFAULT_MINIMUM_VOICED_SECONDS
    ),
) -> bool:
    """Return whether speech is long enough to cancel generation.

    Short sounds and acknowledgements receive a grace window. Longer
    utterances cancel the active response without waiting for STT.
    """

    if block_duration_seconds <= 0:
        raise ValueError(
            "block_duration_seconds must be positive."
        )

    if minimum_voiced_seconds <= 0:
        raise ValueError(
            "minimum_voiced_seconds must be positive."
        )

    try:
        block_count = int(voiced_blocks)
    except (TypeError, ValueError):
        return False

    if block_count < 1:
        return False

    voiced_seconds = (
        block_count * block_duration_seconds
    )

    return (
        voiced_seconds
        >= minimum_voiced_seconds
    )

def iter_managed_generation(
    controller: GenerationCancellationController,
    stream_factory: Callable[..., Any],
    prompt: str,
) -> Iterator[tuple[str, str]]:
    """Run one response stream under a managed cancellation token."""

    token = controller.begin_generation()

    try:
        stream = stream_factory(
            prompt,
            cancellation_token=token,
        )

        yield from stream

    finally:
        controller.finish_generation(token)

def create_managed_generation_worker(
    controller: GenerationCancellationController,
    stream_factory: Callable[..., Any],
    prompt: str,
    *,
    thread_name: str = (
        "avens-managed-generation"
    ),
    queue_capacity: int = 1,
) -> GenerationWorker:
    """Create an unstarted worker for one managed brain stream."""

    return GenerationWorker(
        stream_factory=lambda: (
            iter_managed_generation(
                controller,
                stream_factory,
                prompt,
            )
        ),
        thread_name=thread_name,
        queue_capacity=queue_capacity,
    )


def iter_background_generation(
    controller: GenerationCancellationController,
    stream_factory: Callable[..., Any],
    prompt: str,
    *,
    poll_timeout: float = 0.05,
    queue_capacity: int = 1,
) -> Iterator[tuple[str, str]]:
    """Yield generation items produced by a background worker.

    Producer errors are raised in the consumer thread so existing runtime
    error handling can continue to behave normally.
    """

    worker = create_managed_generation_worker(
        controller,
        stream_factory,
        prompt,
        queue_capacity=queue_capacity,
    )

    worker.start()

    try:
        for event in worker.iter_events(
            poll_timeout=poll_timeout,
        ):
            if event.is_item:
                yield event.item
                continue

            if event.is_error:
                error = event.error

                if error is None:
                    raise RuntimeError(
                        "Generation worker emitted "
                        "an error event without an error."
                    )

                raise error

    finally:
        worker.request_stop()
        worker.join(timeout=1.0)

def cancel_generation_from_shared_state(
    shared_state,
    *,
    reason: object,
) -> bool:
    """Cancel the active brain generation stored in shared state."""

    controller = shared_state.get(
        "generation_cancel_controller"
    )

    if not isinstance(
        controller,
        GenerationCancellationController,
    ):
        return False

    return controller.cancel_active(reason)

def wait_for_generation_idle_from_shared_state(
    shared_state,
    *,
    timeout_seconds: float = 2.0,
    poll_seconds: float = 0.02,
) -> bool:
    """Wait until the shared generation controller has no active stream.

    Returns ``True`` when generation is idle. Returns ``False`` when the
    controller is missing or the timeout expires.
    """

    if timeout_seconds <= 0:
        raise ValueError(
            "timeout_seconds must be positive."
        )

    if poll_seconds <= 0:
        raise ValueError(
            "poll_seconds must be positive."
        )

    controller = shared_state.get(
        "generation_cancel_controller"
    )

    if not isinstance(
        controller,
        GenerationCancellationController,
    ):
        return False

    deadline = (
        time.monotonic()
        + timeout_seconds
    )

    while controller.has_active_generation:
        remaining = (
            deadline
            - time.monotonic()
        )

        if remaining <= 0:
            return False

        time.sleep(
            min(
                poll_seconds,
                remaining,
            )
        )

    return True