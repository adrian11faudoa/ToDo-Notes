"""
widgets/splash_screen.py
────────────────────────
Animated startup splash screen shown while the database and
services initialize. Auto-closes after init completes.
"""

from __future__ import annotations
from PySide6.QtWidgets import QSplashScreen, QWidget, QLabel, QVBoxLayout, QProgressBar
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient, QBrush


class SplashScreen(QSplashScreen):
    """
    Minimal frameless splash shown at startup.
    Call set_progress(0–100) to advance the bar.
    Call finish() to fade out.
    """

    def __init__(self):
        # Create a pixmap programmatically (no image file needed)
        px = self._make_pixmap(480, 280)
        super().__init__(px, Qt.WindowStaysOnTopHint)
        self.setWindowFlag(Qt.FramelessWindowHint)

    def _make_pixmap(self, w: int, h: int) -> QPixmap:
        px = QPixmap(w, h)
        px.fill(Qt.transparent)

        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)

        # Background gradient
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0.0, QColor("#1A1A2E"))
        grad.setColorAt(1.0, QColor("#16213E"))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, w, h, 16, 16)

        # Logo icon
        p.setFont(QFont("Segoe UI", 48))
        p.setPen(QColor("#4A9EFF"))
        p.drawText(0, 0, w, 160, Qt.AlignCenter, "✦")

        # App name
        p.setFont(QFont("Segoe UI", 28, QFont.Bold))
        p.setPen(QColor("#F0F0F8"))
        p.drawText(0, 120, w, 60, Qt.AlignCenter, "NoteFlow")

        # Tagline
        p.setFont(QFont("Segoe UI", 13))
        p.setPen(QColor("#6A6A8A"))
        p.drawText(0, 172, w, 30, Qt.AlignCenter, "Your offline notes & tasks hub")

        # Version
        p.setFont(QFont("Segoe UI", 10))
        p.setPen(QColor("#444458"))
        p.drawText(0, h - 24, w, 20, Qt.AlignCenter, "v1.0.0")

        p.end()
        return px

    def set_message(self, msg: str):
        self.showMessage(
            msg,
            Qt.AlignBottom | Qt.AlignHCenter,
            QColor("#6A6A8A"),
        )
