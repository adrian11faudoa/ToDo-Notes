"""
widgets/sidebar.py
──────────────────
Left sidebar with navigation, folder tree, tag list, and project list.
Emits navigation signals consumed by the main window controller.
"""

from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QScrollArea, QFrame, QSizePolicy, QMenu,
    QInputDialog, QColorDialog,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QColor, QIcon

from app.themes.theme_manager import theme
from app.models.entities import Folder, Project, Tag
from app.widgets.common import (
    SectionHeader, CollapsibleSection, Badge, ColorDot, HDivider
)


# ──────────────────────────────────────────────────────────────────
# NAV BUTTON
# ──────────────────────────────────────────────────────────────────

class NavButton(QPushButton):
    """Sidebar navigation button with icon, label, optional badge."""

    def __init__(self, icon: str, label: str, nav_id: str, parent=None):
        super().__init__(parent)
        self._nav_id = nav_id
        self._badge_count = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 10, 0)
        layout.setSpacing(10)

        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setFont(QFont("Segoe UI", 15))
        self._icon_lbl.setFixedWidth(22)
        self._icon_lbl.setStyleSheet("background: transparent;")

        self._label = QLabel(label)
        self._label.setFont(QFont("Segoe UI", 13, QFont.Medium))
        self._label.setStyleSheet("background: transparent;")

        self._badge = Badge(0)
        self._badge.setFixedSize(20, 20)

        layout.addWidget(self._icon_lbl)
        layout.addWidget(self._label, 1)
        layout.addWidget(self._badge)

        self.setFixedHeight(38)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self._apply_style(False)

    def _apply_style(self, active: bool):
        t = theme.tokens
        if active:
            bg = t["accent_subtle"]
            fg = t["accent"]
            fw = "700"
        else:
            bg = "transparent"
            fg = t["text_secondary"]
            fw = "500"
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                border: none;
                border-radius: 8px;
                text-align: left;
                margin: 1px 8px;
            }}
            QPushButton:hover {{
                background-color: {t['surface_hover']};
            }}
            QLabel {{ color: {fg}; font-weight: {fw}; }}
        """)
        self._label.setStyleSheet(
            f"color: {fg}; font-weight: {fw}; background: transparent;"
        )
        self._icon_lbl.setStyleSheet(
            f"color: {fg}; background: transparent;"
        )

    def setChecked(self, checked: bool):
        super().setChecked(checked)
        self._apply_style(checked)

    def set_badge(self, count: int):
        self._badge.set_count(count)

    @property
    def nav_id(self) -> str:
        return self._nav_id


# ──────────────────────────────────────────────────────────────────
# FOLDER ITEM
# ──────────────────────────────────────────────────────────────────

class FolderItem(QPushButton):
    context_requested = Signal(int)

    def __init__(self, folder: Folder, parent=None):
        super().__init__(parent)
        self._folder = folder
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 10, 0)
        layout.setSpacing(8)

        dot = ColorDot(folder.color, size=8)
        name = QLabel(folder.name)
        name.setFont(QFont("Segoe UI", 12))
        name.setStyleSheet(f"color: {theme.t('text_secondary')}; background: transparent;")
        count = QLabel(str(folder.note_count))
        count.setFont(QFont("Segoe UI", 11))
        count.setStyleSheet(f"color: {theme.t('text_tertiary')}; background: transparent;")

        layout.addWidget(dot)
        layout.addWidget(name, 1)
        layout.addWidget(count)

        self.setFixedHeight(32)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 6px;
                text-align: left;
                margin: 0 8px;
            }}
            QPushButton:hover {{ background-color: {theme.t('surface_hover')}; }}
            QPushButton:checked {{ background-color: {theme.t('accent_subtle')}; }}
        """)

    def contextMenuEvent(self, event):
        self.context_requested.emit(self._folder.id)
        event.accept()

    @property
    def folder_id(self) -> int:
        return self._folder.id


# ──────────────────────────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────────────────────────

