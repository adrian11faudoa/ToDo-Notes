"""
widgets/common.py
─────────────────
Reusable UI widgets used throughout the app.
Each widget is self-contained and theme-aware.
"""

from __future__ import annotations
from typing import Optional, Callable
from PySide6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout,
    QPushButton, QLineEdit, QFrame, QSizePolicy,
    QGraphicsDropShadowEffect, QScrollArea,
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QPropertyAnimation,
    QEasingCurve, QSize, QPoint, Property,
)
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush,
    QFontMetrics, QPainterPath, QLinearGradient,
)

from app.themes.theme_manager import theme
from app.models.entities import Note, Task, Tag


# ──────────────────────────────────────────────────────────────────
# ICON BUTTON
# ──────────────────────────────────────────────────────────────────

class IconButton(QPushButton):
    """Square icon-only button with hover animation."""

    def __init__(self, icon_text: str, tooltip: str = "", size: int = 32, parent=None):
        super().__init__(icon_text, parent)
        self.setObjectName("IconButton")
        self.setFixedSize(size, size)
        self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)


# ──────────────────────────────────────────────────────────────────
# SEARCH BAR
# ──────────────────────────────────────────────────────────────────

class SearchBar(QLineEdit):
    """
    Animated search bar with debounced search signal.
    Emits search_changed after 300ms of no typing.
    """
    search_changed = Signal(str)

    def __init__(self, placeholder: str = "Search…", parent=None):
        super().__init__(parent)
        self.setObjectName("SearchBar")
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._emit_search)
        self.textChanged.connect(self._debounce.start)

    def _emit_search(self):
        self.search_changed.emit(self.text().strip())


# ──────────────────────────────────────────────────────────────────
# SECTION HEADER
# ──────────────────────────────────────────────────────────────────

class SectionHeader(QLabel):
    """Small uppercase section title."""
    def __init__(self, text: str, parent=None):
        super().__init__(text.upper(), parent)
        self.setObjectName("SectionHeader")


# ──────────────────────────────────────────────────────────────────
# HORIZONTAL DIVIDER
# ──────────────────────────────────────────────────────────────────

class HDivider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Plain)
        self.setFixedHeight(1)


# ──────────────────────────────────────────────────────────────────
# TAG PILL
# ──────────────────────────────────────────────────────────────────

