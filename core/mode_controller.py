"""Runtime mode state for Avens.

This module decides which brain and camera providers Avens is allowed to use.
It stores no API keys and makes no network calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Final


BRAIN_MODES: Final = {"offline", "online"}
CAMERA_MODES: Final = {"offline", "online"}

BRAIN_PROVIDERS: Final = {
    "local",
    "gpt",
    "gemini",
}

MODE_SCOPES: Final = {
    "brain",
    "camera",
    "both",
}

PENDING_CHOICES: Final = {
    "none",
    "choose_scope",
    "choose_provider",
}


@dataclass(frozen=True)
class ModeSnapshot:
    """One immutable view of Avens' current provider choices."""

    brain_mode: str
    camera_mode: str
    brain_provider: str
    pending_choice: str
    pending_target_mode: str | None
    pending_scope: str | None


class ModeController:
    """Thread-safe controller for offline and online Avens modes."""

    def __init__(self) -> None:
        self._lock = RLock()

        # Avens always starts private and local.
        self._brain_mode = "offline"
        self._camera_mode = "offline"
        self._brain_provider = "local"

        self._pending_choice = "none"
        self._pending_target_mode: str | None = None
        self._pending_scope: str | None = None

    def snapshot(self) -> ModeSnapshot:
        """Return the current mode state without exposing mutable internals."""
        with self._lock:
            return ModeSnapshot(
                brain_mode=self._brain_mode,
                camera_mode=self._camera_mode,
                brain_provider=self._brain_provider,
                pending_choice=self._pending_choice,
                pending_target_mode=self._pending_target_mode,
                pending_scope=self._pending_scope,
            )

    def get_status_text(self) -> str:
        """Return a compact spoken-friendly description of active modes."""
        state = self.snapshot()

        return (
            f"Brain is {state.brain_mode} using {state.brain_provider}. "
            f"Camera is {state.camera_mode}."
        )

    def begin_mode_change(self, target_mode: str) -> None:
        """Begin an online/offline request and wait for brain/camera scope."""
        normalised_mode = self._normalise_choice(
            target_mode,
            BRAIN_MODES,
            "Mode must be online or offline.",
        )

        with self._lock:
            self._pending_choice = "choose_scope"
            self._pending_target_mode = normalised_mode
            self._pending_scope = None

    def choose_scope(self, scope: str) -> bool:
        """Apply a scope choice. Returns True when a brain provider is needed."""
        normalised_scope = self._normalise_choice(
            scope,
            MODE_SCOPES,
            "Scope must be brain, camera, or both.",
        )

        with self._lock:
            if self._pending_choice != "choose_scope":
                raise RuntimeError("Avens is not waiting for a scope choice.")

            target_mode = self._pending_target_mode

            if target_mode is None:
                raise RuntimeError("No target mode was selected.")

            self._pending_scope = normalised_scope

            if target_mode == "offline":
                self._apply_offline_scope(normalised_scope)
                self._clear_pending()
                return False

            # Online camera mode can be applied immediately.
            if normalised_scope in {"camera", "both"}:
                self._camera_mode = "online"

            # A camera-only request needs no provider selection.
            if normalised_scope == "camera":
                self._clear_pending()
                return False

            self._pending_choice = "choose_provider"
            return True

    def choose_brain_provider(self, provider: str) -> None:
        """Finish an online-brain request with GPT or Gemini."""
        normalised_provider = self._normalise_choice(
            provider,
            {"gpt", "gemini"},
            "Online brain provider must be GPT or Gemini.",
        )

        with self._lock:
            if self._pending_choice != "choose_provider":
                raise RuntimeError(
                    "Avens is not waiting for a brain provider choice."
                )

            self._brain_mode = "online"
            self._brain_provider = normalised_provider
            self._clear_pending()

    def set_camera_mode(self, mode: str) -> None:
        """Set camera mode directly for clear commands such as camera offline."""
        normalised_mode = self._normalise_choice(
            mode,
            CAMERA_MODES,
            "Camera mode must be online or offline.",
        )

        with self._lock:
            self._camera_mode = normalised_mode

    def set_brain_offline(self) -> None:
        """Return the language-model brain to custom_avens locally."""
        with self._lock:
            self._brain_mode = "offline"
            self._brain_provider = "local"

    def cancel_pending_change(self) -> None:
        """Discard an unfinished online/offline voice flow."""
        with self._lock:
            self._clear_pending()

    def _apply_offline_scope(self, scope: str) -> None:
        """Apply a completed offline choice."""
        if scope in {"brain", "both"}:
            self._brain_mode = "offline"
            self._brain_provider = "local"

        if scope in {"camera", "both"}:
            self._camera_mode = "offline"

    def _clear_pending(self) -> None:
        """Reset temporary voice-flow state."""
        self._pending_choice = "none"
        self._pending_target_mode = None
        self._pending_scope = None

    @staticmethod
    def _normalise_choice(
        value: str,
        valid_choices: set[str],
        error_message: str,
    ) -> str:
        """Validate one simple spoken-mode value."""
        normalised = " ".join(str(value).casefold().split())

        if normalised not in valid_choices:
            raise ValueError(error_message)

        return normalised


mode_controller = ModeController()