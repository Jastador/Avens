"""Thread-safe, memory-only handoff for the newest webcam frame.

The frame is never written to disk. While Vision is running, this buffer keeps
only one recent BGR image in RAM and overwrites it whenever a new frame arrives.
When the camera stops, clear() removes that in-memory copy.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np


class LiveFrameBuffer:
    """Share one recent camera frame safely across worker threads."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._frame: Optional[np.ndarray] = None
        self._captured_at = 0.0

    def publish(self, frame: np.ndarray) -> None:
        """Replace the old frame with a private in-memory copy."""
        with self._condition:
            self._frame = frame.copy()
            self._captured_at = time.monotonic()
            self._condition.notify_all()

    def get_latest(
        self,
        max_age_seconds: float = 2.0,
    ) -> Optional[np.ndarray]:
        """Return a safe copy only when the current frame is recent."""
        with self._condition:
            if self._frame is None:
                return None

            age = time.monotonic() - self._captured_at

            if age > max_age_seconds:
                return None

            return self._frame.copy()

    def wait_for_frame(
        self,
        timeout_seconds: float = 5.0,
        newer_than: float = 0.0,
    ) -> Optional[np.ndarray]:
        """Wait for a fresh frame, then return a safe copy."""
        deadline = time.monotonic() + timeout_seconds

        with self._condition:
            while True:
                has_fresh_frame = (
                    self._frame is not None
                    and self._captured_at > newer_than
                )

                if has_fresh_frame:
                    return self._frame.copy()

                remaining = deadline - time.monotonic()

                if remaining <= 0:
                    return None

                self._condition.wait(timeout=remaining)

    def clear(self) -> None:
        """Discard the in-memory frame when camera capture stops."""
        with self._condition:
            self._frame = None
            self._captured_at = 0.0


live_frame_buffer = LiveFrameBuffer()