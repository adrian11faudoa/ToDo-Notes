"""
views/settings_view.py
──────────────────────
Settings panel: theme, accent color, font size,
autosave, backup, Pomodoro durations, keyboard shortcuts.
"""

from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QSpinBox, QCheckBox,
    QScrollArea, QFrame, QGroupBox, QSlider,
    QFileDialog, QMessageBox, QLineEdit,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

from app.themes.theme_manager import theme, ACCENT_COLORS
from app.config.settings_manager import settings_manager
from app.services.backup_service import backup_service
from app.widgets.common import SectionHeader, HDivider


# ──────────────────────────────────────────────────────────────────
# COLOR SWATCH BUTTON
# ──────────────────────────────────────────────────────────────────

class ColorSwatch(QPushButton):
    """Circular color picker button."""
    selected = Signal(str)

    def __init__(self, color: str, label: str, parent=None):
        super().__init__(parent)
        self._color = color
        self._active = False
        self.setFixedSize(32, 32)
        self.setToolTip(label)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style()
        self.clicked.connect(lambda: self.selected.emit(self._color))

    def _apply_style(self):
        border = "3px solid white" if self._active else "2px solid transparent"
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self._color};
                border-radius: 16px;
                border: {border};
            }}
            QPushButton:hover {{ border: 2px solid rgba(255,255,255,0.6); }}
        """)

    def set_active(self, active: bool):
        self._active = active
        self._apply_style()


# ──────────────────────────────────────────────────────────────────
# SETTINGS SECTION CARD
# ──────────────────────────────────────────────────────────────────

class SettingsCard(QFrame):
    """Styled card container for a settings group."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QLabel(f"  {title}")
        header.setFixedHeight(40)
        header.setFont(QFont("Segoe UI", 13, QFont.DemiBold))
        header.setStyleSheet(f"""
            background: {theme.t('bg_tertiary')};
            color: {theme.t('text_primary')};
            border-radius: 10px 10px 0 0;
            padding-left: 8px;
        """)
        outer.addWidget(header)

        self._body = QWidget()
        self._body.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(20, 12, 20, 16)
        self._layout.setSpacing(14)
        outer.addWidget(self._body)

    def add_row(self, label: str, widget: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)
        lbl = QLabel(label)
        lbl.setFont(QFont("Segoe UI", 13))
        lbl.setFixedWidth(200)
        lbl.setStyleSheet(f"color: {theme.t('text_secondary')}; background: transparent;")
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        self._layout.addLayout(row)
        return row

    def add_widget(self, widget: QWidget):
        self._layout.addWidget(widget)

    def add_stretch(self):
        self._layout.addStretch()


# ──────────────────────────────────────────────────────────────────
# SHORTCUT ROW
# ──────────────────────────────────────────────────────────────────

SHORTCUTS = [
    ("New Note",          "Ctrl+N"),
    ("New Task",          "Ctrl+T"),
    ("Search",            "Ctrl+F"),
    ("Save",              "Ctrl+S"),
    ("Bold",              "Ctrl+B"),
    ("Italic",            "Ctrl+I"),
    ("Toggle Sidebar",    "Ctrl+\\"),
    ("Quick Add Popup",   "Ctrl+Space"),
    ("Focus Mode",        "F11"),
    ("Toggle Theme",      "Ctrl+Shift+T"),
    ("Switch to Notes",   "Ctrl+1"),
    ("Switch to Tasks",   "Ctrl+2"),
    ("Switch to Today",   "Ctrl+3"),
    ("Switch to Kanban",  "Ctrl+4"),
]


# ──────────────────────────────────────────────────────────────────
# SETTINGS VIEW
# ──────────────────────────────────────────────────────────────────

