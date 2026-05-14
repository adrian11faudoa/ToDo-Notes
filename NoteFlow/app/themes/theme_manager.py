"""
themes/theme_manager.py
───────────────────────
Centralized theme engine for NoteFlow.

Generates complete Qt stylesheets from a token dictionary.
Supports: Dark / Light / Custom accent color.
All colors are defined as tokens — never hardcoded in widgets.
"""

from __future__ import annotations
from typing import Callable
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# COLOR TOKENS
# ─────────────────────────────────────────────

DARK_TOKENS = {
    # Backgrounds
    "bg_primary":       "#1A1A1F",
    "bg_secondary":     "#22222A",
    "bg_tertiary":      "#2A2A35",
    "bg_elevated":      "#313140",
    "bg_overlay":       "#3A3A4A",

    # Surfaces
    "surface_1":        "#242430",
    "surface_2":        "#2C2C3C",
    "surface_hover":    "#35354A",
    "surface_active":   "#3D3D55",
    "surface_border":   "#3A3A4E",

    # Text
    "text_primary":     "#F0F0F8",
    "text_secondary":   "#A0A0C0",
    "text_tertiary":    "#6A6A8A",
    "text_disabled":    "#444458",
    "text_inverse":     "#0A0A12",

    # Borders
    "border_subtle":    "#2E2E3E",
    "border_default":   "#3A3A50",
    "border_strong":    "#5A5A7A",

    # States
    "success":          "#4CAF50",
    "warning":          "#FFC107",
    "error":            "#FF5252",
    "info":             "#2196F3",

    # Scrollbar
    "scrollbar_bg":     "#1E1E28",
    "scrollbar_handle": "#3A3A50",
    "scrollbar_hover":  "#4A4A65",

    # Input
    "input_bg":         "#1E1E28",
    "input_border":     "#3A3A50",
    "input_focus":      "ACCENT",  # replaced at runtime

    # Misc
    "shadow":           "rgba(0,0,0,0.4)",
    "overlay_bg":       "rgba(0,0,0,0.6)",
    "selection_bg":     "rgba(74,158,255,0.3)",
}

LIGHT_TOKENS = {
    # Backgrounds
    "bg_primary":       "#F5F5FA",
    "bg_secondary":     "#ECECF4",
    "bg_tertiary":      "#E4E4F0",
    "bg_elevated":      "#FFFFFF",
    "bg_overlay":       "#F0F0F8",

    # Surfaces
    "surface_1":        "#FFFFFF",
    "surface_2":        "#F8F8FC",
    "surface_hover":    "#EDEDF8",
    "surface_active":   "#E5E5F5",
    "surface_border":   "#DDDDED",

    # Text
    "text_primary":     "#1A1A2E",
    "text_secondary":   "#5A5A7A",
    "text_tertiary":    "#8A8AAA",
    "text_disabled":    "#BBBBCC",
    "text_inverse":     "#F0F0F8",

    # Borders
    "border_subtle":    "#E8E8F0",
    "border_default":   "#DDDDED",
    "border_strong":    "#AAAACC",

    # States
    "success":          "#388E3C",
    "warning":          "#F57C00",
    "error":            "#D32F2F",
    "info":             "#1565C0",

    # Scrollbar
    "scrollbar_bg":     "#F0F0F8",
    "scrollbar_handle": "#CCCCDD",
    "scrollbar_hover":  "#AAAACC",

    # Input
    "input_bg":         "#FFFFFF",
    "input_border":     "#DDDDED",
    "input_focus":      "ACCENT",

    # Misc
    "shadow":           "rgba(0,0,0,0.12)",
    "overlay_bg":       "rgba(0,0,0,0.3)",
    "selection_bg":     "rgba(74,158,255,0.2)",
}

ACCENT_COLORS = {
    "blue":     "#4A9EFF",
    "purple":   "#9B6DFF",
    "teal":     "#00BFA5",
    "green":    "#4CAF50",
    "orange":   "#FF8C00",
    "pink":     "#FF6B9D",
    "red":      "#FF5252",
    "yellow":   "#FFD93D",
}


def _lighten(hex_color: str, factor: float = 0.2) -> str:
    """Lighten a hex color by factor (0–1)."""
    c = QColor(hex_color)
    h, s, l, a = c.getHslF()
    l = min(1.0, l + factor)
    c.setHslF(h, s, l, a)
    return c.name()