class TagPill(QLabel):
    """Small colored tag badge."""
    clicked = Signal(Tag)

    def __init__(self, tag: Tag, removable: bool = False, parent=None):
        super().__init__(parent)
        self._tag = tag
        self._removable = removable
        text = f"  {tag.name}  " + ("✕ " if removable else "")
        self.setText(text)
        self.setObjectName("TagPill")
        self.setCursor(Qt.PointingHandCursor if removable else Qt.ArrowCursor)

        c = QColor(tag.color)
        bg = f"rgba({c.red()},{c.green()},{c.blue()},40)"
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {tag.color};
                border: 1px solid {tag.color};
                border-radius: 10px;
                padding: 1px 6px;
                font-size: 11px;
                font-weight: 600;
            }}
        """)

    def mousePressEvent(self, event):
        if self._removable:
            self.clicked.emit(self._tag)


# ──────────────────────────────────────────────────────────────────
# COLOR LABEL DOT
# ──────────────────────────────────────────────────────────────────

class ColorDot(QWidget):
    """Small colored circle indicator."""
    def __init__(self, color: str, size: int = 10, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(self._color)))
        p.drawEllipse(0, 0, self.width(), self.height())


# ──────────────────────────────────────────────────────────────────
# NOTE CARD
# ──────────────────────────────────────────────────────────────────

NOTE_COLORS = {
    "red":    "#FF5252",
    "orange": "#FF8C00",
    "yellow": "#FFD93D",
    "green":  "#4CAF50",
    "teal":   "#00BFA5",
    "blue":   "#4A9EFF",
    "purple": "#9B6DFF",
    "pink":   "#FF6B9D",
}


class NoteCard(QWidget):
    """
    Card-style note preview widget.
    Used in the list and grid views.
    """
    clicked = Signal(int)       # note_id
    pin_toggled = Signal(int, bool)
    context_requested = Signal(int, QPoint)

    def __init__(self, note: Note, parent=None):
        super().__init__(parent)
        self._note = note
        self._selected = False
        self.setObjectName("NoteCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        # ── Row 1: Title + pin indicator
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        self._title = QLabel(self._note.title)
        self._title.setFont(QFont("Segoe UI", 13, QFont.DemiBold))
        self._title.setStyleSheet(f"color: {theme.t('text_primary')}; background: transparent;")

        row1.addWidget(self._title, 1)

        if self._note.is_pinned:
            pin = QLabel("📌")
            pin.setFixedWidth(18)
            row1.addWidget(pin)

        if self._note.color_label:
            dot = ColorDot(NOTE_COLORS.get(self._note.color_label,
                                           self._note.color_label), size=8)
            row1.addWidget(dot)

        layout.addLayout(row1)

        # ── Row 2: Preview text
        preview = self._note.preview
        self._preview = QLabel(preview if preview else "No content")
        self._preview.setFont(QFont("Segoe UI", 12))
        self._preview.setStyleSheet(
            f"color: {theme.t('text_secondary')}; background: transparent;"
        )
        self._preview.setWordWrap(True)
        layout.addWidget(self._preview)

        # ── Row 3: Tags + timestamp
        row3 = QHBoxLayout()
        row3.setSpacing(4)

        for tag in self._note.tags[:3]:
            pill = TagPill(tag)
            pill.setFixedHeight(18)
            row3.addWidget(pill)

        row3.addStretch()

        ts = QLabel(self._note.updated_relative)
        ts.setFont(QFont("Segoe UI", 10))
        ts.setStyleSheet(f"color: {theme.t('text_tertiary')}; background: transparent;")
        row3.addWidget(ts)

        layout.addLayout(row3)

        # Color label left border
        if self._note.color_label:
            color = NOTE_COLORS.get(self._note.color_label, self._note.color_label)
            self.setStyleSheet(self.styleSheet() +
                               f"\n#NoteCard {{ border-left: 3px solid {color}; }}")

    def set_selected(self, selected: bool):
        self._selected = selected
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._note.id)
        elif event.button() == Qt.RightButton:
            self.context_requested.emit(self._note.id, event.globalPosition().toPoint())

    def update_note(self, note: Note):
        self._note = note
        self._title.setText(note.title)
        self._preview.setText(note.preview or "No content")


# ──────────────────────────────────────────────────────────────────
# TASK ITEM WIDGET
# ──────────────────────────────────────────────────────────────────

class TaskItemWidget(QWidget):
    """
    Single task row widget with checkbox, title, priority, due date.
    """
    toggled = Signal(int, bool)        # task_id, is_done
    clicked = Signal(int)              # task_id
    context_requested = Signal(int, QPoint)

    def __init__(self, task: Task, show_subtasks: bool = True, parent=None):
        super().__init__(parent)
        self._task = task
        self.setObjectName("TaskItem")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(52 if not task.subtasks else 52 + len(task.subtasks) * 36)
        self._build_ui()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(8, 6, 8, 6)
        main.setSpacing(2)

        row = QHBoxLayout()
        row.setSpacing(10)

        # Checkbox
        self._checkbox = _CircleCheckbox(self._task.is_done, self._task.priority)
        self._checkbox.toggled.connect(lambda v: self.toggled.emit(self._task.id, v))
        row.addWidget(self._checkbox)

        # Title
        col = QVBoxLayout()
        col.setSpacing(2)

        self._title = QLabel(self._task.title)
        font = QFont("Segoe UI", 13)
        if self._task.is_done:
            font.setStrikeOut(True)
        self._title.setFont(font)
        color = theme.t("text_tertiary") if self._task.is_done else theme.t("text_primary")
        self._title.setStyleSheet(f"color: {color}; background: transparent;")
        col.addWidget(self._title)

        # Meta row: project, due, priority
        meta = QHBoxLayout()
        meta.setSpacing(8)

        if self._task.project_name:
            proj = QLabel(f"📁 {self._task.project_name}")
            proj.setFont(QFont("Segoe UI", 10))
            proj.setStyleSheet(f"color: {theme.t('text_tertiary')}; background: transparent;")
            meta.addWidget(proj)

        if self._task.due_date:
            color = theme.t("error") if self._task.is_overdue else theme.t("text_tertiary")
            due = QLabel(f"📅 {self._task.due_label}")
            due.setFont(QFont("Segoe UI", 10))
            due.setStyleSheet(f"color: {color}; background: transparent;")
            meta.addWidget(due)

        for tag in self._task.tags[:2]:
            pill = TagPill(tag)
            pill.setFixedHeight(16)
            meta.addWidget(pill)

        meta.addStretch()
        col.addLayout(meta)
        row.addLayout(col, 1)

        # Priority indicator
        p_color = {1: "#FF4444", 2: "#FF8C00", 3: "#4A9EFF", 4: "#6C6C6C"}.get(
            self._task.priority, "#6C6C6C"
        )
        dot = ColorDot(p_color, size=8)
        row.addWidget(dot)

        main.addLayout(row)

        # Subtasks progress bar
        if self._task.subtasks:
            from PySide6.QtWidgets import QProgressBar
            pb = QProgressBar()
            pb.setFixedHeight(4)
            pb.setRange(0, 100)
            pb.setValue(int(self._task.progress * 100))
            pb.setTextVisible(False)
            main.addWidget(pb)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._task.id)
        elif event.button() == Qt.RightButton:
            self.context_requested.emit(self._task.id, event.globalPosition().toPoint())


class _CircleCheckbox(QWidget):
    """Custom circular checkbox showing priority color."""
    toggled = Signal(bool)

    PRIORITY_COLORS = {1: "#FF4444", 2: "#FF8C00", 3: "#4A9EFF", 4: "#6C6C6C"}

    def __init__(self, checked: bool, priority: int = 3, parent=None):
        super().__init__(parent)
        self._checked = checked
        self._priority = priority
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(self.PRIORITY_COLORS.get(self._priority, "#6C6C6C"))

        if self._checked:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(color))
            p.drawEllipse(1, 1, 20, 20)
            p.setPen(QPen(QColor("white"), 2))
            p.drawLine(6, 11, 10, 15)
            p.drawLine(10, 15, 16, 7)
        else:
            p.setPen(QPen(color, 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(2, 2, 18, 18)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._checked = not self._checked
            self.update()
            self.toggled.emit(self._checked)


# ──────────────────────────────────────────────────────────────────
# EMPTY STATE WIDGET
# ──────────────────────────────────────────────────────────────────

class EmptyState(QWidget):
    """Shown when a list has no items."""

    def __init__(self, icon: str, title: str, subtitle: str,
                 action_label: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)

        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont("Segoe UI", 48))
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent;")

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Segoe UI", 16, QFont.DemiBold))
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet(f"color: {theme.t('text_secondary')}; background: transparent;")

        sub_lbl = QLabel(subtitle)
        sub_lbl.setFont(QFont("Segoe UI", 13))
        sub_lbl.setAlignment(Qt.AlignCenter)
        sub_lbl.setStyleSheet(f"color: {theme.t('text_tertiary')}; background: transparent;")
        sub_lbl.setWordWrap(True)

        layout.addWidget(icon_lbl)
        layout.addWidget(title_lbl)
        layout.addWidget(sub_lbl)

        if action_label:
            self.action_btn = QPushButton(action_label)
            self.action_btn.setObjectName("PrimaryButton")
            self.action_btn.setFixedWidth(160)
            layout.addWidget(self.action_btn, alignment=Qt.AlignCenter)


# ──────────────────────────────────────────────────────────────────
# LOADING SPINNER
# ──────────────────────────────────────────────────────────────────

class LoadingSpinner(QWidget):
    """Animated loading indicator."""

    def __init__(self, size: int = 32, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._size = size
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(16)  # ~60fps

    def _rotate(self):
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(self._size / 2, self._size / 2)
        p.rotate(self._angle)

        pen = QPen(QColor(theme.t("accent")), 3, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(
            -self._size // 2 + 4, -self._size // 2 + 4,
            self._size - 8, self._size - 8,
            0, 270 * 16
        )

    def stop(self):
        self._timer.stop()
        self.hide()


# ──────────────────────────────────────────────────────────────────
# BADGE LABEL
# ──────────────────────────────────────────────────────────────────

class Badge(QLabel):
    def __init__(self, count: int, parent=None):
        super().__init__(str(count) if count > 0 else "", parent)
        self.setObjectName("Badge")
        self.setAlignment(Qt.AlignCenter)
        self.setVisible(count > 0)

    def set_count(self, count: int):
        self.setText(str(count) if count > 0 else "")
        self.setVisible(count > 0)


# ──────────────────────────────────────────────────────────────────
# COLLAPSIBLE SECTION
# ──────────────────────────────────────────────────────────────────

class CollapsibleSection(QWidget):
    """Sidebar section that can be collapsed."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._collapsed = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header button
        self._toggle = QPushButton(f"▾  {title}")
        self._toggle.setObjectName("SectionHeader")
        self._toggle.setCheckable(True)
        self._toggle.clicked.connect(self._on_toggle)
        self._toggle.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {theme.t('text_tertiary')};
                font-size: 11px;
                font-weight: 700;
                text-align: left;
                padding: 8px 16px 4px 16px;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{ color: {theme.t('text_secondary')}; }}
        """)
        outer.addWidget(self._toggle)

        # Content area
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        outer.addWidget(self._content)

    def add_widget(self, widget: QWidget):
        self._content_layout.addWidget(widget)

    def _on_toggle(self, checked: bool):
        self._collapsed = checked
        self._content.setVisible(not checked)
        prefix = "▸" if checked else "▾"
        title = self._toggle.text()[3:]
        self._toggle.setText(f"{prefix}  {title}")