class SettingsView(QWidget):
    """
    Full settings panel.
    Emits theme_changed when the user switches themes or accent.
    """

    theme_changed = Signal(str, str)   # theme_name, accent_color
    settings_saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._swatches: list[ColorSwatch] = []
        self._build_ui()
        self._load_current()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header ────────────────────────────────────
        header = QWidget()
        header.setObjectName("Toolbar")
        header.setFixedHeight(52)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(24, 0, 24, 0)
        title = QLabel("Settings")
        title.setFont(QFont("Segoe UI", 18, QFont.DemiBold))
        title.setStyleSheet("background: transparent;")
        hl.addWidget(title)
        hl.addStretch()
        outer.addWidget(header)

        # ── Scroll area ───────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 20, 32, 32)
        layout.setSpacing(20)

        # ── APPEARANCE ────────────────────────────────
        appearance = SettingsCard("🎨  Appearance")

        # Theme toggle
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["Dark", "Light"])
        self._theme_combo.currentTextChanged.connect(self._on_theme_changed)
        appearance.add_row("Theme:", self._theme_combo)

        # Accent color swatches
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(8)
        for name, hex_color in ACCENT_COLORS.items():
            sw = ColorSwatch(hex_color, name.title())
            sw.selected.connect(self._on_accent_selected)
            self._swatches.append(sw)
            swatch_row.addWidget(sw)
        swatch_row.addStretch()
        swatch_widget = QWidget()
        swatch_widget.setStyleSheet("background: transparent;")
        swatch_widget.setLayout(swatch_row)
        appearance.add_row("Accent color:", swatch_widget)

        # Font size
        self._font_slider = QSlider(Qt.Horizontal)
        self._font_slider.setRange(11, 20)
        self._font_slider.setFixedWidth(200)
        self._font_slider.setTickInterval(1)
        self._font_size_lbl = QLabel("14px")
        self._font_size_lbl.setFixedWidth(40)
        self._font_size_lbl.setStyleSheet("background: transparent;")
        self._font_slider.valueChanged.connect(
            lambda v: self._font_size_lbl.setText(f"{v}px")
        )
        fs_row = QHBoxLayout()
        fs_row.addWidget(self._font_slider)
        fs_row.addWidget(self._font_size_lbl)
        fs_widget = QWidget()
        fs_widget.setStyleSheet("background: transparent;")
        fs_widget.setLayout(fs_row)
        appearance.add_row("Editor font size:", fs_widget)

        layout.addWidget(appearance)

        # ── EDITOR ────────────────────────────────────
        editor_card = SettingsCard("📝  Editor")

        self._autosave_spin = QSpinBox()
        self._autosave_spin.setRange(1, 60)
        self._autosave_spin.setSuffix(" seconds")
        self._autosave_spin.setFixedWidth(140)
        editor_card.add_row("Autosave interval:", self._autosave_spin)

        self._word_count_check = QCheckBox("Show word count in status bar")
        editor_card.add_row("Word count:", self._word_count_check)

        self._default_view_combo = QComboBox()
        self._default_view_combo.addItems(["List", "Grid"])
        self._default_view_combo.setFixedWidth(140)
        editor_card.add_row("Default note view:", self._default_view_combo)

        self._startup_combo = QComboBox()
        self._startup_combo.addItems(["Notes", "Tasks", "Today", "Kanban"])
        self._startup_combo.setFixedWidth(140)
        editor_card.add_row("Startup page:", self._startup_combo)

        layout.addWidget(editor_card)

        # ── POMODORO ──────────────────────────────────
        pomodoro_card = SettingsCard("🍅  Pomodoro")

        self._work_spin = QSpinBox()
        self._work_spin.setRange(1, 120)
        self._work_spin.setSuffix(" min")
        self._work_spin.setFixedWidth(120)
        pomodoro_card.add_row("Work session:", self._work_spin)

        self._short_spin = QSpinBox()
        self._short_spin.setRange(1, 30)
        self._short_spin.setSuffix(" min")
        self._short_spin.setFixedWidth(120)
        pomodoro_card.add_row("Short break:", self._short_spin)

        self._long_spin = QSpinBox()
        self._long_spin.setRange(5, 60)
        self._long_spin.setSuffix(" min")
        self._long_spin.setFixedWidth(120)
        pomodoro_card.add_row("Long break:", self._long_spin)

        layout.addWidget(pomodoro_card)

        # ── BACKUP ────────────────────────────────────
        backup_card = SettingsCard("💾  Backup & Data")

        self._backup_check = QCheckBox("Enable automatic backups")
        backup_card.add_row("Auto backup:", self._backup_check)

        self._backup_interval_combo = QComboBox()
        self._backup_interval_combo.addItems(["Every hour", "Every 6 hours", "Daily", "Weekly"])
        self._backup_interval_combo.setFixedWidth(160)
        backup_card.add_row("Backup frequency:", self._backup_interval_combo)

        backup_now_btn = QPushButton("📦 Back Up Now")
        backup_now_btn.setFixedWidth(160)
        backup_now_btn.clicked.connect(self._backup_now)
        backup_card.add_row("Manual backup:", backup_now_btn)

        restore_btn = QPushButton("♻️ Restore Backup…")
        restore_btn.setFixedWidth(160)
        restore_btn.clicked.connect(self._restore_backup)
        backup_card.add_row("Restore:", restore_btn)

        layout.addWidget(backup_card)

        # ── KEYBOARD SHORTCUTS ─────────────────────────
        shortcuts_card = SettingsCard("⌨️  Keyboard Shortcuts")
        shortcut_grid = QWidget()
        shortcut_grid.setStyleSheet("background: transparent;")
        sg_layout = QVBoxLayout(shortcut_grid)
        sg_layout.setContentsMargins(0, 0, 0, 0)
        sg_layout.setSpacing(6)

        for action, keys in SHORTCUTS:
            row = QHBoxLayout()
            action_lbl = QLabel(action)
            action_lbl.setFont(QFont("Segoe UI", 12))
            action_lbl.setStyleSheet(f"color: {theme.t('text_secondary')}; background: transparent;")
            keys_lbl = QLabel(keys)
            keys_lbl.setFont(QFont("Cascadia Code, Consolas", 11))
            keys_lbl.setAlignment(Qt.AlignRight)
            keys_lbl.setStyleSheet(f"""
                background: {theme.t('bg_tertiary')};
                color: {theme.t('text_primary')};
                border: 1px solid {theme.t('border_default')};
                border-radius: 4px;
                padding: 2px 8px;
            """)
            row.addWidget(action_lbl, 1)
            row.addWidget(keys_lbl)
            sg_layout.addLayout(row)

        shortcuts_card.add_widget(shortcut_grid)
        layout.addWidget(shortcuts_card)

        # ── ABOUT ─────────────────────────────────────
        about_card = SettingsCard("ℹ️  About NoteFlow")
        about_layout = QVBoxLayout()
        about_layout.setSpacing(6)

        for text, style in [
            ("NoteFlow v1.0.0", f"font-size: 16px; font-weight: 700; color: {theme.t('text_primary')};"),
            ("A modern offline notes & tasks app", f"font-size: 13px; color: {theme.t('text_secondary')};"),
            ("Built with Python + PySide6 + SQLite", f"font-size: 12px; color: {theme.t('text_tertiary')};"),
        ]:
            lbl = QLabel(text)
            lbl.setStyleSheet(f"background: transparent; {style}")
            about_layout.addWidget(lbl)

        about_widget = QWidget()
        about_widget.setStyleSheet("background: transparent;")
        about_widget.setLayout(about_layout)
        about_card.add_widget(about_widget)
        layout.addWidget(about_card)

        # ── Save button ───────────────────────────────
        save_btn = QPushButton("💾 Save Settings")
        save_btn.setObjectName("PrimaryButton")
        save_btn.setFixedWidth(180)
        save_btn.setFixedHeight(40)
        save_btn.setFont(QFont("Segoe UI", 13))
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn, alignment=Qt.AlignLeft)

        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

    # ── Load / Save ──────────────────────────────────────────────

    def _load_current(self):
        s = settings_manager

        # Theme
        current_theme = s.get("theme", "dark")
        self._theme_combo.setCurrentText(current_theme.title())

        # Accent
        current_accent = s.get("accent_color", "#4A9EFF")
        for sw in self._swatches:
            sw.set_active(sw._color.lower() == current_accent.lower())

        # Font size
        self._font_slider.setValue(s.get_int("font_size", 14))

        # Editor
        self._autosave_spin.setValue(s.get_int("autosave_interval", 3))
        self._word_count_check.setChecked(s.get_bool("show_word_count", True))
        self._default_view_combo.setCurrentText(s.get("default_view", "list").title())
        startup = s.get("startup_page", "notes")
        self._startup_combo.setCurrentText(startup.title())

        # Pomodoro
        self._work_spin.setValue(s.get_int("pomodoro_work", 1500) // 60)
        self._short_spin.setValue(s.get_int("pomodoro_short_break", 300) // 60)
        self._long_spin.setValue(s.get_int("pomodoro_long_break", 900) // 60)

        # Backup
        self._backup_check.setChecked(s.get_bool("backup_enabled", True))
        interval = s.get_int("backup_interval", 86400)
        interval_map = {3600: 0, 21600: 1, 86400: 2, 604800: 3}
        self._backup_interval_combo.setCurrentIndex(interval_map.get(interval, 2))

    def _save(self):
        interval_map = {0: 3600, 1: 21600, 2: 86400, 3: 604800}
        backup_interval = interval_map.get(self._backup_interval_combo.currentIndex(), 86400)

        settings_manager.set_many({
            "theme": self._theme_combo.currentText().lower(),
            "font_size": self._font_slider.value(),
            "autosave_interval": self._autosave_spin.value(),
            "show_word_count": "1" if self._word_count_check.isChecked() else "0",
            "default_view": self._default_view_combo.currentText().lower(),
            "startup_page": self._startup_combo.currentText().lower(),
            "pomodoro_work": self._work_spin.value() * 60,
            "pomodoro_short_break": self._short_spin.value() * 60,
            "pomodoro_long_break": self._long_spin.value() * 60,
            "backup_enabled": "1" if self._backup_check.isChecked() else "0",
            "backup_interval": backup_interval,
        })
        self.settings_saved.emit()
        QMessageBox.information(self, "Saved", "Settings saved successfully.")

    def _on_theme_changed(self, text: str):
        accent = settings_manager.get("accent_color", "#4A9EFF")
        theme.apply_theme(theme=text.lower(), accent=accent)
        self.theme_changed.emit(text.lower(), accent)
        settings_manager.set("theme", text.lower())

    def _on_accent_selected(self, color: str):
        for sw in self._swatches:
            sw.set_active(sw._color == color)
        theme.apply_theme(accent=color)
        settings_manager.set("accent_color", color)
        self.theme_changed.emit(theme.theme, color)

    def _backup_now(self):
        try:
            path = backup_service.create_backup()
            QMessageBox.information(self, "Backup Created",
                                    f"Backup saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Backup Failed", str(e))

    def _restore_backup(self):
        backups = backup_service.list_backups()
        if not backups:
            QMessageBox.information(self, "No Backups", "No backup files found.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Backup", str(backup_service._backup_dir),
            "Database (*.db)"
        )
        if path:
            confirm = QMessageBox.question(
                self, "Restore Backup",
                "This will replace your current database. Continue?",
                QMessageBox.Yes | QMessageBox.No
            )
            if confirm == QMessageBox.Yes:
                backup_service.restore_backup(path)
                QMessageBox.information(self, "Restored",
                                        "Backup restored. Please restart NoteFlow.")
