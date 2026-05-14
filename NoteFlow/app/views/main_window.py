"""
views/main_window.py
─────────────────────
Main application window.

Responsibilities:
  • Sidebar navigation
  • View stack (Notes / Tasks / Kanban / Today / Pomodoro / Settings)
  • Global keyboard shortcuts
  • System tray icon
  • Autosave background timer
  • Window state persistence
  • Quick-add popup trigger
"""

from __future__ import annotations
import os
import sys
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QLabel, QPushButton, QFrame,
    QSystemTrayIcon, QMenu, QApplication, QStatusBar,
    QSizePolicy, QSplitter,
)
from PySide6.QtCore import (
    Qt, QTimer, QSettings, QSize, Signal, QThread, QObject,
)
from PySide6.QtGui import (
    QKeySequence, QShortcut, QFont, QIcon, QPixmap,
    QAction, QCloseEvent, QColor,
)

from app.themes.theme_manager import theme
from app.config.settings_manager import settings_manager
from app.services.note_service import note_service
from app.services.task_service import task_service
from app.services.backup_service import backup_service
from app.widgets.sidebar import Sidebar
from app.widgets.common import SearchBar
from app.views.notes_view import NotesView
from app.views.tasks_view import TasksView
from app.views.pomodoro_view import PomodoroView
from app.views.settings_view import SettingsView

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# TOOLBAR WIDGET
# ──────────────────────────────────────────────────────────────────

class TopToolbar(QWidget):
    """Top toolbar: search, view toggles, quick-add, theme toggle."""

    search_submitted = Signal(str)
    quick_add_requested = Signal()
    focus_mode_requested = Signal()
    theme_toggle_requested = Signal()
    sidebar_toggle_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Toolbar")
        self.setFixedHeight(52)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        # Sidebar toggle
        sidebar_btn = self._icon_btn("☰", "Toggle Sidebar (Ctrl+\\)")
        sidebar_btn.clicked.connect(self.sidebar_toggle_requested.emit)
        layout.addWidget(sidebar_btn)

        layout.addWidget(self._vsep())

        # Search bar
        self._search = SearchBar("Search everything… (Ctrl+F)")
        self._search.setFixedWidth(300)
        self._search.search_changed.connect(self.search_submitted.emit)
        layout.addWidget(self._search)

        layout.addStretch()

        # Quick add
        quick_btn = QPushButton("＋ Quick Add")
        quick_btn.setObjectName("PrimaryButton")
        quick_btn.setFixedHeight(34)
        quick_btn.setToolTip("Quick add note/task (Ctrl+Space)")
        quick_btn.setCursor(Qt.PointingHandCursor)
        quick_btn.clicked.connect(self.quick_add_requested.emit)
        layout.addWidget(quick_btn)

        layout.addWidget(self._vsep())

        # Theme toggle
        self._theme_btn = self._icon_btn("🌙", "Toggle dark/light mode (Ctrl+Shift+T)")
        self._theme_btn.clicked.connect(self.theme_toggle_requested.emit)
        layout.addWidget(self._theme_btn)

        # Focus mode
        focus_btn = self._icon_btn("⛶", "Focus mode (F11)")
        focus_btn.clicked.connect(self.focus_mode_requested.emit)
        layout.addWidget(focus_btn)

    def _icon_btn(self, icon: str, tooltip: str) -> QPushButton:
        btn = QPushButton(icon)
        btn.setObjectName("IconButton")
        btn.setFixedSize(36, 36)
        btn.setFont(QFont("Segoe UI", 15))
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        return btn

    def _vsep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedHeight(22)
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"color: {theme.t('border_subtle')};")
        return sep

    def update_theme_icon(self):
        self._theme_btn.setText("☀️" if theme.is_dark else "🌙")

    def focus_search(self):
        self._search.setFocus()
        self._search.selectAll()


# ──────────────────────────────────────────────────────────────────
# BACKGROUND WORKER (for backup etc.)
# ──────────────────────────────────────────────────────────────────

class BackupWorker(QObject):
    done = Signal(str)

    def run(self):
        try:
            path = backup_service.create_backup()
            self.done.emit(path)
        except Exception as e:
            logger.error(f"Background backup failed: {e}")
            self.done.emit("")


