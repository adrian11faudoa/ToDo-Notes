"""
views/tasks_view.py
───────────────────
Tasks view with three sub-modes:
  • List view  — grouped by project/status
  • Kanban     — drag-aware column board
  • Daily      — today's tasks + planner
"""

from __future__ import annotations
from typing import Optional
from datetime import datetime, date

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSplitter, QTabWidget, QComboBox,
    QLineEdit, QDateEdit, QMenu, QDialog, QFormLayout,
    QDialogButtonBox, QSpinBox, QCheckBox, QTextEdit,
    QSizePolicy, QStackedWidget,
)
from PySide6.QtCore import Qt, Signal, QDate, QTimer, QPoint
from PySide6.QtGui import QFont, QColor

from app.themes.theme_manager import theme
from app.models.entities import Task, Project, Priority, TaskStatus
from app.services.task_service import task_service
from app.widgets.common import (
    TaskItemWidget, EmptyState, SearchBar,
    SectionHeader, IconButton, Badge, HDivider,
)


# ──────────────────────────────────────────────────────────────────
# TASK CREATION DIALOG
# ──────────────────────────────────────────────────────────────────

class TaskDialog(QDialog):
    """Create/Edit task dialog."""

    def __init__(self, task: Optional[Task] = None,
                 default_project_id: Optional[int] = None, parent=None):
        super().__init__(parent)
        self._task = task
        self._projects = task_service.get_all_projects()
        self.setWindowTitle("Edit Task" if task else "New Task")
        self.setFixedWidth(440)
        self.setModal(True)
        self._build_ui(default_project_id)

    def _build_ui(self, default_project_id: Optional[int]):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title_lbl = QLabel("Edit Task" if self._task else "New Task")
        title_lbl.setFont(QFont("Segoe UI", 16, QFont.DemiBold))
        layout.addWidget(title_lbl)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)

        # Title
        self._title_edit = QLineEdit(self._task.title if self._task else "")
        self._title_edit.setPlaceholderText("Task title…")
        self._title_edit.setFont(QFont("Segoe UI", 13))
        form.addRow("Title:", self._title_edit)

        # Description
        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Notes / description…")
        self._desc_edit.setFixedHeight(80)
        self._desc_edit.setFont(QFont("Segoe UI", 12))
        if self._task:
            self._desc_edit.setPlainText(self._task.description)
        form.addRow("Notes:", self._desc_edit)

        # Project
        self._project_combo = QComboBox()
        self._project_combo.addItem("— No project —", None)
        sel_idx = 0
        for i, p in enumerate(self._projects):
            self._project_combo.addItem(p.name, p.id)
            if p.id == (self._task.project_id if self._task else default_project_id):
                sel_idx = i + 1
        self._project_combo.setCurrentIndex(sel_idx)
        form.addRow("Project:", self._project_combo)

        # Priority
        self._priority_combo = QComboBox()
        priorities = [(1, "🔴 Urgent"), (2, "🟠 High"), (3, "🔵 Medium"), (4, "⚫ Low")]
        for val, label in priorities:
            self._priority_combo.addItem(label, val)
        current_p = self._task.priority if self._task else Priority.MEDIUM
        self._priority_combo.setCurrentIndex(current_p - 1)
        form.addRow("Priority:", self._priority_combo)

        # Due date
        self._due_check = QCheckBox("Set due date")
        self._due_date = QDateEdit()
        self._due_date.setCalendarPopup(True)
        self._due_date.setDisplayFormat("MMM dd, yyyy")
        if self._task and self._task.due_date:
            self._due_check.setChecked(True)
            self._due_date.setDate(QDate(
                self._task.due_date.year,
                self._task.due_date.month,
                self._task.due_date.day,
            ))
        else:
            self._due_date.setDate(QDate.currentDate())
            self._due_date.setEnabled(False)
        self._due_check.toggled.connect(self._due_date.setEnabled)

        due_row = QHBoxLayout()
        due_row.addWidget(self._due_check)
        due_row.addWidget(self._due_date)
        form.addRow("Due:", due_row)

        # Recurrence
        self._recur_combo = QComboBox()
        self._recur_combo.addItems(["None", "Daily", "Weekly", "Monthly", "Yearly"])
        if self._task and self._task.recurrence_rule:
            idx = {"daily": 1, "weekly": 2, "monthly": 3, "yearly": 4}.get(
                self._task.recurrence_rule.lower(), 0
            )
            self._recur_combo.setCurrentIndex(idx)
        form.addRow("Repeat:", self._recur_combo)

        layout.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        ok_btn.setText("Save Task")
        ok_btn.setObjectName("PrimaryButton")
        layout.addWidget(buttons)

        self._title_edit.setFocus()

    def get_data(self) -> dict:
        due = None
        if self._due_check.isChecked():
            d = self._due_date.date()
            due = datetime(d.year(), d.month(), d.day())

        recur_map = {0: None, 1: "daily", 2: "weekly", 3: "monthly", 4: "yearly"}
        return {
            "title": self._title_edit.text().strip(),
            "description": self._desc_edit.toPlainText().strip(),
            "project_id": self._project_combo.currentData(),
            "priority": self._priority_combo.currentData(),
            "due_date": due,
            "recurrence_rule": recur_map.get(self._recur_combo.currentIndex()),
        }