def _darken(hex_color: str, factor: float = 0.2) -> str:
    """Darken a hex color by factor (0–1)."""
    c = QColor(hex_color)
    h, s, l, a = c.getHslF()
    l = max(0.0, l - factor)
    c.setHslF(h, s, l, a)
    return c.name()


def _with_alpha(hex_color: str, alpha: int) -> str:
    """Return rgba() string with given alpha (0–255)."""
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


class ThemeManager:
    """
    Singleton theme manager.
    Call apply_theme() to switch themes at runtime.
    Subscribe via on_theme_changed() for reactive updates.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def initialize(self, theme: str = "dark", accent: str = "#4A9EFF"):
        self._theme = theme
        self._accent = accent
        self._callbacks: list[Callable] = []
        self._tokens: dict[str, str] = {}
        self._initialized = True
        self._build_tokens()

    def _build_tokens(self):
        base = DARK_TOKENS.copy() if self._theme == "dark" else LIGHT_TOKENS.copy()
        accent = self._accent

        # Replace ACCENT placeholder and derive accent variants
        for key, val in base.items():
            if val == "ACCENT":
                base[key] = accent

        base["accent"] = accent
        base["accent_hover"] = _lighten(accent, 0.1)
        base["accent_pressed"] = _darken(accent, 0.1)
        base["accent_subtle"] = _with_alpha(accent, 40)
        base["accent_text"] = "#FFFFFF" if self._theme == "dark" else "#FFFFFF"

        self._tokens = base

    def t(self, key: str) -> str:
        """Get a color token value."""
        return self._tokens.get(key, "#FF00FF")  # magenta = missing token

    def on_theme_changed(self, callback: Callable):
        """Register a callback for theme change events."""
        self._callbacks.append(callback)

    def apply_theme(self, theme: str | None = None, accent: str | None = None):
        """Apply a new theme and/or accent color to the whole application."""
        if theme:
            self._theme = theme
        if accent:
            self._accent = accent
        self._build_tokens()
        self._apply_stylesheet()
        for cb in self._callbacks:
            try:
                cb()
            except Exception as e:
                logger.warning(f"Theme callback error: {e}")

    def _apply_stylesheet(self):
        """Build and apply the full Qt stylesheet."""
        app = QApplication.instance()
        if app:
            app.setStyleSheet(self.build_stylesheet())
            self._apply_palette(app)

    def _apply_palette(self, app: QApplication):
        """Set QPalette to match theme for native widgets."""
        t = self._tokens
        palette = QPalette()
        palette.setColor(QPalette.Window,          QColor(t["bg_primary"]))
        palette.setColor(QPalette.WindowText,       QColor(t["text_primary"]))
        palette.setColor(QPalette.Base,             QColor(t["input_bg"]))
        palette.setColor(QPalette.AlternateBase,    QColor(t["bg_secondary"]))
        palette.setColor(QPalette.Text,             QColor(t["text_primary"]))
        palette.setColor(QPalette.Button,           QColor(t["surface_1"]))
        palette.setColor(QPalette.ButtonText,       QColor(t["text_primary"]))
        palette.setColor(QPalette.Highlight,        QColor(t["accent"]))
        palette.setColor(QPalette.HighlightedText,  QColor(t["accent_text"]))
        palette.setColor(QPalette.PlaceholderText,  QColor(t["text_tertiary"]))
        palette.setColor(QPalette.ToolTipBase,      QColor(t["bg_elevated"]))
        palette.setColor(QPalette.ToolTipText,      QColor(t["text_primary"]))
        app.setPalette(palette)

    def build_stylesheet(self) -> str:
        """Generate the complete application stylesheet."""
        t = self._tokens
        return f"""
/* ═══════════════════════════════════════
   NoteFlow Global Stylesheet
   ═══════════════════════════════════════ */

/* BASE */
QWidget {{
    background-color: {t['bg_primary']};
    color: {t['text_primary']};
    font-family: 'Segoe UI', 'SF Pro Text', -apple-system, sans-serif;
    font-size: 14px;
    border: none;
    outline: none;
}}

QMainWindow {{
    background-color: {t['bg_primary']};
}}

/* ── SIDEBAR ── */
#Sidebar {{
    background-color: {t['bg_secondary']};
    border-right: 1px solid {t['border_subtle']};
    min-width: 220px;
    max-width: 280px;
}}

#SidebarHeader {{
    background-color: {t['bg_secondary']};
    padding: 16px 16px 8px 16px;
    border-bottom: 1px solid {t['border_subtle']};
}}

#AppTitle {{
    color: {t['text_primary']};
    font-size: 18px;
    font-weight: 700;
    letter-spacing: -0.3px;
}}

