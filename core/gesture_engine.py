"""Gesture recognition rules for Avens Vision.

This module does not touch OpenCV, Qt, Windows volume, brightness, media,
or screenshots. It only turns MediaPipe landmarks into safe action signals.
core/vision.py will execute those actions in the next step.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any, Optional, Sequence


@dataclass(frozen=True)
class GestureSignal:
    """One action-ready result from a camera frame."""

    label: str
    mode: str
    action: Optional[str] = None
    value: Optional[int] = None
    hold_progress: float = 0.0
    controls_locked: bool = False


class GestureEngine:
    """Recognise Avens hand gestures using palm-normalised measurements."""

    LOCK_HOLD_SECONDS = 0.65
    SCREENSHOT_HOLD_SECONDS = 0.75
    PLAY_PAUSE_HOLD_SECONDS = 0.75
    BRIGHTNESS_ENTER_HOLD_SECONDS = 0.35

    INDEX_VERTICAL_DEGREES = 12.0
    VOLUME_ENTER_DEGREES = 20.0
    VOLUME_STEP_DEGREES = 6.0
    PAUSE_AFTER_VOLUME_SECONDS = 1.0

    BRIGHTNESS_MIN_OPENNESS = 0.92
    BRIGHTNESS_MAX_OPENNESS = 1.65
    BRIGHTNESS_ALPHA = 0.28
    BRIGHTNESS_REPEAT_SECONDS = 0.12
    BRIGHTNESS_MIN_CHANGE = 2

    HAND_LOST_RESET_SECONDS = 0.70

    def __init__(self) -> None:
        self._locked = False
        self._last_hand_seen_at = 0.0

        self._held_pose: Optional[str] = None
        self._hold_started_at = 0.0
        self._hold_fired = False

        self._brightness_active = False
        self._smoothed_brightness: Optional[float] = None
        self._last_brightness_value: Optional[int] = None
        self._last_brightness_at = 0.0

        self._volume_last_angle: Optional[float] = None
        self._volume_residual_degrees = 0.0
        self._last_volume_at = 0.0

    @property
    def controls_locked(self) -> bool:
        return self._locked

    def enable_controls(self) -> None:
        """Unlock gestures through a deliberate dashboard or voice action."""
        self._locked = False
        self._reset_transient_state()

    def lock_controls(self) -> None:
        """Disable every gesture that can affect the computer."""
        self._locked = True
        self._reset_transient_state()

    def process(
        self,
        landmarks: Optional[Sequence[Any]],
        now: Optional[float] = None,
    ) -> GestureSignal:
        """Convert MediaPipe hand landmarks into one safe signal."""
        now = time.monotonic() if now is None else now

        if not landmarks:
            return self._no_hand_signal(now)

        self._last_hand_seen_at = now
        features = self._features(landmarks)

        if self._locked:
            if features["thumbs_up"]:
                progress, fired = self._hold(
                    "THUMBS_UP_UNLOCK",
                    now,
                    self.LOCK_HOLD_SECONDS,
                )

                if fired:
                    self.enable_controls()
                    return GestureSignal(
                        label="GESTURE CONTROLS UNLOCKED",
                        mode="ACTIVE",
                        action="UNLOCK_CONTROLS",
                        hold_progress=1.0,
                        controls_locked=False,
                    )

                return GestureSignal(
                    label="HOLD THUMBS UP TO UNLOCK",
                    mode="LOCKED",
                    hold_progress=progress,
                    controls_locked=True,
                )

            self._reset_hold()
            return GestureSignal(
                label="CONTROLS LOCKED",
                mode="LOCKED",
                controls_locked=True,
            )

        # Thumbs-up always wins, even during brightness mode.
        if features["thumbs_up"]:
            progress, fired = self._hold(
                "THUMBS_UP",
                now,
                self.LOCK_HOLD_SECONDS,
            )

            if fired:
                self.lock_controls()
                return GestureSignal(
                    label="GESTURE CONTROLS LOCKED",
                    mode="LOCKED",
                    action="LOCK_CONTROLS",
                    hold_progress=1.0,
                    controls_locked=True,
                )

            return GestureSignal(
                label="HOLD THUMBS UP TO LOCK",
                mode="ACTIVE",
                hold_progress=progress,
            )

        # Brightness stays active while you slowly close the hand.
        if self._brightness_active:
            return self._brightness_signal(features, now)

        if features["v_sign"]:
            return self._one_shot_signal(
                pose="V_SIGN",
                label="HOLD V SIGN FOR SCREENSHOT",
                action="TAKE_SCREENSHOT",
                now=now,
            )

        if features["single_index"]:
            return self._index_signal(features, now)

        if features["open_palm"]:
            progress, fired = self._hold(
                "OPEN_PALM",
                now,
                self.BRIGHTNESS_ENTER_HOLD_SECONDS,
            )

            if fired:
                self._brightness_active = True
                self._smoothed_brightness = None
                self._last_brightness_value = None
                self._last_brightness_at = 0.0
                return self._brightness_signal(features, now)

            return GestureSignal(
                label="HOLD OPEN PALM FOR BRIGHTNESS",
                mode="ACTIVE",
                hold_progress=progress,
            )

        self._reset_hold()
        self._reset_volume_dial()

        return GestureSignal(
            label="ACTIVE - SHOW A GESTURE",
            mode="ACTIVE",
        )

    def _no_hand_signal(self, now: float) -> GestureSignal:
        self._reset_hold()
        self._reset_volume_dial()

        if now - self._last_hand_seen_at >= self.HAND_LOST_RESET_SECONDS:
            self._brightness_active = False
            self._smoothed_brightness = None

        return GestureSignal(
            label="NO HAND DETECTED",
            mode="LOCKED" if self._locked else "ACTIVE",
            controls_locked=self._locked,
        )

    def _brightness_signal(
        self,
        features: dict[str, Any],
        now: float,
    ) -> GestureSignal:
        self._reset_hold()
        self._reset_volume_dial()

        value = self._brightness_value(features["palm_openness"])
        action: Optional[str] = None

        changed_enough = (
            self._last_brightness_value is None
            or abs(value - self._last_brightness_value)
            >= self.BRIGHTNESS_MIN_CHANGE
        )

        cooldown_elapsed = (
            now - self._last_brightness_at
            >= self.BRIGHTNESS_REPEAT_SECONDS
        )

        if changed_enough and cooldown_elapsed:
            self._last_brightness_value = value
            self._last_brightness_at = now
            action = "SET_BRIGHTNESS"

        return GestureSignal(
            label=f"BRIGHTNESS: {value}%",
            mode="BRIGHTNESS",
            action=action,
            value=value,
        )

    def _index_signal(
        self,
        features: dict[str, Any],
        now: float,
    ) -> GestureSignal:
        angle = features["index_angle_degrees"]
        is_near_vertical = abs(angle) <= self.INDEX_VERTICAL_DEGREES

        # Upright + still index finger means pause/play.
        if (
            is_near_vertical
            and self._volume_last_angle is None
            and now - self._last_volume_at
            >= self.PAUSE_AFTER_VOLUME_SECONDS
        ):
            return self._one_shot_signal(
                pose="UPRIGHT_INDEX",
                label="HOLD INDEX UP TO PAUSE / PLAY",
                action="TOGGLE_PLAY_PAUSE",
                now=now,
            )

        # Tilt the index finger to enter volume mode.
        # Positive angle is clockwise in the mirrored preview.
        if (
            abs(angle) >= self.VOLUME_ENTER_DEGREES
            or self._volume_last_angle is not None
        ):
            self._reset_hold()

            if self._volume_last_angle is None:
                self._volume_last_angle = angle
                self._volume_residual_degrees = 0.0

                return GestureSignal(
                    label="VOLUME DIAL READY - ROTATE INDEX",
                    mode="VOLUME",
                )

            angle_change = angle - self._volume_last_angle
            self._volume_last_angle = angle
            self._volume_residual_degrees += angle_change

            steps = int(
                self._volume_residual_degrees
                / self.VOLUME_STEP_DEGREES
            )

            if steps:
                self._volume_residual_degrees -= (
                    steps * self.VOLUME_STEP_DEGREES
                )
                self._last_volume_at = now

                return GestureSignal(
                    label="VOLUME UP" if steps > 0 else "VOLUME DOWN",
                    mode="VOLUME",
                    action="VOLUME_DELTA",
                    value=steps,
                )

            return GestureSignal(
                label="VOLUME DIAL - ROTATE CW / CCW",
                mode="VOLUME",
            )

        self._reset_hold()

        return GestureSignal(
            label="TILT INDEX TO ENTER VOLUME DIAL",
            mode="ACTIVE",
        )

    def _one_shot_signal(
        self,
        pose: str,
        label: str,
        action: str,
        now: float,
    ) -> GestureSignal:
        required = (
            self.SCREENSHOT_HOLD_SECONDS
            if action == "TAKE_SCREENSHOT"
            else self.PLAY_PAUSE_HOLD_SECONDS
        )

        progress, fired = self._hold(pose, now, required)

        if fired:
            return GestureSignal(
                label=action.replace("_", " "),
                mode="ACTIVE",
                action=action,
                hold_progress=1.0,
            )

        return GestureSignal(
            label=label,
            mode="ACTIVE",
            hold_progress=progress,
        )

    def _hold(
        self,
        pose: str,
        now: float,
        required_seconds: float,
    ) -> tuple[float, bool]:
        if self._held_pose != pose:
            self._held_pose = pose
            self._hold_started_at = now
            self._hold_fired = False

        progress = min(
            1.0,
            (now - self._hold_started_at) / required_seconds,
        )

        fired = progress >= 1.0 and not self._hold_fired

        if fired:
            self._hold_fired = True

        return progress, fired

    def _reset_hold(self) -> None:
        self._held_pose = None
        self._hold_started_at = 0.0
        self._hold_fired = False

    def _reset_volume_dial(self) -> None:
        self._volume_last_angle = None
        self._volume_residual_degrees = 0.0

    def _reset_transient_state(self) -> None:
        self._reset_hold()
        self._reset_volume_dial()
        self._brightness_active = False
        self._smoothed_brightness = None
        self._last_brightness_value = None
        self._last_brightness_at = 0.0

    def _brightness_value(self, openness: float) -> int:
        clamped = max(
            self.BRIGHTNESS_MIN_OPENNESS,
            min(self.BRIGHTNESS_MAX_OPENNESS, openness),
        )

        raw = (
            (clamped - self.BRIGHTNESS_MIN_OPENNESS)
            / (
                self.BRIGHTNESS_MAX_OPENNESS
                - self.BRIGHTNESS_MIN_OPENNESS
            )
            * 100.0
        )

        previous = (
            raw
            if self._smoothed_brightness is None
            else self._smoothed_brightness
        )

        smoothed = previous + self.BRIGHTNESS_ALPHA * (raw - previous)
        self._smoothed_brightness = smoothed

        return int(round(smoothed))

    @staticmethod
    def _features(landmarks: Sequence[Any]) -> dict[str, Any]:
        if len(landmarks) < 21:
            raise ValueError(
                "MediaPipe returned fewer than 21 hand landmarks."
            )

        def distance(first: int, second: int) -> float:
            a, b = landmarks[first], landmarks[second]
            return math.hypot(a.x - b.x, a.y - b.y)

        wrist = 0
        palm_size = max(
            distance(5, 17),
            distance(0, 9),
            0.05,
        )

        def extended(tip: int, pip: int) -> bool:
            return (
                distance(tip, wrist)
                > distance(pip, wrist) * 1.14
            )

        index_extended = extended(8, 6)
        middle_extended = extended(12, 10)
        ring_extended = extended(16, 14)
        pinky_extended = extended(20, 18)

        thumb_tip = landmarks[4]
        thumb_ip = landmarks[3]
        thumb_mcp = landmarks[2]

        thumb_extended = (
            distance(4, 2) / palm_size > 0.62
        )

        other_fingers_folded = not any(
            (
                index_extended,
                middle_extended,
                ring_extended,
                pinky_extended,
            )
        )

        thumbs_up = (
            thumb_extended
            and thumb_tip.y < thumb_ip.y < thumb_mcp.y
            and other_fingers_folded
        )

        # 0° = index straight up.
        # Positive = clockwise in the mirrored camera view.
        index_tip = landmarks[8]
        index_pip = landmarks[6]

        index_angle_degrees = math.degrees(
            math.atan2(
                index_tip.x - index_pip.x,
                -(index_tip.y - index_pip.y),
            )
        )

        fingertip_distances = [
            distance(tip, wrist) / palm_size
            for tip in (8, 12, 16, 20)
        ]

        palm_openness = (
            sum(fingertip_distances)
            / len(fingertip_distances)
        )

        return {
            "open_palm": (
                index_extended
                and middle_extended
                and ring_extended
                and pinky_extended
            ),
            "single_index": (
                index_extended
                and not middle_extended
                and not ring_extended
                and not pinky_extended
            ),
            "v_sign": (
                index_extended
                and middle_extended
                and not ring_extended
                and not pinky_extended
            ),
            "thumbs_up": thumbs_up,
            "index_angle_degrees": index_angle_degrees,
            "palm_openness": palm_openness,
        }