# ──────────────────────────────────────────────────────────────────
# KANBAN COLUMN
# ──────────────────────────────────────────────────────────────────

class KanbanColumn(QWidget):
    """Single kanban column (To Do / In Progress / Done / Cancelled)."""

    task_dropped = Signal(int, str)  # task_id, column

    COLUMN_META = {
        "todo":        ("📋 To Do",       "#4A9EFF"),
        "in_progress": ("⚡ In Progress",  "#FFD93D"),
        "done":        ("✅ Done",         "#4CAF50"),
        "cancelled":   ("❌ Cancelled",    "#FF5252"),
    }

    def __init__(self, column_id: str, tasks: list[Task], parent=None):
        super().__init__(parent)
        self._column_id = column_id
        self.setObjectName("KanbanColumn")
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._build_ui(tasks)

    def _build_ui(self, tasks: list[Task]):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        label, color = self.COLUMN_META.get(self._column_id, ("Column", "#6C6C6C"))

        # Header
        header = QWidget()
        header.setObjectName("KanbanColumnHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 8, 8, 10)

        title = QLabel(label)
        title.setFont(QFont("Segoe UI", 13, QFont.DemiBold))
        title.setStyleSheet(f"color: {color}; background: transparent;")

        count = Badge(len(tasks))
        count.setStyleSheet(f"""
            QLabel {{
                background: {color}22;
                color: {color};
                border-radius: 10px;
                padding: 1px 7px;
                font-size: 11px;
                font-weight: 700;
            }}
        """)
        hl.addWidget(title)
        hl.addStretch()
        hl.addWidget(count)
        layout.addWidget(header)

        # Task cards scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._task_container = QWidget()
        self._task_layout = QVBoxLayout(self._task_container)
        self._task_layout.setContentsMargins(0, 0, 0, 0)
        self._task_layout.setSpacing(6)
        self._task_layout.addStretch()

        for task in tasks:
            self._add_task_card(task)

        scroll.setWidget(self._task_container)
        layout.addWidget(scroll, 1)

    def _add_task_card(self, task: Task):
        card = _KanbanCard(task, self._column_id)
        idx = max(0, self._task_layout.count() - 1)
        self._task_layout.insertWidget(idx, card)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        task_id = int(event.mimeData().text())
        self.task_dropped.emit(task_id, self._column_id)
        event.acceptProposedAction()


class _KanbanCard(QFrame):
    """Draggable task card for Kanban board."""

    def __init__(self, task: Task, column: str, parent=None):
        super().__init__(parent)
        self._task = task
        self._column = column
        self.setObjectName("NoteCard")
        self.setFixedHeight(90)
        self.setCursor(Qt.OpenHandCursor)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        title = QLabel(self._task.title)
        title.setFont(QFont("Segoe UI", 12, QFont.DemiBold))
        title.setWordWrap(True)
        title.setStyleSheet("background: transparent;")
        layout.addWidget(title)

        meta = QHBoxLayout()
        meta.setSpacing(8)

        p_color = Priority.color(self._task.priority)
        prio = QLabel(f"● {Priority.label(self._task.priority)}")
        prio.setFont(QFont("Segoe UI", 10))
        prio.setStyleSheet(f"color: {p_color}; background: transparent;")
        meta.addWidget(prio)

        if self._task.due_date:
            color = theme.t("error") if self._task.is_overdue else theme.t("text_tertiary")
            due = QLabel(f"📅 {self._task.due_label}")
            due.setFont(QFont("Segoe UI", 10))
            due.setStyleSheet(f"color: {color}; background: transparent;")
            meta.addWidget(due)

        meta.addStretch()
        if self._task.subtasks:
            done = sum(1 for s in self._task.subtasks if s.is_done)
            sub = QLabel(f"✓ {done}/{len(self._task.subtasks)}")
            sub.setFont(QFont("Segoe UI", 10))
            sub.setStyleSheet(f"color: {theme.t('text_tertiary')}; background: transparent;")
            meta.addWidget(sub)

        layout.addLayout(meta)

    def mouseMoveEvent(self, event):
        from PySide6.QtGui import QDrag
        from PySide6.QtCore import QMimeData
        if event.buttons() & Qt.LeftButton:
            drag = QDrag(self)
            mime = QMimeData()
            mime.setText(str(self._task.id))
            drag.setMimeData(mime)
            drag.exec(Qt.MoveAction)


# ──────────────────────────────────────────────────────────────────
# LIST VIEW
# ──────────────────────────────────────────────────────────────────

class TaskListView(QWidget):
    """Scrollable task list grouped by project."""

    task_selected = Signal(int)
    task_create_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(52)
        toolbar.setObjectName("Toolbar")
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(16, 0, 16, 0)
        tl.setSpacing(10)

        self._title = QLabel("Tasks")
        self._title.setFont(QFont("Segoe UI", 16, QFont.DemiBold))
        self._title.setStyleSheet("background: transparent;")

        search = SearchBar("Search tasks…")
        search.setFixedWidth(240)
        search.search_changed.connect(self._on_search)

        filter_combo = QComboBox()
        filter_combo.addItems(["All", "Today", "Overdue", "High Priority", "Completed"])
        filter_combo.currentTextChanged.connect(self._on_filter)

        new_btn = QPushButton("＋ New Task")
        new_btn.setObjectName("PrimaryButton")
        new_btn.setFixedHeight(34)
        new_btn.clicked.connect(self.task_create_requested.emit)

        tl.addWidget(self._title, 1)
        tl.addWidget(search)
        tl.addWidget(filter_combo)
        tl.addWidget(new_btn)
        layout.addWidget(toolbar)

        # Task list
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)

        self._container = QWidget()
        self._task_layout = QVBoxLayout(self._container)
        self._task_layout.setContentsMargins(16, 8, 16, 16)
        self._task_layout.setSpacing(4)
        self._task_layout.addStretch()

        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll, 1)

    def load_tasks(self, tasks: list[Task], title: str = "Tasks"):
        self._title.setText(title)
        while self._task_layout.count() > 1:
            item = self._task_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not tasks:
            empty = EmptyState("✅", "No tasks", "Press ＋ to create a task")
            self._task_layout.insertWidget(0, empty)
            return

        for i, task in enumerate(tasks):
            widget = TaskItemWidget(task)
            widget.toggled.connect(self._on_task_toggled)
            widget.clicked.connect(self.task_selected.emit)
            widget.context_requested.connect(self._on_context_menu)
            self._task_layout.insertWidget(i, widget)

    def _on_task_toggled(self, task_id: int, done: bool):
        if done:
            task_service.complete_task(task_id)
        else:
            task_service.update_task(task_id, status=TaskStatus.TODO, completed_at=None)

    def _on_search(self, query: str):
        tasks = task_service.search_tasks(query) if query else task_service.get_all_tasks()
        self.load_tasks(tasks)

    def _on_filter(self, filter_text: str):
        filters = {
            "All":           lambda: task_service.get_all_tasks(),
            "Today":         lambda: task_service.get_today_tasks(),
            "Overdue":       lambda: task_service.get_overdue_tasks(),
            "High Priority": lambda: task_service.get_all_tasks(),
            "Completed":     lambda: task_service.get_all_tasks(status=TaskStatus.DONE),
        }
        tasks = filters.get(filter_text, lambda: [])()
        if filter_text == "High Priority":
            tasks = [t for t in tasks if t.priority <= Priority.HIGH]
        self.load_tasks(tasks, title=filter_text)

    def _on_context_menu(self, task_id: int, pos: QPoint):
        task = task_service.get_task(task_id)
        if not task:
            return
        menu = QMenu(self)
        menu.addAction("✏️ Edit",   lambda: self.task_selected.emit(task_id))
        menu.addAction("✅ Complete", lambda: task_service.complete_task(task_id))
        menu.addSeparator()
        menu.addAction("🗑️ Delete", lambda: task_service.delete_task(task_id))
        menu.exec(pos)


