"""Embedded PyQt vision dashboard for Avens."""

from __future__ import annotations

import time

import cv2
from PyQt5.QtCore import QThread, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from core.camera_intelligence import DEEP_MODEL_NAME, FAST_MODEL_NAME
from core.live_frame_buffer import live_frame_buffer
from core.mode_controller import mode_controller
from core.vision import (
    HandVisionProcessor,
    get_latest_vision_result,
    get_vision_hud_mode,
    get_vision_scan_progress,
    get_vision_scan_state,
    is_vision_guide_visible,
    is_vision_requested,
    set_vision_guide_visible,
    set_vision_hud_mode,
    start_vision,
    stop_vision,
)

class VisionWorker(QThread):
    """Owns the webcam and MediaPipe work away from the Qt UI thread."""

    frame_ready = pyqtSignal(QImage)
    telemetry_ready = pyqtSignal(dict)
    camera_error = pyqtSignal(str)
    camera_started = pyqtSignal()
    camera_stopped = pyqtSignal()

    def __init__(self, camera_index: int = 0, parent=None) -> None:
        super().__init__(parent)
        self.camera_index = camera_index
        self._running = False

    def stop(self) -> None:
        self._running = False
        self.requestInterruption()

    def _open_camera(self):
        """Try DirectShow first on Windows, then fall back to OpenCV defaults."""
        camera = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not camera.isOpened():
            camera.release()
            camera = cv2.VideoCapture(self.camera_index)

        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        camera.set(cv2.CAP_PROP_FPS, 30)
        return camera

    def run(self) -> None:
        camera = None
        processor = None
        try:
            camera = self._open_camera()
            if not camera.isOpened():
                self.camera_error.emit("Camera 0 could not be opened.")
                return

            processor = HandVisionProcessor()
            self._running = True
            self.camera_started.emit()
            last_frame_at = time.perf_counter()

            while self._running and not self.isInterruptionRequested():
                success, frame = camera.read()

                if not success:
                    self.camera_error.emit("The camera stopped returning frames.")
                    break

                # Keep only the latest raw frame in RAM for user-requested analysis.
                # This frame is overwritten every camera cycle and never written to disk.
                live_frame_buffer.publish(frame)

                now = time.perf_counter()
                elapsed = max(now - last_frame_at, 0.0001)
                last_frame_at = now
                fps = 1.0 / elapsed

                processed_frame, telemetry = processor.process_frame(frame, fps)
                rgb_frame = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB)
                height, width, channels = rgb_frame.shape
                bytes_per_line = channels * width
                qt_image = QImage(
                    rgb_frame.data,
                    width,
                    height,
                    bytes_per_line,
                    QImage.Format_RGB888,
                ).copy()

                self.frame_ready.emit(qt_image)
                self.telemetry_ready.emit(telemetry.as_dict())

        except Exception as error:
            self.camera_error.emit(str(error))
        finally:
            if processor is not None:
                processor.close()

            if camera is not None:
                camera.release()

            live_frame_buffer.clear()
            self._running = False
            self.camera_stopped.emit()