#SidebarNav QPushButton {{
    background-color: transparent;
    color: {t['text_secondary']};
    border: none;
    border-radius: 8px;
    padding: 8px 12px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
    margin: 1px 8px;
}}

#SidebarNav QPushButton:hover {{
    background-color: {t['surface_hover']};
    color: {t['text_primary']};
}}

#SidebarNav QPushButton[active="true"] {{
    background-color: {t['accent_subtle']};
    color: {t['accent']};
    font-weight: 600;
}}

/* ── TOOLBAR ── */
#Toolbar {{
    background-color: {t['bg_secondary']};
    border-bottom: 1px solid {t['border_subtle']};
    padding: 8px 16px;
    min-height: 52px;
    max-height: 52px;
}}

/* ── SEARCH BAR ── */
#SearchBar {{
    background-color: {t['input_bg']};
    border: 1.5px solid {t['border_default']};
    border-radius: 10px;
    padding: 6px 12px 6px 36px;
    color: {t['text_primary']};
    font-size: 13px;
    min-width: 240px;
}}

#SearchBar:focus {{
    border-color: {t['accent']};
    background-color: {t['surface_1']};
}}

#SearchBar::placeholder {{
    color: {t['text_tertiary']};
}}

/* ── BUTTONS ── */
QPushButton {{
    background-color: {t['surface_1']};
    color: {t['text_primary']};
    border: 1px solid {t['border_default']};
    border-radius: 8px;
    padding: 7px 14px;
    font-size: 13px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {t['surface_hover']};
    border-color: {t['border_strong']};
}}

QPushButton:pressed {{
    background-color: {t['surface_active']};
}}

QPushButton:disabled {{
    color: {t['text_disabled']};
    border-color: {t['border_subtle']};
}}

QPushButton#PrimaryButton {{
    background-color: {t['accent']};
    color: {t['accent_text']};
    border: none;
    font-weight: 600;
}}

QPushButton#PrimaryButton:hover {{
    background-color: {t['accent_hover']};
}}

QPushButton#PrimaryButton:pressed {{
    background-color: {t['accent_pressed']};
}}

QPushButton#IconButton {{
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 6px;
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    max-height: 32px;
}}

QPushButton#IconButton:hover {{
    background-color: {t['surface_hover']};
}}

QPushButton#DangerButton {{
    background-color: transparent;
    color: {t['error']};
    border: 1px solid {t['error']};
}}

QPushButton#DangerButton:hover {{
    background-color: {_with_alpha(t['error'], 30)};
}}

/* ── SCROLL AREAS ── */
QScrollArea {{
    background-color: transparent;
    border: none;
}}