# ──────────────────────────────────────────────────────────────────
# KANBAN VIEW
# ──────────────────────────────────────────────────────────────────

class KanbanView(QWidget):
    """Four-column Kanban board."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: Optional[int] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setObjectName("Toolbar")
        toolbar.setFixedHeight(52)
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(16, 0, 16, 0)

        title = QLabel("Kanban Board")
        title.setFont(QFont("Segoe UI", 16, QFont.DemiBold))
        title.setStyleSheet("background: transparent;")

        self._project_combo = QComboBox()
        self._project_combo.addItem("All Projects", None)
        for p in task_service.get_all_projects():
            self._project_combo.addItem(p.name, p.id)
        self._project_combo.currentIndexChanged.connect(
            lambda: self.load_board(self._project_combo.currentData())
        )

        new_btn = QPushButton("＋ New Task")
        new_btn.setObjectName("PrimaryButton")
        new_btn.setFixedHeight(34)
        new_btn.clicked.connect(self._new_task)

        tl.addWidget(title)
        tl.addWidget(self._project_combo)
        tl.addStretch()
        tl.addWidget(new_btn)
        layout.addWidget(toolbar)

        # Board scroll
        self._board_scroll = QScrollArea()
        self._board_scroll.setWidgetResizable(True)
        self._board_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._board_scroll.setFrameShape(QFrame.NoFrame)

        self._board_widget = QWidget()
        self._board_layout = QHBoxLayout(self._board_widget)
        self._board_layout.setContentsMargins(16, 12, 16, 12)
        self._board_layout.setSpacing(12)

        self._board_scroll.setWidget(self._board_widget)
        layout.addWidget(self._board_scroll, 1)

    def load_board(self, project_id: Optional[int] = None):
        self._project_id = project_id
        while self._board_layout.count():
            item = self._board_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        board = task_service.get_kanban_board(project_id)
        for col_id in ("todo", "in_progress", "done", "cancelled"):
            col = KanbanColumn(col_id, board.get(col_id, []))
            col.task_dropped.connect(self._on_task_dropped)
            self._board_layout.addWidget(col, 1)

    def _on_task_dropped(self, task_id: int, column: str):
        task_service.move_to_kanban(task_id, column)
        self.load_board(self._project_id)

    def _new_task(self):
        dialog = TaskDialog(default_project_id=self._project_id, parent=self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            if data["title"]:
                task_service.create_task(**data)
                self.load_board(self._project_id)


# ──────────────────────────────────────────────────────────────────
# TODAY VIEW
# ──────────────────────────────────────────────────────────────────

class TodayView(QWidget):
    """Daily planner: today's tasks + upcoming."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Date header
        today_str = datetime.now().strftime("%A, %B %d")
        date_lbl = QLabel(today_str)
        date_lbl.setFont(QFont("Segoe UI", 24, QFont.Bold))
        date_lbl.setStyleSheet("background: transparent;")
        layout.addWidget(date_lbl)

        # Stats row
        self._stats_row = QHBoxLayout()
        self._stats_row.setSpacing(12)
        layout.addLayout(self._stats_row)

        layout.addWidget(HDivider())

        # Task sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(8)
        self._content_layout.addStretch()

        scroll.setWidget(self._content)
        layout.addWidget(scroll, 1)

    def load(self):
        # Clear
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Stats
        while self._stats_row.count():
            item = self._stats_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        stats = task_service.get_stats()
        stat_data = [
            ("📋 Total",     stats["total"],           theme.t("text_primary")),
            ("✅ Done",      stats["done"],             "#4CAF50"),
            ("📅 Today",     stats["today_due"],        "#4A9EFF"),
            ("⚠️ Overdue",   stats["overdue"],          "#FF5252"),
        ]
        for label, count, color in stat_data:
            card = self._stat_card(label, str(count), color)
            self._stats_row.addWidget(card)

        # Overdue
        overdue = task_service.get_overdue_tasks()
        if overdue:
            self._content_layout.insertWidget(
                0, SectionHeader("⚠️ Overdue"), alignment=Qt.AlignLeft
            )
            for i, task in enumerate(overdue):
                w = TaskItemWidget(task)
                w.toggled.connect(lambda tid, done: task_service.complete_task(tid) if done else None)
                self._content_layout.insertWidget(i + 1, w)

        # Today
        today_tasks = task_service.get_today_tasks()
        today_tasks = [t for t in today_tasks if not t.is_overdue]
        offset = len(overdue) + (2 if overdue else 0)
        if today_tasks:
            self._content_layout.insertWidget(
                offset, SectionHeader("📅 Today"), alignment=Qt.AlignLeft
            )
            for i, task in enumerate(today_tasks):
                w = TaskItemWidget(task)
                w.toggled.connect(lambda tid, done: task_service.complete_task(tid) if done else None)
                self._content_layout.insertWidget(offset + i + 1, w)

        if not overdue and not today_tasks:
            empty = EmptyState("🌟", "All clear!", "No tasks due today. Enjoy your day!")
            self._content_layout.insertWidget(0, empty)

    def _stat_card(self, label: str, value: str, color: str) -> QWidget:
        card = QWidget()
        card.setObjectName("Card")
        card.setFixedHeight(80)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)

        val_lbl = QLabel(value)
        val_lbl.setFont(QFont("Segoe UI", 22, QFont.Bold))
        val_lbl.setStyleSheet(f"color: {color}; background: transparent;")

        lbl = QLabel(label)
        lbl.setFont(QFont("Segoe UI", 11))
        lbl.setStyleSheet(f"color: {theme.t('text_tertiary')}; background: transparent;")

        layout.addWidget(val_lbl)
        layout.addWidget(lbl)
        return card


