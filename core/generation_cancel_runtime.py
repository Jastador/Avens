from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from core.generation_cancel import (
    GenerationCancellationController,
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