class Sidebar(QWidget):
    """
    Main sidebar widget.
    Signals:
        navigate(page_id)       — one of: notes, tasks, today, kanban, pomodoro, settings
        folder_selected(id)     — user clicked a folder
        project_selected(id)    — user clicked a project
        tag_selected(id)        — user clicked a tag
        folder_create_requested — user wants a new folder
        project_create_requested
    """

    navigate = Signal(str)
    folder_selected = Signal(int)
    project_selected = Signal(int)
    tag_selected = Signal(int)
    folder_create_requested = Signal()
    project_create_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(240)

        self._nav_buttons: list[NavButton] = []
        self._folder_items: list[FolderItem] = []
        self._current_page = "notes"

        self._build_ui()
        theme.on_theme_changed(self._refresh_style)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── App header ──────────────────────────────────
        header = QWidget()
        header.setObjectName("SidebarHeader")
        header.setFixedHeight(60)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 0, 16, 0)

        logo = QLabel("✦")
        logo.setFont(QFont("Segoe UI", 20))
        logo.setStyleSheet(f"color: {theme.t('accent')}; background: transparent;")

        title = QLabel("NoteFlow")
        title.setObjectName("AppTitle")
        title.setFont(QFont("Segoe UI", 17, QFont.Bold))

        h_layout.addWidget(logo)
        h_layout.addWidget(title)
        h_layout.addStretch()
        layout.addWidget(header)

        # ── Scroll area for nav items ─────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self._nav_layout = QVBoxLayout(content)
        self._nav_layout.setContentsMargins(0, 8, 0, 8)
        self._nav_layout.setSpacing(0)

        # ── Main Navigation ───────────────────────────
        main_nav = [
            ("📝", "Notes",       "notes"),
            ("✅", "Tasks",       "tasks"),
            ("📅", "Today",       "today"),
            ("🗂️", "Kanban",      "kanban"),
            ("🔍", "All Notes",   "all_notes"),
            ("📦", "Archive",     "archive"),
            ("🗑️", "Trash",       "trash"),
        ]
        for icon, label, nav_id in main_nav:
            btn = NavButton(icon, label, nav_id)
            btn.clicked.connect(lambda _, nid=nav_id: self._on_navigate(nid))
            self._nav_buttons.append(btn)
            self._nav_layout.addWidget(btn)

        self._nav_layout.addSpacing(8)
        self._nav_layout.addWidget(HDivider())
        self._nav_layout.addSpacing(8)

        # ── Folders section ───────────────────────────
        self._folders_section = CollapsibleSection("Folders")
        self._nav_layout.addWidget(self._folders_section)

        add_folder_btn = QPushButton("+ New Folder")
        add_folder_btn.setFlat(True)
        add_folder_btn.setCursor(Qt.PointingHandCursor)
        add_folder_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {theme.t('text_tertiary')}; font-size: 12px;
                text-align: left; padding: 4px 24px;
            }}
            QPushButton:hover {{ color: {theme.t('accent')}; }}
        """)
        add_folder_btn.clicked.connect(self.folder_create_requested.emit)
        self._folders_section.add_widget(add_folder_btn)

        self._nav_layout.addSpacing(8)
        self._nav_layout.addWidget(HDivider())
        self._nav_layout.addSpacing(8)

        # ── Projects section ──────────────────────────
        self._projects_section = CollapsibleSection("Projects")
        self._nav_layout.addWidget(self._projects_section)

        add_project_btn = QPushButton("+ New Project")
        add_project_btn.setFlat(True)
        add_project_btn.setCursor(Qt.PointingHandCursor)
        add_project_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {theme.t('text_tertiary')}; font-size: 12px;
                text-align: left; padding: 4px 24px;
            }}
            QPushButton:hover {{ color: {theme.t('accent')}; }}
        """)
        add_project_btn.clicked.connect(self.project_create_requested.emit)
        self._projects_section.add_widget(add_project_btn)

        self._nav_layout.addSpacing(8)
        self._nav_layout.addWidget(HDivider())
        self._nav_layout.addSpacing(8)

        # ── Tags section ──────────────────────────────
        self._tags_section = CollapsibleSection("Tags")
        self._tags_layout = QVBoxLayout()
        self._tags_layout.setContentsMargins(0, 0, 0, 0)
        self._tags_layout.setSpacing(0)
        tags_container = QWidget()
        tags_container.setLayout(self._tags_layout)
        self._tags_section.add_widget(tags_container)
        self._nav_layout.addWidget(self._tags_section)

        self._nav_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # ── Bottom actions ─────────────────────────────
        bottom = QWidget()
        bottom.setFixedHeight(56)
        b_layout = QHBoxLayout(bottom)
        b_layout.setContentsMargins(12, 8, 12, 8)
        b_layout.setSpacing(4)

        pomodoro_btn = NavButton("🍅", "Pomodoro", "pomodoro")
        pomodoro_btn.clicked.connect(lambda: self._on_navigate("pomodoro"))
        self._nav_buttons.append(pomodoro_btn)
        b_layout.addWidget(pomodoro_btn)

        settings_btn = NavButton("⚙️", "Settings", "settings")
        settings_btn.clicked.connect(lambda: self._on_navigate("settings"))
        self._nav_buttons.append(settings_btn)
        b_layout.addWidget(settings_btn)

        layout.addWidget(bottom)

    # ── Public API ────────────────────────────────────────────────

    def set_folders(self, folders: list[Folder]):
        """Refresh folder list."""
        # Clear existing folder items
        while self._folder_items:
            item = self._folder_items.pop()
            self._folders_section._content_layout.removeWidget(item)
            item.deleteLater()

        for folder in folders:
            item = FolderItem(folder)
            item.clicked.connect(lambda _, fid=folder.id: self._on_folder(fid))
            self._folder_items.append(item)
            self._folders_section.add_widget(item)

    def set_projects(self, projects: list[Project]):
        """Refresh project list."""
        # Clear project buttons (keep "New Project" btn)
        while self._projects_section._content_layout.count() > 1:
            item = self._projects_section._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for project in projects:
            btn = QPushButton(f"  {project.name}")
            btn.setFixedHeight(30)
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            c = QColor(project.color)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none;
                    border-left: 3px solid {project.color};
                    color: {theme.t('text_secondary')}; font-size: 12px;
                    text-align: left; padding: 0 12px 0 20px;
                    margin: 0 8px;
                }}
                QPushButton:hover {{ background: {theme.t('surface_hover')}; }}
            """)
            btn.clicked.connect(lambda _, pid=project.id: self.project_selected.emit(pid))
            # Insert before "New Project" button
            idx = max(0, self._projects_section._content_layout.count() - 1)
            self._projects_section._content_layout.insertWidget(idx, btn)

    def set_tags(self, tags: list[Tag]):
        """Refresh tag list."""
        while self._tags_layout.count():
            item = self._tags_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for tag in tags:
            btn = QPushButton(f"  # {tag.name}")
            btn.setFixedHeight(28)
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none;
                    color: {tag.color}; font-size: 12px;
                    text-align: left; padding: 0 0 0 24px;
                    margin: 0 8px;
                }}
                QPushButton:hover {{ background: {theme.t('surface_hover')}; }}
            """)
            btn.clicked.connect(lambda _, tid=tag.id: self.tag_selected.emit(tid))
            self._tags_layout.addWidget(btn)

    def set_badge(self, nav_id: str, count: int):
        for btn in self._nav_buttons:
            if btn.nav_id == nav_id:
                btn.set_badge(count)
                break

    def set_active(self, nav_id: str):
        self._current_page = nav_id
        for btn in self._nav_buttons:
            btn.setChecked(btn.nav_id == nav_id)

    # ── Private ───────────────────────────────────────────────────

    def _on_navigate(self, nav_id: str):
        self.set_active(nav_id)
        self.navigate.emit(nav_id)

    def _on_folder(self, folder_id: int):
        self.folder_selected.emit(folder_id)
        self.navigate.emit("notes")

    def _refresh_style(self):
        self.setStyleSheet(f"background-color: {theme.t('bg_secondary')};")
