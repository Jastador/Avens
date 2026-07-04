"""Camera and hand-tracking backend for Avens Vision.

This module owns frame processing, gesture recognition, and carefully bounded
Windows actions. PyQt owns all presentation through the embedded dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
import datetime
import os
from pathlib import Path
import time
import urllib.request
from threading import RLock
from typing import Any, Final

import cv2
import mediapipe as mp
import pyautogui
import screen_brightness_control as sbc
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from automation.commands import force_volume_change
from core.gesture_engine import GestureEngine, GestureSignal

@dataclass(frozen=True)
class VisionResult:
    """A completed camera result exposed to the UI without frame data."""

    kind: str
    text: str
    detail: str = ""


VISION_RESULT_KINDS: Final[frozenset[str]] = frozenset(
    {
        "local_identify",
        "local_describe",
        "local_read",
        "online_google_lens",
    }
)

_vision_result_lock = RLock()
_latest_vision_result: VisionResult | None = None

vision_active = False
vision_fullscreen_requested = False
vision_guide_visible = True
vision_hud_mode = "STANDARD"
vision_scan_state = ""
vision_scan_progress: float | None = None

@dataclass
class VisionTelemetry:
    """Small snapshot of what the camera currently sees."""

    status: str = "CAMERA ONLINE"
    gesture: str = "NO HAND DETECTED"
    mode: str = "ACTIVE"
    hands_detected: int = 0
    fps: float = 0.0
    value: int | None = None
    hold_progress: float = 0.0
    controls_locked: bool = False
    last_action: str | None = None
    guide_key: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "gesture": self.gesture,
            "mode": self.mode,
            "hands_detected": self.hands_detected,
            "fps": self.fps,
            "value": self.value,
            "hold_progress": self.hold_progress,
            "controls_locked": self.controls_locked,
            "last_action": self.last_action,
            "guide_key": self.guide_key,
        }

def start_vision() -> None:
    """Request that the Qt vision dashboard starts the camera."""
    global vision_active
    vision_active = True

def stop_vision() -> None:
    """Stop the camera and return the UI to its compact orb layout."""
    global vision_active
    global vision_fullscreen_requested
    global vision_scan_state
    global vision_scan_progress

    vision_active = False
    vision_fullscreen_requested = False
    vision_scan_state = ""
    vision_scan_progress = None
    clear_latest_vision_result()

def request_vision_fullscreen() -> None:
    """Start vision and request a webcam-only full-screen layout."""
    global vision_active, vision_fullscreen_requested
    vision_active = True
    vision_fullscreen_requested = True

def restore_vision_layout() -> None:
    """Keep the camera running but return to the normal orb + dashboard view."""
    global vision_fullscreen_requested
    vision_fullscreen_requested = False

def is_vision_requested() -> bool:
    """Return the state requested by voice commands or dashboard buttons."""
    return vision_active

def is_vision_fullscreen_requested() -> bool:
    """Return whether the camera should occupy the full display."""
    return vision_active and vision_fullscreen_requested

def set_vision_guide_visible(visible: bool) -> None:
    """Show or hide the on-camera gesture guide."""
    global vision_guide_visible
    vision_guide_visible = bool(visible)

def is_vision_guide_visible() -> bool:
    """Return whether the gesture guide should be drawn on the camera feed."""
    return vision_guide_visible

def set_vision_scan_state(
    state: str | None,
    progress: float | None = None,
) -> None:
    """Show or clear the temporary centre scan overlay and capture progress."""
    global vision_scan_state, vision_scan_progress

    vision_scan_state = " ".join((state or "").split()).upper()

    if not vision_scan_state or progress is None:
        vision_scan_progress = None
        return

    vision_scan_progress = max(0.0, min(1.0, float(progress)))

def get_vision_scan_state() -> str:
    """Return the currently displayed Lens Scan state."""
    return vision_scan_state

def get_vision_scan_progress() -> float | None:
    """Return Lens Scan capture progress, or None when not capturing."""
    return vision_scan_progress

def set_latest_vision_result(
    kind: str,
    text: str,
    detail: str | None = None,
) -> None:
    """Store one completed analysis result for read-only UI presentation."""
    global _latest_vision_result

    normalised_kind = " ".join(str(kind).casefold().split())

    if normalised_kind not in VISION_RESULT_KINDS:
        raise ValueError(f"Unsupported vision result kind: {kind}")

    normalised_text = str(text).strip()

    if not normalised_text:
        raise ValueError("Vision result text cannot be empty.")

    normalised_detail = str(detail or "").strip()

    with _vision_result_lock:
        _latest_vision_result = VisionResult(
            kind=normalised_kind,
            text=normalised_text,
            detail=normalised_detail,
        )


def get_latest_vision_result() -> VisionResult | None:
    """Return the latest immutable completed vision result, if any."""
    with _vision_result_lock:
        return _latest_vision_result


def clear_latest_vision_result() -> None:
    """Remove any completed result when the related vision session ends."""
    global _latest_vision_result

    with _vision_result_lock:
        _latest_vision_result = None

def set_vision_hud_mode(mode: str) -> None:
    """Set the normal camera overlay style."""
    global vision_hud_mode

    normalised = mode.strip().upper()

    if normalised not in {"STANDARD", "MINIMAL"}:
        raise ValueError(
            "Vision HUD mode must be either STANDARD or MINIMAL."
        )

    vision_hud_mode = normalised


def get_vision_hud_mode() -> str:
    """Return the normal camera overlay preference."""
    return vision_hud_mode


def is_minimal_vision_hud() -> bool:
    """Fullscreen always uses the compact HUD without changing preference."""
    return (
        vision_fullscreen_requested
        or vision_hud_mode == "MINIMAL"
    )

def download_model() -> str:
    """Download the MediaPipe hand-landmarker asset only when it is missing."""
    model_path = os.path.join(
        os.path.dirname(__file__),
        "hand_landmarker.task",
    )

    if not os.path.exists(model_path):
        print("⏳ Downloading MediaPipe hand tracking model...")

        url = (
            "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
            "hand_landmarker/float16/1/hand_landmarker.task"
        )

        urllib.request.urlretrieve(url, model_path)

    return model_path


def draw_manual_skeleton(image, landmarks) -> None:
    """Draw the MediaPipe hand skeleton without relying on mp.solutions."""
    height, width, _ = image.shape

    connections = [
        (0, 1), (1, 2), (2, 3), (3, 4),
        (0, 5), (5, 6), (6, 7), (7, 8),
        (5, 9), (9, 10), (10, 11), (11, 12),
        (9, 13), (13, 14), (14, 15), (15, 16),
        (13, 17), (17, 18), (18, 19), (19, 20),
        (0, 17),
    ]

    points: list[tuple[int, int]] = []

    for landmark in landmarks:
        x = int(landmark.x * width)
        y = int(landmark.y * height)

        points.append((x, y))
        cv2.circle(image, (x, y), 5, (245, 230, 80), cv2.FILLED)

    for start_index, end_index in connections:
        if start_index < len(points) and end_index < len(points):
            cv2.line(
                image,
                points[start_index],
                points[end_index],
                (245, 185, 45),
                2,
                lineType=cv2.LINE_AA,
            )


class HandVisionProcessor:
    """Process webcam frames and execute verified gesture actions."""

    def __init__(self) -> None:
        model_path = download_model()

        base_options = python.BaseOptions(
            model_asset_path=model_path,
        )

        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=1,
            min_hand_detection_confidence=0.7,
            min_hand_presence_confidence=0.7,
            min_tracking_confidence=0.7,
            running_mode=vision.RunningMode.VIDEO,
        )

        self.detector = vision.HandLandmarker.create_from_options(options)
        self.gesture_engine = GestureEngine()
        self.last_timestamp_ms = 0
        self._action_toast: str | None = None
        self._action_toast_until = 0.0

    def close(self) -> None:
        """Release MediaPipe resources before the worker thread exits."""
        try:
            self.detector.close()
        except Exception:
            pass

    def process_frame(
        self,
        frame: Any,
        fps: float,
    ) -> tuple[Any, VisionTelemetry]:
        """Flip, track, draw, and act on one BGR OpenCV frame."""
        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=rgb_frame,
        )

        timestamp_ms = int(time.time() * 1000)

        if timestamp_ms <= self.last_timestamp_ms:
            timestamp_ms = self.last_timestamp_ms + 1

        self.last_timestamp_ms = timestamp_ms

        result = self.detector.detect_for_video(
            mp_image,
            timestamp_ms,
        )

        hand_landmarks = result.hand_landmarks
        primary_hand = hand_landmarks[0] if hand_landmarks else None

        now = time.monotonic()

        signal = self.gesture_engine.process(primary_hand)

        scan_is_active = bool(get_vision_scan_state())

        action = (
            None
            if scan_is_active
            else self._apply_signal(signal)
        )

        if action:
            self._action_toast = action
            self._action_toast_until = now + 1.4

        last_action = (
            self._action_toast
            if now < self._action_toast_until
            else None
        )

        telemetry = VisionTelemetry(
            gesture=signal.label,
            mode=signal.mode,
            hands_detected=len(hand_landmarks),
            fps=fps,
            value=signal.value,
            hold_progress=signal.hold_progress,
            controls_locked=signal.controls_locked,
            last_action=last_action,
            guide_key=self._guide_key_for(signal),
        )

        for landmarks in hand_landmarks:
            draw_manual_skeleton(frame, landmarks)

        if is_minimal_vision_hud():
            self._draw_minimal_hud(frame, telemetry)
        else:
            self._draw_hud(frame, telemetry)

            if is_vision_guide_visible():
                self._draw_gesture_guide(frame, telemetry)

        scan_state = get_vision_scan_state()

        if scan_state:
            self._draw_scan_region(
                frame,
                scan_state,
                get_vision_scan_progress(),
            )

        return frame, telemetry

    def _apply_signal(self, signal: GestureSignal) -> str | None:
        """Perform only the deliberate action emitted by GestureEngine."""
        action = signal.action

        if action == "VOLUME_DELTA" and signal.value:
            direction = "up" if signal.value > 0 else "down"
            steps = min(abs(signal.value), 8)

            force_volume_change(direction, steps)

            return f"VOLUME {direction.upper()} x{steps}"

        if action == "SET_BRIGHTNESS" and signal.value is not None:
            self._set_brightness(signal.value)

            return f"BRIGHTNESS {signal.value}%"

        if action == "TOGGLE_PLAY_PAUSE":
            self._toggle_play_pause()

            return "PLAY / PAUSE"

        if action == "TAKE_SCREENSHOT":
            screenshot_name = self._take_screenshot()

            return screenshot_name or "SCREENSHOT FAILED"

        if action == "LOCK_CONTROLS":
            return "CONTROLS LOCKED"

        if action == "UNLOCK_CONTROLS":
            return "CONTROLS UNLOCKED"

        return None

    @staticmethod
    def _set_brightness(level: int) -> None:
        """Set display brightness while preventing invalid values."""
        try:
            safe_level = max(0, min(100, int(level)))
            sbc.set_brightness(safe_level)

        except Exception as error:
            print(f"⚠️ Brightness gesture error: {error}")

    @staticmethod
    def _toggle_play_pause() -> None:
        """Send Windows' dedicated media play/pause key."""
        media_play_pause = 0xB3

        ctypes.windll.user32.keybd_event(
            media_play_pause,
            0,
            0,
            0,
        )

        ctypes.windll.user32.keybd_event(
            media_play_pause,
            0,
            2,
            0,
        )

    @staticmethod
    def _take_screenshot() -> str | None:
        """Save gesture screenshots in a predictable project folder."""
        try:
            screenshot_dir = Path.cwd() / "screenshots"
            screenshot_dir.mkdir(exist_ok=True)

            filename = (
                "vision_"
                f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            )

            filepath = screenshot_dir / filename

            pyautogui.screenshot(str(filepath))

            print(f"📸 Vision screenshot saved: {filepath}")

            return filename

        except Exception as error:
            print(f"⚠️ Screenshot gesture error: {error}")

            return None

    @staticmethod
    def _guide_key_for(signal: GestureSignal) -> str:
        """Map the current gesture signal to one guide row."""
        label = signal.label.upper()
        action = signal.action or ""

        if (
            action in {"LOCK_CONTROLS", "UNLOCK_CONTROLS"}
            or "THUMBS UP" in label
            or "CONTROLS LOCKED" in label
        ):
            return "LOCK"

        if action == "VOLUME_DELTA" or "VOLUME" in label:
            return "VOLUME"

        if action == "SET_BRIGHTNESS" or "BRIGHTNESS" in label:
            return "BRIGHTNESS"

        if (
            action == "TOGGLE_PLAY_PAUSE"
            or "PAUSE" in label
            or "PLAY" in label
        ):
            return "PLAY_PAUSE"

        if (
            action == "TAKE_SCREENSHOT"
            or "SCREENSHOT" in label
            or "V SIGN" in label
        ):
            return "SCREENSHOT"

        return ""

    @staticmethod
    def _draw_gesture_guide(
        frame: Any,
        telemetry: VisionTelemetry,
    ) -> None:
        """Draw a compact live gesture guide in the camera feed."""
        height, width = frame.shape[:2]

        entries = [
            ("VOLUME", "INDEX DIAL", "Tilt + rotate index"),
            ("BRIGHTNESS", "BRIGHTNESS", "Open palm -> close fist"),
            ("PLAY_PAUSE", "PLAY / PAUSE", "Hold index upright"),
            ("SCREENSHOT", "SCREENSHOT", "Hold V-sign"),
            ("LOCK", "LOCK / UNLOCK", "Hold thumbs-up"),
        ]

        panel_width = min(350, max(270, width - 32))
        row_height = 27
        panel_height = 38 + (len(entries) * row_height) + 12

        left = max(16, width - panel_width - 16)
        top = max(16, height - panel_height - 16)
        right = left + panel_width
        bottom = top + panel_height

        overlay = frame.copy()

        cv2.rectangle(
            overlay,
            (left, top),
            (right, bottom),
            (10, 14, 24),
            cv2.FILLED,
        )

        cv2.addWeighted(overlay, 0.88, frame, 0.12, 0, frame)

        cv2.rectangle(
            frame,
            (left, top),
            (right, bottom),
            (245, 185, 45),
            1,
        )

        cv2.putText(
            frame,
            "GESTURE GUIDE",
            (left + 12, top + 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (245, 230, 80),
            1,
            lineType=cv2.LINE_AA,
        )

        for index, (key, title, instruction) in enumerate(entries):
            row_top = top + 35 + (index * row_height)
            is_active = key == telemetry.guide_key

            if is_active:
                cv2.rectangle(
                    frame,
                    (left + 7, row_top - 17),
                    (right - 7, row_top + 6),
                    (46, 71, 105),
                    cv2.FILLED,
                )

            title_color = (
                (255, 232, 110)
                if is_active
                else (222, 229, 241)
            )

            instruction_color = (
                (180, 203, 238)
                if is_active
                else (135, 153, 182)
            )

            cv2.putText(
                frame,
                title,
                (left + 14, row_top),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.34,
                title_color,
                1,
                lineType=cv2.LINE_AA,
            )

            cv2.putText(
                frame,
                instruction,
                (left + 142, row_top),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.31,
                instruction_color,
                1,
                lineType=cv2.LINE_AA,
            )

    @staticmethod
    def _draw_scan_region(
        frame: Any,
        state: str,
        progress: float | None,
    ) -> None:
        """Draw the centre region used by the one-shot Lens Scan crop."""
        height, width = frame.shape[:2]

        crop_width = max(1, int(width * 0.72))
        crop_height = max(1, int(height * 0.86))

        left = (width - crop_width) // 2
        top = (height - crop_height) // 2
        right = left + crop_width
        bottom = top + crop_height

        scan_color = (0, 220, 255)
        panel_color = (12, 18, 30)

        cv2.rectangle(
            frame,
            (left, top),
            (right, bottom),
            scan_color,
            2,
            lineType=cv2.LINE_AA,
        )

        corner_length = min(42, crop_width // 5, crop_height // 5)

        corners = (
            ((left, top), (left + corner_length, top), (left, top + corner_length)),
            ((right, top), (right - corner_length, top), (right, top + corner_length)),
            ((left, bottom), (left + corner_length, bottom), (left, bottom - corner_length)),
            ((right, bottom), (right - corner_length, bottom), (right, bottom - corner_length)),
        )

        for corner, horizontal_end, vertical_end in corners:
            cv2.line(
                frame,
                corner,
                horizontal_end,
                scan_color,
                4,
                lineType=cv2.LINE_AA,
            )
            cv2.line(
                frame,
                corner,
                vertical_end,
                scan_color,
                4,
                lineType=cv2.LINE_AA,
            )

        label = f" {state} "
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.48
        thickness = 1

        (label_width, label_height), _ = cv2.getTextSize(
            label,
            font,
            scale,
            thickness,
        )

        label_left = left + 12
        label_top = max(8, top - label_height - 16)
        label_right = label_left + label_width + 12
        label_bottom = label_top + label_height + 12

        cv2.rectangle(
            frame,
            (label_left, label_top),
            (label_right, label_bottom),
            panel_color,
            cv2.FILLED,
        )

        cv2.rectangle(
            frame,
            (label_left, label_top),
            (label_right, label_bottom),
            scan_color,
            1,
        )

        cv2.putText(
            frame,
            label,
            (label_left + 6, label_bottom - 7),
            font,
            scale,
            scan_color,
            thickness,
            lineType=cv2.LINE_AA,
        )

        if progress is None:
            return

        safe_progress = max(0.0, min(1.0, float(progress)))
        percentage = int(round(safe_progress * 100))

        bar_left = left + 16
        bar_right = right - 16
        bar_top = bottom - 28
        bar_bottom = bottom - 16

        overlay = frame.copy()

        cv2.rectangle(
            overlay,
            (bar_left - 4, bar_top - 4),
            (bar_right + 4, bar_bottom + 4),
            panel_color,
            cv2.FILLED,
        )

        cv2.addWeighted(overlay, 0.84, frame, 0.16, 0, frame)

        cv2.rectangle(
            frame,
            (bar_left, bar_top),
            (bar_right, bar_bottom),
            (60, 70, 90),
            cv2.FILLED,
        )

        filled_right = bar_left + int(
            (bar_right - bar_left) * safe_progress
        )

        if filled_right > bar_left:
            cv2.rectangle(
                frame,
                (bar_left, bar_top),
                (filled_right, bar_bottom),
                scan_color,
                cv2.FILLED,
            )

        cv2.rectangle(
            frame,
            (bar_left, bar_top),
            (bar_right, bar_bottom),
            scan_color,
            1,
        )

        progress_text = (
            "CAPTURED - YOU CAN LOWER IT"
            if safe_progress >= 1.0
            else f"HOLD STILL {percentage}%"
        )

        cv2.putText(
            frame,
            progress_text,
            (bar_left, bar_top - 7),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            scan_color,
            1,
            lineType=cv2.LINE_AA,
        )

    @staticmethod
    def _draw_minimal_hud(
        frame: Any,
        telemetry: VisionTelemetry,
    ) -> None:
        """Draw a small status pill for minimal and fullscreen vision."""
        height, width = frame.shape[:2]

        mode = "LOCKED" if telemetry.controls_locked else "ACTIVE"
        detail = telemetry.last_action or telemetry.gesture

        if telemetry.value is not None:
            detail = f"{detail} | {telemetry.value}%"

        if len(detail) > 46:
            detail = f"{detail[:43]}..."

        text = f"AVENS | {mode} | {detail}"

        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.45
        thickness = 1

        (text_width, text_height), _ = cv2.getTextSize(
            text,
            font,
            scale,
            thickness,
        )

        left, top = 18, 18
        right = min(width - 18, left + text_width + 28)
        bottom = top + text_height + 22

        overlay = frame.copy()

        cv2.rectangle(
            overlay,
            (left, top),
            (right, bottom),
            (10, 14, 24),
            cv2.FILLED,
        )

        cv2.addWeighted(overlay, 0.88, frame, 0.12, 0, frame)

        border_color = (
            (105, 215, 160)
            if not telemetry.controls_locked
            else (110, 155, 255)
        )

        cv2.rectangle(
            frame,
            (left, top),
            (right, bottom),
            border_color,
            1,
        )

        cv2.putText(
            frame,
            text,
            (left + 14, bottom - 10),
            font,
            scale,
            (230, 237, 250),
            thickness,
            lineType=cv2.LINE_AA,
        )

    @staticmethod
    def _draw_hud(
        frame: Any,
        telemetry: VisionTelemetry,
    ) -> None:
        """Draw control state directly on the camera feed."""
        height, width = frame.shape[:2]

        left, top = 16, 16
        right = min(width - 16, left + 550)
        bottom = min(height - 16, top + 142)

        cv2.rectangle(
            frame,
            (left, top),
            (right, bottom),
            (18, 20, 30),
            cv2.FILLED,
        )

        cv2.rectangle(
            frame,
            (left, top),
            (right, bottom),
            (245, 185, 45),
            1,
        )

        mode_color = (
            (100, 210, 150)
            if not telemetry.controls_locked
            else (110, 155, 255)
        )

        hold_percent = int(round(telemetry.hold_progress * 100))

        value_text = (
            f"  VALUE: {telemetry.value}%"
            if telemetry.value is not None
            else ""
        )

        action_text = telemetry.last_action or "READY"

        cv2.putText(
            frame,
            "AVENS VISION  |  GESTURE CONTROL",
            (left + 14, top + 27),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.56,
            (245, 230, 80),
            2,
            lineType=cv2.LINE_AA,
        )

        cv2.putText(
            frame,
            f"{telemetry.mode}: {telemetry.gesture}",
            (left + 14, top + 54),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.43,
            (232, 236, 246),
            1,
            lineType=cv2.LINE_AA,
        )

        cv2.putText(
            frame,
            f"HANDS: {telemetry.hands_detected}  |  "
            f"{telemetry.fps:.0f} FPS  |  "
            f"HOLD: {hold_percent}%{value_text}",
            (left + 14, top + 79),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.37,
            (170, 200, 255),
            1,
            lineType=cv2.LINE_AA,
        )

        cv2.putText(
            frame,
            f"STATUS: {action_text}",
            (left + 14, top + 104),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.40,
            mode_color,
            1,
            lineType=cv2.LINE_AA,
        )

        bar_left = left + 14
        bar_top = top + 116
        bar_width = right - left - 28
        bar_height = 10

        cv2.rectangle(
            frame,
            (bar_left, bar_top),
            (bar_left + bar_width, bar_top + bar_height),
            (45, 55, 75),
            cv2.FILLED,
        )

        filled_width = int(bar_width * telemetry.hold_progress)

        if filled_width:
            cv2.rectangle(
                frame,
                (bar_left, bar_top),
                (bar_left + filled_width, bar_top + bar_height),
                mode_color,
                cv2.FILLED,
            )