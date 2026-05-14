"""
widgets/quick_add.py
────────────────────
Floating quick-add popup for rapid note or task creation.
Triggered by Ctrl+Space global shortcut.
Auto-dismisses on focus loss.
"""

from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTabWidget, QWidget,
    QFrame, QApplication,
)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QFont, QKeyEvent

from app.themes.theme_manager import theme
from app.services.note_service import note_service
from app.services.task_service import task_service


class QuickAddPopup(QDialog):
    """
    Borderless floating dialog for quick note/task creation.
    Appears near the cursor, closes on Escape or focus loss.
    """

    note_created = Signal(int)    # note_id
    task_created = Signal(int)    # task_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Dialog |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(440)
        self._build_ui()
        self._position_near_cursor()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Card frame
        card = QFrame()
        card.setObjectName("Card")
        card.setStyleSheet(f"""
            QFrame#Card {{
                background: {theme.t('bg_elevated')};
                border: 1px solid {theme.t('border_default')};
                border-radius: 14px;
            }}
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(12)

        # Header
        hdr = QHBoxLayout()
        logo = QLabel("✦")
        logo.setFont(QFont("Segoe UI", 14))
        logo.setStyleSheet(f"color: {theme.t('accent')}; background: transparent;")
        title = QLabel("Quick Add")
        title.setFont(QFont("Segoe UI", 14, QFont.DemiBold))
        title.setStyleSheet("background: transparent;")
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {theme.t('text_tertiary')}; font-size: 14px;
            }}
            QPushButton:hover {{ color: {theme.t('text_primary')}; }}
        """)
        close_btn.clicked.connect(self.reject)
        hdr.addWidget(logo)
        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(close_btn)
        card_layout.addLayout(hdr)

        # Tabs
        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        # Note tab
        note_tab = QWidget()
        note_tab.setStyleSheet("background: transparent;")
        nl = QVBoxLayout(note_tab)
        nl.setContentsMargins(0, 8, 0, 0)
        nl.setSpacing(10)

        self._note_title = QLineEdit()
        self._note_title.setPlaceholderText("Note title…")
        self._note_title.setFont(QFont("Segoe UI", 13))

        from PySide6.QtWidgets import QTextEdit
        self._note_body = QTextEdit()
        self._note_body.setPlaceholderText("Start writing… (Markdown supported)")
        self._note_body.setFixedHeight(120)
        self._note_body.setFont(QFont("Segoe UI", 12))

        save_note_btn = QPushButton("＋ Create Note")
        save_note_btn.setObjectName("PrimaryButton")
        save_note_btn.setFixedHeight(36)
        save_note_btn.clicked.connect(self._create_note)

        nl.addWidget(self._note_title)
        nl.addWidget(self._note_body)
        nl.addWidget(save_note_btn)
        tabs.addTab(note_tab, "📝 Note")

        # Task tab
        task_tab = QWidget()
        task_tab.setStyleSheet("background: transparent;")
        tl = QVBoxLayout(task_tab)
        tl.setContentsMargins(0, 8, 0, 0)
        tl.setSpacing(10)

        self._task_title = QLineEdit()
        self._task_title.setPlaceholderText("Task title…")
        self._task_title.setFont(QFont("Segoe UI", 13))
        self._task_title.returnPressed.connect(self._create_task)

        from PySide6.QtWidgets import QComboBox, QDateEdit
        from PySide6.QtCore import QDate

        row = QHBoxLayout()
        row.setSpacing(8)

        self._priority_combo = QComboBox()
        self._priority_combo.addItems(["🔴 Urgent", "🟠 High", "🔵 Medium", "⚫ Low"])
        self._priority_combo.setCurrentIndex(2)

        self._due_edit = QDateEdit()
        self._due_edit.setCalendarPopup(True)
        self._due_edit.setDate(QDate.currentDate())
        self._due_edit.setDisplayFormat("MMM dd")

        row.addWidget(self._priority_combo, 1)
        row.addWidget(self._due_edit)

        save_task_btn = QPushButton("＋ Create Task")
        save_task_btn.setObjectName("PrimaryButton")
        save_task_btn.setFixedHeight(36)
        save_task_btn.clicked.connect(self._create_task)

        tl.addWidget(self._task_title)
        tl.addLayout(row)
        tl.addWidget(save_task_btn)
        tabs.addTab(task_tab, "✅ Task")

        card_layout.addWidget(tabs)

        # Hint
        hint = QLabel("Press Esc to close  •  Ctrl+Space to toggle")
        hint.setFont(QFont("Segoe UI", 10))
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(f"color: {theme.t('text_tertiary')}; background: transparent;")
        card_layout.addWidget(hint)

        outer.addWidget(card)
        self._note_title.setFocus()

    def _position_near_cursor(self):
        cursor_pos = QApplication.instance().primaryScreen().availableGeometry().center()
        from PySide6.QtGui import QCursor
        pos = QCursor.pos()
        screen = QApplication.instance().primaryScreen().availableGeometry()
        x = min(pos.x(), screen.right() - self.width() - 20)
        y = min(pos.y() + 20, screen.bottom() - 360)
        self.move(x, y)

    def _create_note(self):
        title = self._note_title.text().strip() or "Quick Note"
        content = self._note_body.toPlainText().strip()
        note = note_service.create_note(title=title)
        if content:
            note_service.update_note(note.id, content=content)
        self.note_created.emit(note.id)
        self.accept()

    def _create_task(self):
        title = self._task_title.text().strip()
        if not title:
            self._task_title.setFocus()
            return
        priority = self._priority_combo.currentIndex() + 1
        from datetime import datetime
        d = self._due_edit.date()
        due = datetime(d.year(), d.month(), d.day())
        task = task_service.create_task(title=title, priority=priority, due_date=due)
        self.task_created.emit(task.id)
        self.accept()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        # Don't auto-close — user may click inside child widgets
        pass
