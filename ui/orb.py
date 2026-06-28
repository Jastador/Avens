import math
import random
import numpy as np
from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtGui import QPainter, QColor, QRadialGradient, QLinearGradient, QPen, QBrush
from PyQt5.QtCore import Qt, QTimer
from ui.visualizer import audio_instance

class Orb(QWidget):
    def __init__(self, shared_state):
        super().__init__()
        self.shared_state = shared_state
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(400, 400)
        
        # 🔥 CENTER ORB ON SCREEN
        screen_geo = QApplication.primaryScreen().availableGeometry()
        center_x = (screen_geo.width() - self.width()) // 2
        center_y = (screen_geo.height() - self.height()) // 2
        self.move(center_x, center_y)
        
        self.audio = audio_instance
        self.time = 0.0
        
        # Generate Base 3D Sphere Vertices
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
            
        # Generate Floating Particles
        self.particles = [(random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(-1, 1)) for _ in range(80)]
        
        # Timer for 60fps animation
        self.timer = QTimer()
        self.timer.timeout.connect(self.animate)
        self.timer.start(16)

    def animate(self):
        self.time += 0.03
        # 🔥 HIDE / SHOW LOGIC
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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w = self.width()
        h = self.height()
        cx = w // 2
        cy = h // 2
        
        state = self.shared_state.get("state", "idle")
        wave = self.audio.get_wave()
        audio_energy = np.mean(np.abs(wave)) if len(wave) > 0 else 0
        
        # 🎨 COLORS (Matching the Reference Image Vibe)
        if state == "listening":
            c1, c2 = QColor(0, 150, 255), QColor(255, 0, 150)  # Neon Blue to Pink
        elif state == "thinking":
            c1, c2 = QColor(150, 0, 255), QColor(0, 255, 255)  # Purple to Cyan
        elif state == "speaking":
            c1, c2 = QColor(0, 255, 150), QColor(0, 100, 255)  # Mint Green to Deep Blue
        else:
            c1, c2 = QColor(0, 80, 150), QColor(100, 0, 100)   # Dim Idle Colors
            
        # 1. SOFT BACKGROUND GLOW
        glow_radius = 160 + (audio_energy * 200)
        bg_gradient = QRadialGradient(cx, cy, glow_radius)
        bg_color = QColor(c1.red()//3, c1.green()//3, c1.blue()//3, 80)
        bg_gradient.setColorAt(0, bg_color)
        bg_gradient.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setBrush(bg_gradient)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(int(cx - glow_radius), int(cy - glow_radius), int(glow_radius*2), int(glow_radius*2))
        
        # 2. SET UP WIREFRAME PEN WITH LINEAR GRADIENT
        pen_gradient = QLinearGradient(0, 0, w, h)
        pen_gradient.setColorAt(0.0, c1)
        pen_gradient.setColorAt(1.0, c2)
        pen = QPen(pen_gradient, 1.2)
        painter.setPen(pen)
        
        # 3. 3D PROJECTION & AUDIO DISPLACEMENT MATH
        rot_y = self.time
        rot_x = self.time * 0.6
        cos_y, sin_y = math.cos(rot_y), math.sin(rot_y)
        cos_x, sin_x = math.cos(rot_x), math.sin(rot_x)
        base_radius = 80
        distance = 350
        projected = []
        
        for i in range(self.lats + 1):
            row_proj = []
            for j in range(self.lons):
                x, y, z = self.base_sphere[i][j]
                
                # Map vertex to a spot on the audio wave array
                wave_idx = int(((i * self.lons + j) / ((self.lats + 1) * self.lons)) * len(wave))
                wave_idx = min(len(wave) - 1, max(0, wave_idx))
                
                # Create the "blob" distortion based on audio
                displacement = abs(wave[wave_idx]) * 500
                r = base_radius + displacement + (audio_energy * 80)
                x *= r
                y *= r
                z *= r
                
                # Rotate Y Axis
                x_rot = x * cos_y - z * sin_y
                z_rot = x * sin_y + z * cos_y
                # Rotate X Axis
                y_rot = y * cos_x - z_rot * sin_x
                z_rot = y * sin_x + z_rot * cos_x
                
                # 2D Projection
                factor = distance / (distance + z_rot) if (distance + z_rot) != 0 else 1
                x_proj = cx + x_rot * factor
                y_proj = cy + y_rot * factor
                row_proj.append((x_proj, y_proj, z_rot))
            projected.append(row_proj)
            
        # 4. DRAW THE WIREFRAME MESH
        for i in range(self.lats):
            for j in range(self.lons):
                p1 = projected[i][j]
                p2 = projected[i+1][j]
                p3 = projected[i][(j+1) % self.lons]
                
                # Only draw lines if they are facing forward (Optional Backface Culling)
                if p1[2] < 50:
                    painter.drawLine(int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1]))
                    painter.drawLine(int(p1[0]), int(p1[1]), int(p3[0]), int(p3[1]))
                    
        # 5. DRAW FLOATING PARTICLES
        painter.setPen(QPen(c2, 2))
        for px, py, pz in self.particles:
            pr = base_radius * 1.5 + math.sin(self.time * 2 + px) * 10
            x = px * pr
            y = py * pr
            z = pz * pr
            
            # Rotate particles
            x_rot = x * cos_y - z * sin_y
            z_rot = x * sin_y + z * cos_y
            y_rot = y * cos_x - z_rot * sin_x
            z_rot = y * sin_x + z_rot * cos_x
            
            if z_rot < 0:  # Only draw front particles
                factor = distance / (distance + z_rot)
                x_proj = cx + x_rot * factor
                y_proj = cy + y_rot * factor
                painter.drawPoint(int(x_proj), int(y_proj))