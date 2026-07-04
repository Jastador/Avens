"""Embedded PyQt vision dashboard for Avens."""

from __future__ import annotations

import time

import cv2
from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap

from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from core.vision import (
    HandVisionProcessor,
    get_vision_hud_mode,
    is_vision_guide_visible,
    is_vision_requested,
    set_vision_guide_visible,
    set_vision_hud_mode,
    start_vision,
    stop_vision,
)

from core.live_frame_buffer import live_frame_buffer

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
        self._build_ui()

    def _build_ui(self) -> None:
        self.setObjectName("visionDashboard")
        self.setFixedSize(670, 485)
        self.setStyleSheet(
            """
            QFrame#visionDashboard {
                background: rgba(10, 14, 24, 245);
                border: 1px solid #e6b94a;
                border-radius: 18px;
            }
            QLabel#visionTitle {
                color: #f5e650;
                font-size: 17px;
                font-weight: 700;
                letter-spacing: 1px;
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
            QPushButton {
                background: #18233b;
                border: 1px solid #314765;
                border-radius: 8px;
                color: #eaf2ff;
                font-size: 12px;
                font-weight: 700;
                padding: 8px 14px;
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
        layout.setSpacing(10)

        self.header_widget = QFrame()

        header = QHBoxLayout(self.header_widget)
        header.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel("AVENS VISION")
        self.title_label.setObjectName("visionTitle")
        self.status_label = QLabel("● STANDBY")
        self.status_label.setObjectName("visionStatus")
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.status_label)
        layout.addWidget(self.header_widget)

        self.camera_feed = QLabel("Camera is offline")
        self.camera_feed.setObjectName("cameraFeed")
        self.camera_feed.setAlignment(Qt.AlignCenter)
        self.camera_feed.setMinimumSize(634, 356)
        layout.addWidget(self.camera_feed)

        self.telemetry_widget = QFrame()

        telemetry_row = QHBoxLayout(self.telemetry_widget)
        telemetry_row.setContentsMargins(0, 0, 0, 0)
        self.gesture_label = QLabel("GESTURE: NO HAND DETECTED")
        self.gesture_label.setObjectName("gestureLabel")
        self.meta_label = QLabel("HANDS: 0  |  FPS: 0")
        self.meta_label.setObjectName("metaLabel")
        self.meta_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        telemetry_row.addWidget(self.gesture_label)
        telemetry_row.addStretch(1)
        telemetry_row.addWidget(self.meta_label)
        layout.addWidget(self.telemetry_widget)

        self.controls_widget = QFrame()

        controls = QHBoxLayout(self.controls_widget)
        controls.setContentsMargins(0, 0, 0, 0)

        self.guide_button = QPushButton("HIDE GUIDE")
        self.guide_button.clicked.connect(self.toggle_guide)

        self.hud_button = QPushButton("MINIMAL HUD")
        self.hud_button.clicked.connect(self.toggle_hud_mode)

        self.start_button = QPushButton("START CAMERA")
        self.stop_button = QPushButton("STOP CAMERA")
        self.stop_button.setEnabled(False)

        self.start_button.clicked.connect(self.request_start)
        self.stop_button.clicked.connect(self.request_stop)

        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.guide_button)
        controls.addWidget(self.hud_button)
        controls.addStretch(1)

        layout.addWidget(self.controls_widget)
        self._sync_guide_button()
        self._sync_hud_button()

    def set_fullscreen_mode(self, enabled: bool) -> None:
        """Switch between dashboard view and camera-only fullscreen."""
        if self._fullscreen_mode == enabled:
            return

        self._fullscreen_mode = enabled

        if enabled:
            self.setMinimumSize(1, 1)
            self.setMaximumSize(16_777_215, 16_777_215)

            self.header_widget.hide()
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

            self.camera_feed.setMinimumSize(634, 356)
            self.camera_feed.setSizePolicy(
                QSizePolicy.Preferred,
                QSizePolicy.Preferred,
            )

            self._layout.setContentsMargins(18, 16, 18, 16)

            self.setFixedSize(670, 485)
            self.move(418, 20)
    
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
        self.gesture_label.setText(f"GESTURE: {gesture}")
        self.meta_label.setText(f"HANDS: {hands}  |  FPS: {fps:.0f}")

    def _on_camera_started(self) -> None:
        self._set_status("● CAMERA ONLINE")

    def _show_camera_error(self, message: str) -> None:
        self._set_status("● CAMERA ERROR")
        self.camera_feed.setText(f"Camera error\n{message}")
        self.gesture_label.setText("GESTURE: UNAVAILABLE")

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
        self.meta_label.setText("HANDS: 0  |  FPS: 0")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def _set_status(self, status: str) -> None:
        self._last_status = status
        self.status_label.setText(status)

    def shutdown(self) -> None:
        """Ask the worker to stop before the parent window is destroyed."""
        stop_vision()
        self.stop_camera()
