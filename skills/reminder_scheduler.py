from __future__ import annotations

import math
from collections.abc import Callable
from queue import Empty, Queue
from threading import Event, RLock, Thread
from typing import Final

from skills.local_reminders import (
    LocalReminder,
    LocalRemindersError,
    claim_due_reminders,
)


DEFAULT_REMINDER_POLL_INTERVAL_SECONDS: Final[float] = 1.0


class ReminderScheduler:
    """Claim due reminders in the background and queue safe deliveries."""

    def __init__(
        self,
        *,
        claim_due: Callable[[], tuple[LocalReminder, ...]] = (
            claim_due_reminders
        ),
        poll_interval_seconds: float = (
            DEFAULT_REMINDER_POLL_INTERVAL_SECONDS
        ),
        error_output: Callable[[str], None] = print,
    ) -> None:
        if (
            isinstance(poll_interval_seconds, bool)
            or not isinstance(
                poll_interval_seconds,
                (int, float),
            )
            or not math.isfinite(poll_interval_seconds)
            or poll_interval_seconds <= 0
        ):
            raise ValueError(
                "Reminder poll interval must be a positive number."
            )

        self._claim_due = claim_due
        self._poll_interval_seconds = float(
            poll_interval_seconds
        )
        self._error_output = error_output
        self._deliveries: Queue[LocalReminder] = Queue()
        self._delivery_lock = RLock()
        self._delivery_ready = Event()
        self._stop_event = Event()
        self._lock = RLock()
        self._thread: Thread | None = None

    def poll_once(self) -> tuple[LocalReminder, ...]:
        """Claim due reminders once and enqueue their deliveries."""
        try:
            due_reminders = self._claim_due()
        except LocalRemindersError as error:
            self._error_output(
                f"Local reminder scheduler error: {error}"
            )
            return ()
        except Exception as error:
            self._error_output(
                f"Unexpected reminder scheduler error: {error}"
            )
            return ()

        if (
            not isinstance(due_reminders, tuple)
            or any(
                not isinstance(reminder, LocalReminder)
                for reminder in due_reminders
            )
        ):
            self._error_output(
                "Reminder scheduler returned invalid reminder data."
            )
            return ()

        with self._delivery_lock:
            for reminder in due_reminders:
                self._deliveries.put(reminder)

            if due_reminders:
                self._delivery_ready.set()

        return due_reminders

    def drain_deliveries(self) -> tuple[LocalReminder, ...]:
        """Return all queued reminder deliveries in FIFO order."""
        deliveries: list[LocalReminder] = []

        with self._delivery_lock:
            while True:
                try:
                    deliveries.append(
                        self._deliveries.get_nowait()
                    )
                except Empty:
                    break

            if self._deliveries.empty():
                self._delivery_ready.clear()

        return tuple(deliveries)

    def has_queued_deliveries(self) -> bool:
        """Return whether due reminders are waiting for app delivery."""
        with self._delivery_lock:
            return self._delivery_ready.is_set()

    def is_running(self) -> bool:
        """Return whether the scheduler worker is currently alive."""
        with self._lock:
            return (
                self._thread is not None
                and self._thread.is_alive()
            )

    def start(self) -> bool:
        """Start the background polling worker once."""
        with self._lock:
            if (
                self._thread is not None
                and self._thread.is_alive()
            ):
                return False

            self._stop_event.clear()

            self._thread = Thread(
                target=self._run,
                name="avens-reminder-scheduler",
                daemon=True,
            )
            self._thread.start()

        return True

    def stop(
        self,
        *,
        timeout_seconds: float = 2.0,
    ) -> bool:
        """Stop the worker and return whether it ended in time."""
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(
                timeout_seconds,
                (int, float),
            )
            or not math.isfinite(timeout_seconds)
            or timeout_seconds < 0
        ):
            raise ValueError(
                "Reminder scheduler timeout must be non-negative."
            )

        with self._lock:
            thread = self._thread
            self._stop_event.set()

        if thread is None:
            return False

        thread.join(timeout=float(timeout_seconds))
        stopped = not thread.is_alive()

        if stopped:
            with self._lock:
                if self._thread is thread:
                    self._thread = None

        return stopped

    def _run(self) -> None:
        """Poll immediately, then wait safely between future polls."""
        while not self._stop_event.is_set():
            self.poll_once()

            if self._stop_event.wait(
                self._poll_interval_seconds
            ):
                return


reminder_scheduler = ReminderScheduler()