QScrollBar:vertical {{
    background-color: {t['scrollbar_bg']};
    width: 6px;
    border-radius: 3px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background-color: {t['scrollbar_handle']};
    border-radius: 3px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {t['scrollbar_hover']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
    background: none;
}}

QScrollBar:horizontal {{
    background-color: {t['scrollbar_bg']};
    height: 6px;
    border-radius: 3px;
}}

QScrollBar::handle:horizontal {{
    background-color: {t['scrollbar_handle']};
    border-radius: 3px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {t['scrollbar_hover']};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
    background: none;
}}

/* ── LIST WIDGETS ── */
QListWidget {{
    background-color: transparent;
    border: none;
    outline: none;
}}

QListWidget::item {{
    background-color: transparent;
    border-radius: 8px;
    padding: 4px;
    margin: 2px 8px;
}}

QListWidget::item:hover {{
    background-color: {t['surface_hover']};
}}

QListWidget::item:selected {{
    background-color: {t['accent_subtle']};
    color: {t['text_primary']};
}}

/* ── TREE WIDGET (folder tree) ── */
QTreeWidget {{
    background-color: transparent;
    border: none;
    outline: none;
}}

QTreeWidget::item {{
    height: 32px;
    border-radius: 6px;
    padding: 2px 4px;
}}

QTreeWidget::item:hover {{
    background-color: {t['surface_hover']};
}}

QTreeWidget::item:selected {{
    background-color: {t['accent_subtle']};
    color: {t['accent']};
}}

QTreeWidget::branch {{
    background-color: transparent;
}}

/* ── TEXT EDITOR ── */
QTextEdit, QPlainTextEdit {{
    background-color: {t['bg_primary']};
    color: {t['text_primary']};
    border: none;
    padding: 8px;
    font-size: 14px;
    line-height: 1.6;
    selection-background-color: {t['selection_bg']};
}}

QTextEdit:focus, QPlainTextEdit:focus {{
    background-color: {t['bg_primary']};
}}

/* ── LINE EDIT ── */
QLineEdit {{
    background-color: {t['input_bg']};
    color: {t['text_primary']};
    border: 1.5px solid {t['border_default']};
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 13px;
    selection-background-color: {t['selection_bg']};
}}

QLineEdit:focus {{
    border-color: {t['accent']};
}}

QLineEdit:read-only {{
    color: {t['text_secondary']};
    background-color: {t['bg_tertiary']};
}}

/* ── COMBO BOX ── */
QComboBox {{
    background-color: {t['surface_1']};
    color: {t['text_primary']};
    border: 1px solid {t['border_default']};
    border-radius: 8px;
    padding: 6px 32px 6px 10px;
    font-size: 13px;
}}

QComboBox:hover {{
    border-color: {t['border_strong']};
}}

QComboBox:focus {{
    border-color: {t['accent']};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox QAbstractItemView {{
    background-color: {t['bg_elevated']};
    border: 1px solid {t['border_default']};
    border-radius: 8px;
    padding: 4px;
    outline: none;
    selection-background-color: {t['accent_subtle']};
    selection-color: {t['text_primary']};
}}

/* ── SPIN BOX ── */
QSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {{
    background-color: {t['input_bg']};
    color: {t['text_primary']};
    border: 1.5px solid {t['border_default']};
    border-radius: 8px;
    padding: 5px 8px;
    font-size: 13px;
}}

QSpinBox:focus, QDateEdit:focus {{
    border-color: {t['accent']};
}}

/* ── CHECK BOX ── */
QCheckBox {{
    color: {t['text_primary']};
    spacing: 8px;
    font-size: 13px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {t['border_strong']};
    border-radius: 5px;
    background-color: {t['input_bg']};
}}

QCheckBox::indicator:checked {{
    background-color: {t['accent']};
    border-color: {t['accent']};
    image: none;
}}

QCheckBox::indicator:hover {{
    border-color: {t['accent']};
}}

/* ── SPLITTER ── */
QSplitter::handle {{
    background-color: {t['border_subtle']};
}}

QSplitter::handle:horizontal {{
    width: 1px;
}}

QSplitter::handle:vertical {{
    height: 1px;
}}

QSplitter::handle:hover {{
    background-color: {t['accent']};
}}

/* ── TABS ── */
QTabWidget::pane {{
    border: none;
    background-color: {t['bg_primary']};
}}

QTabBar::tab {{
    background-color: transparent;
    color: {t['text_tertiary']};
    border: none;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
    border-bottom: 2px solid transparent;
}}

QTabBar::tab:hover {{
    color: {t['text_secondary']};
}}

QTabBar::tab:selected {{
    color: {t['accent']};
    border-bottom: 2px solid {t['accent']};
}}

/* ── MENU ── */
QMenu {{
    background-color: {t['bg_elevated']};
    border: 1px solid {t['border_default']};
    border-radius: 10px;
    padding: 6px;
}}

QMenu::item {{
    background-color: transparent;
    color: {t['text_primary']};
    border-radius: 6px;
    padding: 7px 14px;
    font-size: 13px;
}}

QMenu::item:selected {{
    background-color: {t['surface_hover']};
}}

QMenu::item:disabled {{
    color: {t['text_disabled']};
}}

QMenu::separator {{
    height: 1px;
    background-color: {t['border_subtle']};
    margin: 4px 8px;
}}

/* ── TOOLTIP ── */
QToolTip {{
    background-color: {t['bg_elevated']};
    color: {t['text_primary']};
    border: 1px solid {t['border_default']};
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 12px;
}}

/* ── PROGRESS BAR ── */
QProgressBar {{
    background-color: {t['surface_border']};
    border-radius: 4px;
    height: 6px;
    text-align: center;
    font-size: 0px;
}}

QProgressBar::chunk {{
    background-color: {t['accent']};
    border-radius: 4px;
}}

/* ── LABEL ── */
QLabel {{
    background-color: transparent;
    color: {t['text_primary']};
}}

QLabel#SecondaryLabel {{
    color: {t['text_secondary']};
    font-size: 12px;
}}

QLabel#TertiaryLabel {{
    color: {t['text_tertiary']};
    font-size: 11px;
}}

/* ── STATUS BAR ── */
QStatusBar {{
    background-color: {t['bg_secondary']};
    color: {t['text_tertiary']};
    border-top: 1px solid {t['border_subtle']};
    font-size: 12px;
    padding: 0 8px;
}}