# ──────────────────────────────────────────────────────────────────
# TASKS VIEW (tab container)
# ──────────────────────────────────────────────────────────────────

class TasksView(QWidget):
    """
    Container for List / Kanban / Today sub-views.
    Exposes a unified API for the main controller.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._list_view = TaskListView()
        self._list_view.task_create_requested.connect(self._create_task_dialog)

        self._kanban_view = KanbanView()
        self._today_view = TodayView()

        self._tabs.addTab(self._list_view,   "☰  List")
        self._tabs.addTab(self._kanban_view, "⬛  Kanban")
        self._tabs.addTab(self._today_view,  "📅  Today")

        layout.addWidget(self._tabs)

    def refresh(self):
        tasks = task_service.get_all_tasks()
        self._list_view.load_tasks(tasks)
        self._kanban_view.load_board()
        self._today_view.load()

    def set_project(self, project_id: int):
        tasks = task_service.get_all_tasks(project_id=project_id)
        project = next((p for p in task_service.get_all_projects() if p.id == project_id), None)
        title = project.name if project else "Project"
        self._list_view.load_tasks(tasks, title=title)
        self._kanban_view.load_board(project_id)
        self._tabs.setCurrentIndex(0)

    def _create_task_dialog(self):
        dialog = TaskDialog(parent=self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            if data["title"]:
                task_service.create_task(**data)
                self.refresh()
