import math
import random

import numpy as np
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QLinearGradient, QPainter, QPen, QRadialGradient
from PyQt5.QtWidgets import QApplication, QWidget

from core.vision import (
    get_vision_scan_progress,
    get_vision_scan_state,
    is_vision_fullscreen_requested,
    is_vision_requested,
)

from ui.vision_dashboard import VisionDashboard
from ui.visualizer import audio_instance


class Orb(QWidget):
    """Avens' floating orb plus its expandable Vision Dashboard."""

    COMPACT_SIZE = (400, 400)
    VISION_SIZE = (1110, 585)

    def __init__(self, shared_state):
        super().__init__()
        self.shared_state = shared_state
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(*self.COMPACT_SIZE)
        self._center_on_screen()

        self.audio = audio_instance
        self.time = 0.0
        self._vision_mode = False
        self._vision_fullscreen = False

        # The dashboard is a child of this same PyQt window, not an OpenCV pop-up.
        self.vision_dashboard = VisionDashboard(self)
        self.vision_dashboard.move(418, 20)
        self.vision_dashboard.hide()

        # Generate base 3D sphere vertices.
        self.lats = 22
        self.lons = 26
        self.base_sphere = []
        for i in range(self.lats + 1):
            lat = math.pi * i / self.lats
            row = []
            for j in range(self.lons):
                lon = 2 * math.pi * j / self.lons
                x = math.sin(lat) * math.cos(lon)
                y = math.sin(lat) * math.sin(lon)
                z = math.cos(lat)
                row.append((x, y, z))
            self.base_sphere.append(row)

        # Generate floating particles.
        self.particles = [
            (random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(-1, 1))
            for _ in range(80)
        ]

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(16)

    def _center_on_screen(self) -> None:
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        x = screen_geometry.x() + (screen_geometry.width() - self.width()) // 2
        y = screen_geometry.y() + (screen_geometry.height() - self.height()) // 2
        self.move(x, y)

    def _resize_around_current_center(self, width: int, height: int) -> None:
        current_center = self.geometry().center()
        self.resize(width, height)
        self.move(current_center.x() - width // 2, current_center.y() - height // 2)

    def _set_vision_fullscreen(self, enabled: bool) -> None:
        if self._vision_fullscreen == enabled:
            return

        self._vision_fullscreen = enabled

        if enabled:
            screen = QApplication.primaryScreen()
            self.setGeometry(screen.geometry())

            self.vision_dashboard.set_fullscreen_mode(True)
            self.vision_dashboard.setGeometry(self.rect())

            self.raise_()

        else:
            self.vision_dashboard.set_fullscreen_mode(False)
            self._resize_around_current_center(*self.VISION_SIZE)
            self.vision_dashboard.move(418, 20)


    def _sync_vision_mode(self) -> None:
        requested = is_vision_requested()
        fullscreen_requested = (
            requested and is_vision_fullscreen_requested()
        )

        if requested != self._vision_mode:
            self._vision_mode = requested

            if requested:
                self._resize_around_current_center(*self.VISION_SIZE)

                self.vision_dashboard.set_fullscreen_mode(False)
                self.vision_dashboard.show()
                self.vision_dashboard.sync_requested_state()

            else:
                if self._vision_fullscreen:
                    self._set_vision_fullscreen(False)

                self.vision_dashboard.shutdown()
                self.vision_dashboard.hide()
                self._resize_around_current_center(*self.COMPACT_SIZE)
                return

        if not requested:
            return

        if fullscreen_requested != self._vision_fullscreen:
            self._set_vision_fullscreen(fullscreen_requested)

        self.vision_dashboard.sync_requested_state()

    def animate(self):
        self.time += 0.03
        self._sync_vision_mode()

        is_visible = self.shared_state.get("visible", True)
        if is_visible and self.isHidden():
            self.show()
        elif not is_visible and not self.isHidden():
            self.hide()
        self.update()

    def mousePressEvent(self, event):
        self.old_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        delta = event.globalPos() - self.old_pos
        self.move(self.x() + delta.x(), self.y() + delta.y())
        self.old_pos = event.globalPos()

    def closeEvent(self, event):
        self.vision_dashboard.shutdown()
        super().closeEvent(event)

    def paintEvent(self, event):
        if self._vision_fullscreen:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()
        center_x = 205 if self._vision_mode else width // 2
        center_y = height // 2

        state = self.shared_state.get("state", "idle")
        wave = self.audio.get_wave()
        audio_energy = np.mean(np.abs(wave)) if len(wave) > 0 else 0

        scan_state = get_vision_scan_state() or ""
        raw_scan_progress = get_vision_scan_progress()

        try:
            scan_progress = (
                None
                if raw_scan_progress is None
                else min(max(float(raw_scan_progress), 0.0), 1.0)
            )
        except (TypeError, ValueError):
            scan_progress = None

        scan_active = bool(scan_state) or (
            scan_progress is not None and scan_progress > 0
        )

        reduced_motion = (
            self._vision_mode
            and self.vision_dashboard.is_reduced_motion_enabled()
        )

        motion_scale = 0.18 if reduced_motion else 1.0
        animation_time = self.time * motion_scale

        if self._vision_mode:
            color_one = QColor(245, 185, 45)
            color_two = QColor(74, 169, 255)
        elif state == "listening":
            color_one = QColor(0, 150, 255)
            color_two = QColor(255, 0, 150)
        elif state == "thinking":
            color_one = QColor(150, 0, 255)
            color_two = QColor(0, 255, 255)
        elif state == "speaking":
            color_one = QColor(0, 255, 150)
            color_two = QColor(0, 100, 255)
        else:
            color_one = QColor(0, 80, 150)
            color_two = QColor(100, 0, 100)

        scan_pulse = 0.0
        if self._vision_mode and scan_active and not reduced_motion:
            scan_pulse = (math.sin(animation_time * 4.5) + 1) / 2

        glow_radius = 160 + (audio_energy * 200)
        if self._vision_mode and scan_active:
            glow_radius += 20 + (12 * scan_pulse)

        background_gradient = QRadialGradient(center_x, center_y, glow_radius)
        background_color = QColor(
            color_one.red() // 3,
            color_one.green() // 3,
            color_one.blue() // 3,
            80,
        )
        background_gradient.setColorAt(0, background_color)
        background_gradient.setColorAt(1, QColor(0, 0, 0, 0))

        painter.setBrush(background_gradient)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(
            int(center_x - glow_radius),
            int(center_y - glow_radius),
            int(glow_radius * 2),
            int(glow_radius * 2),
        )

        base_radius = 80
        distance = 350

        # Vision-only reticle. It sits beside the camera feed and reflects
        # genuine scan state without changing capture, inference, or timing.
        if self._vision_mode:
            ring_radius = base_radius + 31 + int(scan_pulse * 7)
            ring_x = int(center_x - ring_radius)
            ring_y = int(center_y - ring_radius)
            ring_diameter = ring_radius * 2

            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(111, 210, 255, 110), 1.0))
            painter.drawEllipse(ring_x, ring_y, ring_diameter, ring_diameter)

            if scan_active:
                arc_start = int((90 - (animation_time * 110)) * 16)
                arc_span = int((82 + (scan_pulse * 38)) * 16)

                painter.setPen(QPen(QColor(245, 230, 80, 225), 2.2))
                painter.drawArc(
                    ring_x,
                    ring_y,
                    ring_diameter,
                    ring_diameter,
                    arc_start,
                    arc_span,
                )

                if scan_progress is not None:
                    progress_radius = ring_radius + 9
                    progress_x = int(center_x - progress_radius)
                    progress_y = int(center_y - progress_radius)
                    progress_diameter = progress_radius * 2

                    painter.setPen(QPen(QColor(95, 220, 255, 205), 2.0))
                    painter.drawArc(
                        progress_x,
                        progress_y,
                        progress_diameter,
                        progress_diameter,
                        90 * 16,
                        -int(scan_progress * 360 * 16),
                    )

        pen_gradient = QLinearGradient(0, 0, width, height)
        pen_gradient.setColorAt(0.0, color_one)
        pen_gradient.setColorAt(1.0, color_two)
        painter.setPen(QPen(pen_gradient, 1.2))

        rotation_multiplier = 1.35 if scan_active and not reduced_motion else 1.0
        rotation_y = animation_time * rotation_multiplier
        rotation_x = animation_time * 0.6 * rotation_multiplier

        cos_y, sin_y = math.cos(rotation_y), math.sin(rotation_y)
        cos_x, sin_x = math.cos(rotation_x), math.sin(rotation_x)

        projected = []

        for i in range(self.lats + 1):
            row_projection = []

            for j in range(self.lons):
                x, y, z = self.base_sphere[i][j]

                wave_index = int(
                    (
                        (i * self.lons + j)
                        / ((self.lats + 1) * self.lons)
                    )
                    * len(wave)
                )
                wave_index = min(len(wave) - 1, max(0, wave_index))

                displacement = abs(wave[wave_index]) * 500
                radius = base_radius + displacement + (audio_energy * 80)

                x *= radius
                y *= radius
                z *= radius

                x_rotated = x * cos_y - z * sin_y
                z_rotated = x * sin_y + z * cos_y
                y_rotated = y * cos_x - z_rotated * sin_x
                z_rotated = y * sin_x + z_rotated * cos_x

                factor = (
                    distance / (distance + z_rotated)
                    if (distance + z_rotated) != 0
                    else 1
                )

                x_projected = center_x + x_rotated * factor
                y_projected = center_y + y_rotated * factor

                row_projection.append((x_projected, y_projected, z_rotated))

            projected.append(row_projection)

        for i in range(self.lats):
            for j in range(self.lons):
                point_one = projected[i][j]
                point_two = projected[i + 1][j]
                point_three = projected[i][(j + 1) % self.lons]

                if point_one[2] < 50:
                    painter.drawLine(
                        int(point_one[0]),
                        int(point_one[1]),
                        int(point_two[0]),
                        int(point_two[1]),
                    )
                    painter.drawLine(
                        int(point_one[0]),
                        int(point_one[1]),
                        int(point_three[0]),
                        int(point_three[1]),
                    )

        painter.setPen(QPen(color_two, 2))

        for particle_x, particle_y, particle_z in self.particles:
            particle_radius = (
                base_radius * 1.5
                + math.sin(animation_time * 2 + particle_x) * 10
            )

            x = particle_x * particle_radius
            y = particle_y * particle_radius
            z = particle_z * particle_radius

            x_rotated = x * cos_y - z * sin_y
            z_rotated = x * sin_y + z * cos_y
            y_rotated = y * cos_x - z_rotated * sin_x
            z_rotated = y * sin_x + z_rotated * cos_x

            if z_rotated < 0:
                factor = distance / (distance + z_rotated)
                x_projected = center_x + x_rotated * factor
                y_projected = center_y + y_rotated * factor
                painter.drawPoint(int(x_projected), int(y_projected))