class VisionDashboard(QFrame):
    """A styled panel that displays the webcam feed and camera controls."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.worker: VisionWorker | None = None
        self._fullscreen_mode = False
        self._last_status = "STANDBY"
        self._reduced_motion = False

        self._build_ui()

        # Reads lightweight runtime state for labels only. This never touches
        # camera capture, frame processing, model requests, or recognition.
        self._runtime_timer = QTimer(self)
        self._runtime_timer.setInterval(250)
        self._runtime_timer.timeout.connect(self._sync_runtime_labels)
        self._runtime_timer.start()

        self._sync_runtime_labels()

    def _build_ui(self) -> None:
        self.setObjectName("visionDashboard")
        self.setFixedSize(670, 545)

        self.setStyleSheet(
            """
            QFrame#visionDashboard {
                background: rgba(8, 13, 23, 247);
                border: 1px solid #e6b94a;
                border-radius: 18px;
            }

            QLabel#visionTitle {
                color: #f5e650;
                font-size: 17px;
                font-weight: 700;
                letter-spacing: 1px;
            }

            QLabel#visionMode {
                color: #79e7ff;
                background: rgba(26, 71, 92, 150);
                border: 1px solid rgba(95, 206, 235, 180);
                border-radius: 7px;
                font-size: 10px;
                font-weight: 700;
                padding: 4px 7px;
            }

            QLabel#visionStatus {
                color: #b8d4ff;
                font-size: 11px;
                font-weight: 700;
            }

            QLabel#gestureLabel {
                color: #ffffff;
                font-size: 14px;
                font-weight: 700;
            }

            QLabel#scanLabel {
                color: #f5e650;
                font-size: 10px;
                font-weight: 700;
            }

            QLabel#metaLabel {
                color: #9aa9c5;
                font-size: 11px;
            }

            QLabel#cameraFeed {
                background: #020308;
                border: 1px solid #27304a;
                border-radius: 12px;
                color: #8491aa;
                font-size: 14px;
            }

            QProgressBar#scanProgress {
                background: #0b111d;
                border: 1px solid #293a52;
                border-radius: 2px;
                min-height: 4px;
                max-height: 4px;
            }

            QProgressBar#scanProgress::chunk {
                background: #f5e650;
                border-radius: 2px;
            }

            QFrame#visionResultCard {
                background: rgba(14, 27, 44, 228);
                border: 1px solid rgba(95, 206, 235, 175);
                border-radius: 9px;
            }

            QLabel#resultKind {
                color: #f5e650;
                font-size: 10px;
                font-weight: 700;
            }

            QLabel#resultText {
                color: #edf5ff;
                font-size: 11px;
                font-weight: 600;
            }

            QLabel#resultDetail {
                color: #9ccbea;
                font-size: 9px;
                font-weight: 700;
            }

            QPushButton {
                background: #18233b;
                border: 1px solid #314765;
                border-radius: 8px;
                color: #eaf2ff;
                font-size: 11px;
                font-weight: 700;
                padding: 8px 10px;
            }

            QPushButton:hover {
                background: #223555;
                border-color: #f5e650;
            }

            QPushButton:disabled {
                color: #65718a;
                border-color: #243044;
                background: #101621;
            }
            """
        )

        layout = QVBoxLayout(self)
        self._layout = layout
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        self.header_widget = QFrame()
        header = QHBoxLayout(self.header_widget)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self.title_label = QLabel("AVENS VISION")
        self.title_label.setObjectName("visionTitle")

        self.mode_label = QLabel("LOCAL · VISION READY")
        self.mode_label.setObjectName("visionMode")
        self.mode_label.setAlignment(Qt.AlignCenter)
        self.mode_label.setMaximumWidth(300)

        self.status_label = QLabel("● STANDBY")
        self.status_label.setObjectName("visionStatus")
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_label.setMinimumWidth(112)

        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.mode_label)
        header.addWidget(self.status_label)
        layout.addWidget(self.header_widget)

        self.camera_feed = QLabel("Camera is offline")
        self.camera_feed.setObjectName("cameraFeed")
        self.camera_feed.setAlignment(Qt.AlignCenter)
        self.camera_feed.setMinimumSize(634, 336)
        layout.addWidget(self.camera_feed)

        self.scan_progress = QProgressBar()
        self.scan_progress.setObjectName("scanProgress")
        self.scan_progress.setRange(0, 100)
        self.scan_progress.setValue(0)
        self.scan_progress.setTextVisible(False)
        self.scan_progress.hide()
        layout.addWidget(self.scan_progress)

        self.result_widget = QFrame()
        self.result_widget.setObjectName("visionResultCard")
        self.result_widget.setMinimumHeight(54)
        self.result_widget.setMaximumHeight(62)

        result_layout = QVBoxLayout(self.result_widget)
        result_layout.setContentsMargins(10, 7, 10, 7)
        result_layout.setSpacing(3)

        result_header = QHBoxLayout()
        result_header.setContentsMargins(0, 0, 0, 0)
        result_header.setSpacing(8)

        self.result_kind_label = QLabel("RESULT")
        self.result_kind_label.setObjectName("resultKind")

        self.result_detail_label = QLabel()
        self.result_detail_label.setObjectName("resultDetail")
        self.result_detail_label.setAlignment(
            Qt.AlignRight | Qt.AlignVCenter
        )
        self.result_detail_label.setMaximumWidth(220)
        self.result_detail_label.hide()

        result_header.addWidget(self.result_kind_label)
        result_header.addStretch(1)
        result_header.addWidget(self.result_detail_label)

        self.result_text_label = QLabel()
        self.result_text_label.setObjectName("resultText")
        self.result_text_label.setWordWrap(True)
        self.result_text_label.setMaximumHeight(30)

        result_layout.addLayout(result_header)
        result_layout.addWidget(self.result_text_label)

        self.result_widget.hide()
        layout.addWidget(self.result_widget)

        self.telemetry_widget = QFrame()
        telemetry_row = QHBoxLayout(self.telemetry_widget)
        telemetry_row.setContentsMargins(0, 0, 0, 0)
        telemetry_row.setSpacing(8)

        self.gesture_label = QLabel("GESTURE: NO HAND DETECTED")
        self.gesture_label.setObjectName("gestureLabel")

        self.scan_label = QLabel("SCAN: IDLE")
        self.scan_label.setObjectName("scanLabel")
        self.scan_label.setAlignment(Qt.AlignCenter)

        self.meta_label = QLabel("HANDS: 0 | FPS: 0")
        self.meta_label.setObjectName("metaLabel")
        self.meta_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        telemetry_row.addWidget(self.gesture_label)
        telemetry_row.addStretch(1)
        telemetry_row.addWidget(self.scan_label)
        telemetry_row.addWidget(self.meta_label)
        layout.addWidget(self.telemetry_widget)

        self.controls_widget = QFrame()
        controls = QHBoxLayout(self.controls_widget)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(7)

        self.start_button = QPushButton("START CAMERA")
        self.stop_button = QPushButton("STOP CAMERA")
        self.guide_button = QPushButton("HIDE GUIDE")
        self.hud_button = QPushButton("MINIMAL HUD")
        self.motion_button = QPushButton("MOTION: FULL")

        self.stop_button.setEnabled(False)

        self.start_button.clicked.connect(self.request_start)
        self.stop_button.clicked.connect(self.request_stop)
        self.guide_button.clicked.connect(self.toggle_guide)
        self.hud_button.clicked.connect(self.toggle_hud_mode)
        self.motion_button.clicked.connect(self.toggle_reduced_motion)

        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.guide_button)
        controls.addWidget(self.hud_button)
        controls.addWidget(self.motion_button)
        controls.addStretch(1)
        layout.addWidget(self.controls_widget)

        self._sync_guide_button()
        self._sync_hud_button()
        self._sync_motion_button()

    def set_fullscreen_mode(self, enabled: bool) -> None:
        """Switch between dashboard view and camera-only fullscreen."""
        if self._fullscreen_mode == enabled:
            return

        self._fullscreen_mode = enabled

        if enabled:
            self.setMinimumSize(1, 1)
            self.setMaximumSize(16_777_215, 16_777_215)

            self.header_widget.hide()
            self.scan_progress.hide()
            self.result_widget.hide()
            self.telemetry_widget.hide()
            self.controls_widget.hide()

            self.camera_feed.setMinimumSize(1, 1)
            self.camera_feed.setSizePolicy(
                QSizePolicy.Expanding,
                QSizePolicy.Expanding,
            )
            self._layout.setContentsMargins(18, 18, 18, 18)

            if self.parentWidget() is not None:
                self.setGeometry(self.parentWidget().rect())
        else:
            self.header_widget.show()
            self.telemetry_widget.show()
            self.controls_widget.show()

            self.camera_feed.setMinimumSize(634, 336)
            self.camera_feed.setSizePolicy(
                QSizePolicy.Preferred,
                QSizePolicy.Preferred,
            )

            self._layout.setContentsMargins(18, 16, 18, 16)
            self.setFixedSize(670, 545)
            self.move(418, 20)

        self._sync_runtime_labels()

    def sync_requested_state(self) -> None:
        """Keep the camera and buttons synced with voice commands."""
        requested = is_vision_requested()
        has_worker = self.worker is not None

        if requested and not has_worker:
            self.start_camera()
        elif not requested and has_worker:
            self.stop_camera()

        self._sync_guide_button()
        self._sync_hud_button()
        self._sync_runtime_labels()

    def toggle_guide(self) -> None:
        """Toggle the on-camera gesture legend."""
        set_vision_guide_visible(not is_vision_guide_visible())
        self._sync_guide_button()

    def toggle_hud_mode(self) -> None:
        """Toggle between the detailed and minimal camera overlay."""
        next_mode = (
            "MINIMAL"
            if get_vision_hud_mode() == "STANDARD"
            else "STANDARD"
        )
        set_vision_hud_mode(next_mode)
        self._sync_hud_button()

    def toggle_reduced_motion(self) -> None:
        """Set a UI-only preference for calmer vision animations."""
        self._reduced_motion = not self._reduced_motion
        self._sync_motion_button()

    def is_reduced_motion_enabled(self) -> bool:
        """Return the UI-only motion preference used by the orb renderer."""
        return self._reduced_motion

    def _sync_hud_button(self) -> None:
        """Reflect the current HUD mode in the dashboard button."""
        self.hud_button.setText(
            "STANDARD HUD"
            if get_vision_hud_mode() == "MINIMAL"
            else "MINIMAL HUD"
        )

    def _sync_guide_button(self) -> None:
        """Keep the button label honest about the current guide state."""
        self.guide_button.setText(
            "HIDE GUIDE"
            if is_vision_guide_visible()
            else "SHOW GUIDE"
        )

    def _sync_motion_button(self) -> None:
        """Display the actual UI motion preference."""
        self.motion_button.setText(
            "MOTION: REDUCED"
            if self._reduced_motion
            else "MOTION: FULL"
        )

    def _sync_runtime_labels(self) -> None:
        """Render current camera mode and scan state without changing them."""
        snapshot = mode_controller.snapshot()

        if snapshot.camera_mode == "online":
            mode_text = "ONLINE · GOOGLE LENS"
            mode_tip = (
                "Online camera mode. Lens Scan uses SerpApi Google Lens "
                "through a temporary Cloudinary upload."
            )
        else:
            mode_text = f"LOCAL · {FAST_MODEL_NAME} / {DEEP_MODEL_NAME}"
            mode_tip = (
                "Offline camera mode using the configured local Ollama "
                "vision models."
            )

        self.mode_label.setText(mode_text)
        self.mode_label.setToolTip(mode_tip)

        scan_state = get_vision_scan_state()
        scan_progress = get_vision_scan_progress()

        if scan_state:
            self.scan_label.setText(f"SCAN: {scan_state}")
        elif self.worker is not None:
            self.scan_label.setText("SCAN: READY")
        else:
            self.scan_label.setText("SCAN: IDLE")

        show_progress = (
            not self._fullscreen_mode
            and scan_progress is not None
        )
        self.scan_progress.setVisible(show_progress)

        if scan_progress is not None:
            self.scan_progress.setValue(round(scan_progress * 100))
        self._sync_result_card()

    def _sync_result_card(self) -> None:
        """Render one completed camera result without changing camera state."""
        result = get_latest_vision_result()

        if result is None or self._fullscreen_mode:
            self.result_widget.hide()
            return

        kind_labels = {
            "local_identify": "RESULT · LOCAL IDENTIFY",
            "local_describe": "RESULT · LOCAL DESCRIBE",
            "local_read": "RESULT · LOCAL READ",
            "online_google_lens": "RESULT · ONLINE GOOGLE LENS",
        }

        self.result_kind_label.setText(
            kind_labels.get(result.kind, "RESULT")
        )
        self.result_text_label.setText(
            self._compact_result_text(result.text, 180)
        )
        self.result_text_label.setToolTip(result.text)

        if result.detail:
            detail = self._compact_result_text(result.detail, 72)
            self.result_detail_label.setText(f"SOURCE · {detail}")
            self.result_detail_label.setToolTip(result.detail)
            self.result_detail_label.show()
        else:
            self.result_detail_label.clear()
            self.result_detail_label.hide()

        if result.kind == "online_google_lens":
            self.result_widget.setToolTip(
                "Online Google Lens visual match. "
                "Treat the exact model as unconfirmed."
            )
        else:
            self.result_widget.setToolTip(
                "Completed local camera analysis."
            )

        self.result_widget.show()


    @staticmethod
    def _compact_result_text(value: str, limit: int) -> str:
        """Keep one UI result concise without changing the spoken answer."""
        normalised = " ".join(str(value or "").split())

        if len(normalised) <= limit:
            return normalised

        shortened = normalised[:limit].rsplit(" ", 1)[0]
        shortened = shortened or normalised[:limit]

        return f"{shortened}..."

    def request_start(self) -> None:
        start_vision()
        self.start_camera()

    def request_stop(self) -> None:
        stop_vision()
        self.stop_camera()

    def start_camera(self) -> None:
        if self.worker is not None:
            return

        self._set_status("● STARTING CAMERA")
        self.gesture_label.setText("GESTURE: WAITING FOR CAMERA")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        self.worker = VisionWorker(parent=self)
        self.worker.frame_ready.connect(self._update_frame)
        self.worker.telemetry_ready.connect(self._update_telemetry)
        self.worker.camera_error.connect(self._show_camera_error)
        self.worker.camera_started.connect(self._on_camera_started)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

        self._sync_runtime_labels()

    def stop_camera(self) -> None:
        if self.worker is None:
            self._set_standby()
            return

        self._set_status("● STOPPING CAMERA")
        self.worker.stop()

    def _update_frame(self, image: QImage) -> None:
        pixmap = QPixmap.fromImage(image)
        scaled = pixmap.scaled(
            self.camera_feed.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.camera_feed.setPixmap(scaled)

    def _update_telemetry(self, telemetry: dict) -> None:
        gesture = telemetry.get("gesture", "NO HAND DETECTED")
        hands = telemetry.get("hands_detected", 0)
        fps = telemetry.get("fps", 0.0)
        last_action = telemetry.get("last_action")
        controls_locked = telemetry.get("controls_locked", False)

        gesture_text = f"GESTURE: {gesture}"
        if last_action:
            gesture_text = f"{gesture_text} · {last_action}"

        meta_parts = [f"HANDS: {hands}", f"FPS: {fps:.0f}"]
        if controls_locked:
            meta_parts.append("LOCKED")

        self.gesture_label.setText(gesture_text)
        self.meta_label.setText(" | ".join(meta_parts))

    def _on_camera_started(self) -> None:
        self._set_status("● CAMERA ONLINE")
        self._sync_runtime_labels()

    def _show_camera_error(self, message: str) -> None:
        self._set_status("● CAMERA ERROR")
        self.camera_feed.setText(f"Camera error\n{message}")
        self.gesture_label.setText("GESTURE: UNAVAILABLE")
        self.scan_label.setText("SCAN: UNAVAILABLE")
        self.scan_progress.hide()

    def _on_worker_finished(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()

        self.worker = None
        self._set_standby()

    def _set_standby(self) -> None:
        self._set_status("● STANDBY")
        self.camera_feed.setPixmap(QPixmap())
        self.camera_feed.setText("Camera is offline")
        self.gesture_label.setText("GESTURE: NO HAND DETECTED")
        self.meta_label.setText("HANDS: 0 | FPS: 0")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self._sync_runtime_labels()

    def _set_status(self, status: str) -> None:
        self._last_status = status
        self.status_label.setText(status)

    def shutdown(self) -> None:
        """Ask the worker to stop before the parent window is destroyed."""
        self._runtime_timer.stop()
        stop_vision()
        self.stop_camera()