# ──────────────────────────────────────────────────────────────────
# MAIN WINDOW
# ──────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """
    Application main window.
    Uses a QStackedWidget to swap between page views.
    """

    PAGE_NOTES     = 0
    PAGE_TASKS     = 1
    PAGE_POMODORO  = 2
    PAGE_SETTINGS  = 3

    def __init__(self):
        super().__init__()
        self._focus_mode = False
        self._sidebar_visible = True
        self._setup_window()
        self._build_ui()
        self._setup_shortcuts()
        self._setup_tray()
        self._restore_state()
        self._start_timers()
        self._navigate_to_startup()
        theme.on_theme_changed(self._on_theme_changed)

    # ── Window setup ─────────────────────────────────────────────

    def _setup_window(self):
        self.setWindowTitle("NoteFlow")
        self.setMinimumSize(900, 600)
        self.resize(1280, 800)

        # App icon (generated programmatically)
        icon_px = QPixmap(32, 32)
        icon_px.fill(Qt.transparent)
        from PySide6.QtGui import QPainter, QPen, QBrush
        p = QPainter(icon_px)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(QColor("#4A9EFF")))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, 32, 32, 8, 8)
        p.setFont(QFont("Segoe UI", 18, QFont.Bold))
        p.setPen(QColor("white"))
        p.drawText(0, 0, 32, 32, Qt.AlignCenter, "✦")
        p.end()
        self.setWindowIcon(QIcon(icon_px))

        # High-DPI support
        self.setAttribute(Qt.WA_DeleteOnClose)

    # ── UI construction ───────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ───────────────────────────────────
        self._sidebar = Sidebar()
        self._sidebar.navigate.connect(self._on_navigate)
        self._sidebar.folder_selected.connect(self._on_folder_selected)
        self._sidebar.project_selected.connect(self._on_project_selected)
        self._sidebar.tag_selected.connect(self._on_tag_selected)
        self._sidebar.folder_create_requested.connect(self._create_folder)
        self._sidebar.project_create_requested.connect(self._create_project)
        root.addWidget(self._sidebar)

        # ── Right side: toolbar + page stack ─────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Toolbar
        self._toolbar = TopToolbar()
        self._toolbar.search_submitted.connect(self._on_search)
        self._toolbar.quick_add_requested.connect(self._show_quick_add)
        self._toolbar.focus_mode_requested.connect(self._toggle_focus_mode)
        self._toolbar.theme_toggle_requested.connect(self._toggle_theme)
        self._toolbar.sidebar_toggle_requested.connect(self._toggle_sidebar)
        right_layout.addWidget(self._toolbar)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"color: {theme.t('border_subtle')};")
        right_layout.addWidget(sep)

        # Page stack
        self._stack = QStackedWidget()

        self._notes_view = NotesView()
        self._tasks_view = TasksView()
        self._pomodoro_view = PomodoroView()
        self._settings_view = SettingsView()
        self._settings_view.theme_changed.connect(
            lambda t, a: self._toolbar.update_theme_icon()
        )

        self._stack.addWidget(self._notes_view)    # 0
        self._stack.addWidget(self._tasks_view)    # 1
        self._stack.addWidget(self._pomodoro_view) # 2
        self._stack.addWidget(self._settings_view) # 3

        right_layout.addWidget(self._stack, 1)
        root.addWidget(right, 1)

        # ── Status bar ────────────────────────────────
        self._status = QStatusBar()
        self._status.setFixedHeight(24)
        self.setStatusBar(self._status)

        self._status_note_lbl = QLabel("Ready")
        self._status_note_lbl.setFont(QFont("Segoe UI", 11))
        self._status.addWidget(self._status_note_lbl)

        self._status_task_lbl = QLabel("")
        self._status_task_lbl.setFont(QFont("Segoe UI", 11))
        self._status.addPermanentWidget(self._status_task_lbl)

        self._refresh_sidebar()
        self._refresh_status()

    # ── Keyboard shortcuts ────────────────────────────────────────

    def _setup_shortcuts(self):
        shortcuts = [
            ("Ctrl+N",       self._new_note),
            ("Ctrl+T",       self._new_task),
            ("Ctrl+F",       self._toolbar.focus_search),
            ("Ctrl+\\",      self._toggle_sidebar),
            ("Ctrl+Space",   self._show_quick_add),
            ("F11",          self._toggle_focus_mode),
            ("Ctrl+Shift+T", self._toggle_theme),
            ("Ctrl+1",       lambda: self._on_navigate("notes")),
            ("Ctrl+2",       lambda: self._on_navigate("tasks")),
            ("Ctrl+3",       lambda: self._on_navigate("today")),
            ("Ctrl+4",       lambda: self._on_navigate("kanban")),
            ("Ctrl+5",       lambda: self._on_navigate("pomodoro")),
        ]
        for keys, fn in shortcuts:
            sc = QShortcut(QKeySequence(keys), self)
            sc.activated.connect(fn)

    # ── System tray ───────────────────────────────────────────────

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self._tray = QSystemTrayIcon(self.windowIcon(), self)
        self._tray.setToolTip("NoteFlow")
        self._tray.activated.connect(self._on_tray_activated)

        menu = QMenu()
        menu.addAction("Open NoteFlow",  self.show_normal)
        menu.addAction("Quick Add",      self._show_quick_add)
        menu.addSeparator()
        menu.addAction("New Note",       self._new_note)
        menu.addAction("New Task",       self._new_task)
        menu.addSeparator()
        menu.addAction("Quit",           self._quit)

        self._tray.setContextMenu(menu)
        self._tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_normal()

    def show_normal(self):
        self.show()
        self.activateWindow()
        self.raise_()

    # ── Timers ────────────────────────────────────────────────────

    def _start_timers(self):
        # Status bar refresh every 30s
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(30_000)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start()

        # Scheduled backup
        backup_interval = settings_manager.get_int("backup_interval", 86400)
        if settings_manager.get_bool("backup_enabled", True):
            self._backup_timer = QTimer(self)
            self._backup_timer.setInterval(backup_interval * 1000)
            self._backup_timer.timeout.connect(self._run_backup)
            self._backup_timer.start()

    def _run_backup(self):
        thread = QThread(self)
        worker = BackupWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(thread.quit)
        thread.start()

    # ── Navigation ────────────────────────────────────────────────

    def _on_navigate(self, page_id: str):
        self._sidebar.set_active(page_id)

        page_map = {
            "notes":     self.PAGE_NOTES,
            "all_notes": self.PAGE_NOTES,
            "archive":   self.PAGE_NOTES,
            "trash":     self.PAGE_NOTES,
            "tasks":     self.PAGE_TASKS,
            "today":     self.PAGE_TASKS,
            "kanban":    self.PAGE_TASKS,
            "pomodoro":  self.PAGE_POMODORO,
            "settings":  self.PAGE_SETTINGS,
        }
        page_idx = page_map.get(page_id, self.PAGE_NOTES)
        self._stack.setCurrentIndex(page_idx)

        # Sub-page routing
        if page_id == "all_notes":
            self._notes_view.set_folder(None)
            self._notes_view.set_archived(False)
        elif page_id == "archive":
            self._notes_view.set_archived(True)
        elif page_id == "trash":
            self._notes_view.set_trash()
        elif page_id == "notes":
            self._notes_view.refresh()
        elif page_id == "today":
            self._tasks_view._tabs.setCurrentIndex(2)  # Today tab
        elif page_id == "kanban":
            self._tasks_view._tabs.setCurrentIndex(1)  # Kanban tab
        elif page_id == "tasks":
            self._tasks_view._tabs.setCurrentIndex(0)  # List tab

    def _on_folder_selected(self, folder_id: int):
        self._stack.setCurrentIndex(self.PAGE_NOTES)
        self._notes_view.set_folder(folder_id)

    def _on_project_selected(self, project_id: int):
        self._stack.setCurrentIndex(self.PAGE_TASKS)
        self._tasks_view.set_project(project_id)

    def _on_tag_selected(self, tag_id: int):
        self._stack.setCurrentIndex(self.PAGE_NOTES)
        notes = note_service.get_notes_by_tag(tag_id)
        self._notes_view._list_panel.load_notes(notes, title="Tag Results")

    def _on_search(self, query: str):
        if not query:
            return
        # Search both notes and tasks; show notes view with results
        notes = note_service.search_notes(query)
        self._stack.setCurrentIndex(self.PAGE_NOTES)
        self._notes_view._list_panel.load_notes(notes, title=f"Search: {query}")

    # ── Actions ───────────────────────────────────────────────────

    def _new_note(self):
        self._stack.setCurrentIndex(self.PAGE_NOTES)
        self._notes_view._create_note()
        self._sidebar.set_active("notes")

    def _new_task(self):
        self._stack.setCurrentIndex(self.PAGE_TASKS)
        self._tasks_view._tabs.setCurrentIndex(0)
        self._tasks_view._list_view._create_task_dialog \
            if hasattr(self._tasks_view._list_view, '_create_task_dialog') \
            else self._tasks_view._list_view.task_create_requested.emit()
        self._tasks_view._create_task_dialog()
        self._sidebar.set_active("tasks")

    def _create_folder(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name.strip():
            note_service.create_folder(name.strip())
            self._refresh_sidebar()

    def _create_project(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New Project", "Project name:")
        if ok and name.strip():
            task_service.create_project(name.strip())
            self._refresh_sidebar()

    def _show_quick_add(self):
        from app.widgets.quick_add import QuickAddPopup
        popup = QuickAddPopup(self)
        popup.note_created.connect(lambda nid: self._on_quick_note(nid))
        popup.task_created.connect(lambda tid: self._tasks_view.refresh())
        popup.exec()

    def _on_quick_note(self, note_id: int):
        self._notes_view.refresh()
        self._notes_view._list_panel.select_note(note_id)
        note = note_service.get_note(note_id)
        if note:
            self._notes_view._editor_panel.load_note(note)

    # ── View modes ────────────────────────────────────────────────

    def _toggle_sidebar(self):
        self._sidebar_visible = not self._sidebar_visible
        self._sidebar.setVisible(self._sidebar_visible)

    def _toggle_focus_mode(self):
        self._focus_mode = not self._focus_mode
        self._toolbar.setVisible(not self._focus_mode)
        self._sidebar.setVisible(not self._focus_mode and self._sidebar_visible)
        self._status.setVisible(not self._focus_mode)
        if self._focus_mode:
            self.setWindowState(Qt.WindowFullScreen)
            self._show_status("Focus mode — press F11 to exit", 3000)
        else:
            self.setWindowState(Qt.WindowNoState)

    def _toggle_theme(self):
        new_theme = "light" if theme.is_dark else "dark"
        theme.apply_theme(theme=new_theme)
        settings_manager.set("theme", new_theme)
        self._toolbar.update_theme_icon()

    # ── Status bar ────────────────────────────────────────────────

    def _show_status(self, msg: str, timeout: int = 3000):
        self._status.showMessage(msg, timeout)

    def _refresh_status(self):
        try:
            stats = task_service.get_stats()
            note_count = len(note_service.get_all_notes())
            self._status_note_lbl.setText(f"📝 {note_count} notes")
            overdue = stats["overdue"]
            if overdue:
                self._status_task_lbl.setText(f"⚠️ {overdue} overdue  ")
            else:
                today = stats["today_due"]
                self._status_task_lbl.setText(f"📅 {today} due today  ")
        except Exception:
            pass

    def _refresh_sidebar(self):
        try:
            folders = note_service.get_all_folders()
            projects = task_service.get_all_projects()
            tags = note_service.get_all_tags()
            self._sidebar.set_folders(folders)
            self._sidebar.set_projects(projects)
            self._sidebar.set_tags(tags)

            overdue = task_service.get_stats().get("overdue", 0)
            self._sidebar.set_badge("today", overdue)
        except Exception as e:
            logger.warning(f"Sidebar refresh failed: {e}")

    # ── Window state ──────────────────────────────────────────────

    def _restore_state(self):
        qs = QSettings("NoteFlow", "NoteFlow")
        geometry = qs.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        state = qs.value("windowState")
        if state:
            self.restoreState(state)

    def _save_state(self):
        qs = QSettings("NoteFlow", "NoteFlow")
        qs.setValue("geometry", self.saveGeometry())
        qs.setValue("windowState", self.saveState())

    def _navigate_to_startup(self):
        startup = settings_manager.get("startup_page", "notes")
        self._on_navigate(startup)

    # ── Close event ───────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent):
        self._save_state()
        # Minimize to tray instead of closing
        if QSystemTrayIcon.isSystemTrayAvailable() and hasattr(self, "_tray"):
            event.ignore()
            self.hide()
            self._tray.showMessage(
                "NoteFlow",
                "Running in the background. Double-click the tray icon to reopen.",
                QSystemTrayIcon.Information,
                2000,
            )
        else:
            self._quit()

    def _quit(self):
        self._save_state()
        QApplication.quit()

    # ── Theme changes ─────────────────────────────────────────────

    def _on_theme_changed(self):
        self._toolbar.update_theme_icon()
        self.update()