/* ── DIALOG ── */
QDialog {{
    background-color: {t['bg_secondary']};
    border-radius: 12px;
}}

/* ── GROUP BOX ── */
QGroupBox {{
    border: 1px solid {t['border_subtle']};
    border-radius: 10px;
    margin-top: 12px;
    padding-top: 8px;
    font-size: 12px;
    color: {t['text_secondary']};
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    left: 12px;
}}

/* ── FRAME ── */
QFrame[frameShape="4"],
QFrame[frameShape="5"] {{
    color: {t['border_subtle']};
}}

/* ── MESSAGE BOX ── */
QMessageBox {{
    background-color: {t['bg_secondary']};
}}

/* ── HEADER VIEW (tables) ── */
QHeaderView::section {{
    background-color: {t['bg_tertiary']};
    color: {t['text_secondary']};
    border: none;
    border-right: 1px solid {t['border_subtle']};
    border-bottom: 1px solid {t['border_subtle']};
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.4px;
}}

/* ── TABLE WIDGET ── */
QTableWidget {{
    background-color: {t['surface_1']};
    gridline-color: {t['border_subtle']};
    border: 1px solid {t['border_default']};
    border-radius: 8px;
}}

QTableWidget::item {{
    padding: 6px 10px;
}}

QTableWidget::item:selected {{
    background-color: {t['accent_subtle']};
    color: {t['text_primary']};
}}

/* ── SLIDER ── */
QSlider::groove:horizontal {{
    background-color: {t['surface_border']};
    height: 4px;
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background-color: {t['accent']};
    width: 14px;
    height: 14px;
    border-radius: 7px;
    margin: -5px 0;
}}

QSlider::sub-page:horizontal {{
    background-color: {t['accent']};
    border-radius: 2px;
}}

/* ── CARD WIDGET ── */
#Card {{
    background-color: {t['surface_1']};
    border: 1px solid {t['border_subtle']};
    border-radius: 12px;
}}

#Card:hover {{
    border-color: {t['border_default']};
    background-color: {t['surface_hover']};
}}

#Card[selected="true"] {{
    border-color: {t['accent']};
    background-color: {t['accent_subtle']};
}}

/* ── NOTE CARD ── */
#NoteCard {{
    background-color: {t['surface_1']};
    border: 1px solid {t['border_subtle']};
    border-radius: 10px;
    padding: 12px;
}}

#NoteCard:hover {{
    border-color: {t['border_default']};
}}

#NoteCard[pinned="true"] {{
    border-left: 3px solid {t['accent']};
}}

/* ── TASK ITEM ── */
#TaskItem {{
    background-color: {t['surface_1']};
    border: 1px solid {t['border_subtle']};
    border-radius: 8px;
    margin: 2px 0;
}}

#TaskItem:hover {{
    border-color: {t['border_default']};
    background-color: {t['surface_hover']};
}}

/* ── KANBAN COLUMN ── */
#KanbanColumn {{
    background-color: {t['bg_tertiary']};
    border-radius: 12px;
    min-width: 260px;
    max-width: 320px;
}}

#KanbanColumnHeader {{
    background-color: transparent;
    border-bottom: 2px solid {t['border_subtle']};
    padding: 12px;
}}

/* ── POMODORO WIDGET ── */
#PomodoroTimer {{
    background-color: {t['surface_2']};
    border-radius: 50%;
    border: 4px solid {t['accent']};
}}

/* ── SECTION HEADER ── */
#SectionHeader {{
    color: {t['text_tertiary']};
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 8px 16px 4px 16px;
}}

/* ── BADGE ── */
#Badge {{
    background-color: {t['accent']};
    color: {t['accent_text']};
    border-radius: 10px;
    padding: 2px 7px;
    font-size: 11px;
    font-weight: 700;
}}

/* ── TAG PILL ── */
#TagPill {{
    border-radius: 12px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}

/* ── EMPTY STATE ── */
#EmptyState {{
    color: {t['text_tertiary']};
    font-size: 14px;
}}

/* ── SPLASH SCREEN ── */
#SplashScreen {{
    background-color: {t['bg_primary']};
    border-radius: 16px;
}}
"""

    @property
    def is_dark(self) -> bool:
        return self._theme == "dark"

    @property
    def accent(self) -> str:
        return self._accent

    @property
    def theme(self) -> str:
        return self._theme

    @property
    def tokens(self) -> dict:
        return self._tokens.copy()


# Module-level singleton
theme = ThemeManager()
