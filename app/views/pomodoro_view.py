"""
views/pomodoro_view.py
──────────────────────
Pomodoro timer with animated circular progress ring,
session management, and task linking.
"""

from __future__ import annotations
import math
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QSpinBox, QFrame,
)
from PySide6.QtCore import Qt, QTimer, Signal, QRectF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont,
    QConicalGradient, QLinearGradient,
)

from app.themes.theme_manager import theme
from app.services.notification_service import notification_service
from app.services.task_service import task_service
from app.config.settings_manager import settings_manager


# ──────────────────────────────────────────────────────────────────
# CIRCULAR TIMER WIDGET
# ──────────────────────────────────────────────────────────────────

class CircularTimer(QWidget):
    """Animated circular progress ring showing remaining time."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(240, 240)
        self._progress = 1.0    # 0.0 → 1.0
        self._time_str = "25:00"
        self._session_type = "work"
        self._running = False

        TYPE_COLORS = {
            "work":        "#FF6B6B",
            "short_break": "#4CAF50",
            "long_break":  "#4A9EFF",
        }
        self._color = TYPE_COLORS.get(self._session_type, theme.t("accent"))

    def set_state(self, progress: float, time_str: str,
                  session_type: str, running: bool):
        self._progress = max(0.0, min(1.0, progress))
        self._time_str = time_str
        self._session_type = session_type
        self._running = running
        TYPE_COLORS = {
            "work":        "#FF6B6B",
            "short_break": "#4CAF50",
            "long_break":  "#4A9EFF",
        }
        self._color = TYPE_COLORS.get(session_type, theme.t("accent"))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        margin = 16
        rect = QRectF(margin, margin, w - 2 * margin, h - 2 * margin)

        # Background ring
        pen = QPen(QColor(theme.t("surface_border")), 12, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 0, 360 * 16)

        # Progress arc (starts at top, goes clockwise)
        if self._progress > 0:
            arc_pen = QPen(QColor(self._color), 12, Qt.SolidLine, Qt.RoundCap)
            p.setPen(arc_pen)
            span = int(self._progress * 360 * 16)
            p.drawArc(rect, 90 * 16, -span)

        # Dot at the tip of the arc
        if self._progress > 0:
            angle_rad = math.radians(90 - self._progress * 360)
            cx = w / 2 + (w / 2 - margin) * math.cos(angle_rad)
            cy = h / 2 - (h / 2 - margin) * math.sin(angle_rad)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(self._color)))
            p.drawEllipse(QRectF(cx - 7, cy - 7, 14, 14))

        # Center time text
        p.setPen(QPen(QColor(theme.t("text_primary"))))
        time_font = QFont("Segoe UI", 36, QFont.Bold)
        p.setFont(time_font)
        p.drawText(rect, Qt.AlignCenter, self._time_str)

        # Session type label below time
        label_map = {
            "work": "FOCUS", "short_break": "SHORT BREAK", "long_break": "LONG BREAK"
        }
        label = label_map.get(self._session_type, "FOCUS")
        label_font = QFont("Segoe UI", 9, QFont.Bold)
        p.setFont(label_font)
        p.setPen(QPen(QColor(self._color)))
        sub_rect = QRectF(margin, rect.center().y() + 24, w - 2 * margin, 30)
        p.drawText(sub_rect, Qt.AlignCenter, label)


# ──────────────────────────────────────────────────────────────────
# POMODORO VIEW
# ──────────────────────────────────────────────────────────────────

class PomodoroView(QWidget):
    """
    Full Pomodoro timer view.
    Work → Short Break → Work → Short Break → Work → Long Break (cycle of 4)
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        s = settings_manager
        self._work_secs = s.get_int("pomodoro_work", 1500)
        self._short_secs = s.get_int("pomodoro_short_break", 300)
        self._long_secs = s.get_int("pomodoro_long_break", 900)

        self._session_order = ["work", "short_break", "work", "short_break",
                                "work", "short_break", "work", "long_break"]
        self._session_idx = 0
        self._completed_sessions = 0

        self._current_type = "work"
        self._total_secs = self._work_secs
        self._remaining = self._work_secs
        self._running = False

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._tick)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(24)

        # Title
        title = QLabel("🍅 Pomodoro Timer")
        title.setFont(QFont("Segoe UI", 20, QFont.DemiBold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("background: transparent;")
        layout.addWidget(title)

        # Session type buttons
        type_row = QHBoxLayout()
        type_row.setSpacing(8)
        type_row.setAlignment(Qt.AlignCenter)

        for label, stype in [("Focus", "work"), ("Short Break", "short_break"), ("Long Break", "long_break")]:
            btn = QPushButton(label)
            btn.setFixedHeight(32)
            btn.setCheckable(True)
            btn.setChecked(stype == "work")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, t=stype, b=btn: self._switch_type(t))
            type_row.addWidget(btn)

        layout.addLayout(type_row)

        # Timer ring
        self._ring = CircularTimer()
        layout.addWidget(self._ring, alignment=Qt.AlignCenter)

        # Session counter
        self._session_lbl = QLabel("Session 1 of 4")
        self._session_lbl.setFont(QFont("Segoe UI", 12))
        self._session_lbl.setAlignment(Qt.AlignCenter)
        self._session_lbl.setStyleSheet(
            f"color: {theme.t('text_tertiary')}; background: transparent;"
        )
        layout.addWidget(self._session_lbl)

        # Control buttons
        controls = QHBoxLayout()
        controls.setSpacing(12)
        controls.setAlignment(Qt.AlignCenter)

        self._reset_btn = QPushButton("↺")
        self._reset_btn.setFixedSize(44, 44)
        self._reset_btn.setFont(QFont("Segoe UI", 18))
        self._reset_btn.setToolTip("Reset")
        self._reset_btn.clicked.connect(self._reset)

        self._start_btn = QPushButton("▶ Start")
        self._start_btn.setObjectName("PrimaryButton")
        self._start_btn.setFixedSize(120, 44)
        self._start_btn.setFont(QFont("Segoe UI", 14))
        self._start_btn.clicked.connect(self._toggle_start)

        self._skip_btn = QPushButton("⏭")
        self._skip_btn.setFixedSize(44, 44)
        self._skip_btn.setFont(QFont("Segoe UI", 18))
        self._skip_btn.setToolTip("Skip to next")
        self._skip_btn.clicked.connect(self._skip)

        controls.addWidget(self._reset_btn)
        controls.addWidget(self._start_btn)
        controls.addWidget(self._skip_btn)
        layout.addLayout(controls)

        # Task link
        task_row = QHBoxLayout()
        task_row.setSpacing(8)
        task_row.setAlignment(Qt.AlignCenter)

        task_lbl = QLabel("Linked task:")
        task_lbl.setFont(QFont("Segoe UI", 12))
        task_lbl.setStyleSheet(f"color: {theme.t('text_secondary')}; background: transparent;")

        self._task_combo = QComboBox()
        self._task_combo.setFixedWidth(280)
        self._task_combo.addItem("— No task linked —", None)
        for task in task_service.get_today_tasks():
            self._task_combo.addItem(task.title, task.id)

        task_row.addWidget(task_lbl)
        task_row.addWidget(self._task_combo)
        layout.addLayout(task_row)

        # Stats
        stats_frame = QFrame()
        stats_frame.setObjectName("Card")
        stats_frame.setFixedWidth(360)
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(20, 12, 20, 12)
        stats_layout.setSpacing(24)

        self._completed_lbl = self._stat("🍅 Completed", "0")
        self._focus_time_lbl = self._stat("⏱ Focus time", "0 min")

        stats_layout.addWidget(self._completed_lbl)
        stats_layout.addWidget(self._focus_time_lbl)
        layout.addWidget(stats_frame, alignment=Qt.AlignCenter)

        self._update_ring()

    def _stat(self, label: str, value: str) -> QWidget:
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setSpacing(2)
        val = QLabel(value)
        val.setFont(QFont("Segoe UI", 18, QFont.Bold))
        val.setAlignment(Qt.AlignCenter)
        val.setStyleSheet("background: transparent;")
        lbl = QLabel(label)
        lbl.setFont(QFont("Segoe UI", 10))
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"color: {theme.t('text_tertiary')}; background: transparent;")
        vl.addWidget(val)
        vl.addWidget(lbl)
        # Store refs
        w._val_lbl = val
        w._lbl_lbl = lbl
        return w

    # ── Timer logic ───────────────────────────────────────────────

    def _toggle_start(self):
        if self._running:
            self._pause()
        else:
            self._start()

    def _start(self):
        self._running = True
        self._start_btn.setText("⏸ Pause")
        self._tick_timer.start()

    def _pause(self):
        self._running = False
        self._start_btn.setText("▶ Resume")
        self._tick_timer.stop()

    def _reset(self):
        self._tick_timer.stop()
        self._running = False
        self._remaining = self._total_secs
        self._start_btn.setText("▶ Start")
        self._update_ring()

    def _skip(self):
        self._tick_timer.stop()
        self._running = False
        self._start_btn.setText("▶ Start")
        self._advance_session()

    def _tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._session_complete()
        else:
            self._update_ring()

    def _session_complete(self):
        self._tick_timer.stop()
        self._running = False

        if self._current_type == "work":
            self._completed_sessions += 1
            self._completed_lbl._val_lbl.setText(str(self._completed_sessions))
            focus_min = self._completed_sessions * (self._work_secs // 60)
            self._focus_time_lbl._val_lbl.setText(f"{focus_min} min")

        notification_service.pomodoro_complete(self._current_type)
        self._advance_session()

    def _advance_session(self):
        self._session_idx = (self._session_idx + 1) % len(self._session_order)
        self._switch_type(self._session_order[self._session_idx])
        work_sessions = (self._session_idx // 2) % 4 + 1
        self._session_lbl.setText(f"Session {work_sessions} of 4")

    def _switch_type(self, stype: str):
        self._current_type = stype
        durations = {
            "work": self._work_secs,
            "short_break": self._short_secs,
            "long_break": self._long_secs,
        }
        self._total_secs = durations[stype]
        self._remaining = self._total_secs
        self._update_ring()

    def _update_ring(self):
        progress = self._remaining / self._total_secs if self._total_secs else 0
        mins, secs = divmod(self._remaining, 60)
        time_str = f"{mins:02d}:{secs:02d}"
        self._ring.set_state(progress, time_str, self._current_type, self._running)
