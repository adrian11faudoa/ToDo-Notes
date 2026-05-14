"""
views/notes_view.py
───────────────────
Notes main view: resizable split-pane with note list on left
and rich markdown editor on right. Handles autosave, word count,
tags, color labels, export, and context menus.
"""

from __future__ import annotations
import re
from typing import Optional
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QScrollArea, QLabel, QPushButton, QTextEdit,
    QLineEdit, QFrame, QMenu, QFileDialog,
    QMessageBox, QToolBar, QSizePolicy, QComboBox,
)
from PySide6.QtCore import Qt, Signal, QTimer, QPoint, QThread, QObject
from PySide6.QtGui import (
    QFont, QTextCursor, QKeySequence, QAction,
    QTextCharFormat, QColor,
)

from app.themes.theme_manager import theme
from app.models.entities import Note, Folder, Tag
from app.services.note_service import note_service
from app.widgets.common import (
    NoteCard, SearchBar, EmptyState, TagPill,
    SectionHeader, IconButton, HDivider, NOTE_COLORS,
)


# ──────────────────────────────────────────────────────────────────
# NOTE LIST PANEL
# ──────────────────────────────────────────────────────────────────

class NoteListPanel(QWidget):
    """Left panel: searchable, scrollable list of NoteCard widgets."""

    note_selected = Signal(int)
    note_create_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NoteListPanel")
        self.setFixedWidth(280)
        self._notes: list[Note] = []
        self._selected_id: Optional[int] = None
        self._card_map: dict[int, NoteCard] = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar ─────────────────────────────────
        toolbar = QWidget()
        toolbar.setFixedHeight(52)
        toolbar.setStyleSheet(
            f"background: {theme.t('bg_secondary')};"
            f"border-bottom: 1px solid {theme.t('border_subtle')};"
        )
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(12, 8, 12, 8)
        tl.setSpacing(8)

        self._title_lbl = QLabel("Notes")
        self._title_lbl.setFont(QFont("Segoe UI", 15, QFont.DemiBold))
        self._title_lbl.setStyleSheet("background: transparent;")

        new_btn = QPushButton("＋")
        new_btn.setObjectName("PrimaryButton")
        new_btn.setFixedSize(32, 32)
        new_btn.setFont(QFont("Segoe UI", 16))
        new_btn.setToolTip("New note  (Ctrl+N)")
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.clicked.connect(self.note_create_requested.emit)

        tl.addWidget(self._title_lbl, 1)
        tl.addWidget(new_btn)
        layout.addWidget(toolbar)

        # ── Search ────────────────────────────────────
        search_wrap = QWidget()
        search_wrap.setFixedHeight(44)
        search_wrap.setStyleSheet(
            f"background: {theme.t('bg_secondary')};"
        )
        sl = QHBoxLayout(search_wrap)
        sl.setContentsMargins(10, 6, 10, 6)

        self._search = SearchBar("Search notes…")
        self._search.search_changed.connect(self._on_search)
        sl.addWidget(self._search)
        layout.addWidget(search_wrap)

        # ── Sort / Filter bar ─────────────────────────
        filter_bar = QWidget()
        filter_bar.setFixedHeight(34)
        filter_bar.setStyleSheet(
            f"background: {theme.t('bg_secondary')};"
            f"border-bottom: 1px solid {theme.t('border_subtle')};"
        )
        fl = QHBoxLayout(filter_bar)
        fl.setContentsMargins(10, 0, 10, 0)
        fl.setSpacing(4)

        sort_combo = QComboBox()
        sort_combo.addItems(["↕ Recent", "↕ Oldest", "↕ Title A–Z", "↕ Title Z–A"])
        sort_combo.setFixedHeight(26)
        sort_combo.setStyleSheet("font-size: 11px;")
        fl.addWidget(sort_combo)
        fl.addStretch()

        self._count_lbl = QLabel("0 notes")
        self._count_lbl.setFont(QFont("Segoe UI", 11))
        self._count_lbl.setStyleSheet(
            f"color: {theme.t('text_tertiary')}; background: transparent;"
        )
        fl.addWidget(self._count_lbl)
        layout.addWidget(filter_bar)

        # ── Note list ─────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background: {theme.t('bg_primary')}; border: none; }}"
        )

        self._list_container = QWidget()
        self._list_container.setStyleSheet(
            f"background: {theme.t('bg_primary')};"
        )
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 6, 0, 6)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._list_container)
        layout.addWidget(self._scroll, 1)

    def load_notes(self, notes: list[Note], title: str = "Notes"):
        """Replace current note list with new data."""
        self._title_lbl.setText(title)
        self._notes = notes
        self._card_map.clear()
        self._count_lbl.setText(f"{len(notes)} note{'s' if len(notes) != 1 else ''}")

        # Clear old cards (keep stretch at end)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not notes:
            empty = EmptyState("📝", "No notes yet",
                               "Press ＋ to create your first note")
            self._list_layout.insertWidget(0, empty)
            return

        # Pinned separator
        pinned = [n for n in notes if n.is_pinned]
        unpinned = [n for n in notes if not n.is_pinned]

        if pinned:
            self._list_layout.insertWidget(
                0, SectionHeader("Pinned"), alignment=Qt.AlignLeft
            )
            for i, note in enumerate(pinned):
                card = NoteCard(note)
                card.clicked.connect(self._on_card_clicked)
                card.context_requested.connect(self._on_context_menu)
                self._card_map[note.id] = card
                self._list_layout.insertWidget(i + 1, card)

        offset = len(pinned) + (2 if pinned else 0)
        if unpinned and pinned:
            self._list_layout.insertWidget(
                offset, SectionHeader("Notes"), alignment=Qt.AlignLeft
            )
            offset += 1

        for i, note in enumerate(unpinned):
            card = NoteCard(note)
            card.clicked.connect(self._on_card_clicked)
            card.context_requested.connect(self._on_context_menu)
            self._card_map[note.id] = card
            self._list_layout.insertWidget(offset + i, card)

        # Re-select if still present
        if self._selected_id and self._selected_id in self._card_map:
            self._card_map[self._selected_id].set_selected(True)

    def select_note(self, note_id: int):
        for nid, card in self._card_map.items():
            card.set_selected(nid == note_id)
        self._selected_id = note_id

    def _on_card_clicked(self, note_id: int):
        self.select_note(note_id)
        self.note_selected.emit(note_id)

    def _on_search(self, query: str):
        if query:
            results = note_service.search_notes(query)
        else:
            results = note_service.get_all_notes()
        self.load_notes(results, title=f"Results for "{query}"" if query else "Notes")

    def _on_context_menu(self, note_id: int, pos: QPoint):
        note = note_service.get_note(note_id)
        if not note:
            return

        menu = QMenu(self)
        menu.addAction("✏️  Open", lambda: self.note_selected.emit(note_id))
        menu.addSeparator()

        pin_lbl = "📌  Unpin" if note.is_pinned else "📌  Pin to top"
        menu.addAction(pin_lbl, lambda: self._toggle_pin(note))
        menu.addAction("📦  Archive", lambda: self._archive_note(note_id))

        color_menu = menu.addMenu("🎨  Color label")
        for name, hex_col in NOTE_COLORS.items():
            color_menu.addAction(name.title(),
                                 lambda c=name: note_service.set_color_label(note_id, c))
        color_menu.addAction("Clear", lambda: note_service.set_color_label(note_id, None))

        export_menu = menu.addMenu("📤  Export")
        export_menu.addAction("Text (.txt)", lambda: self._export(note, "txt"))
        export_menu.addAction("Markdown (.md)", lambda: self._export(note, "md"))
        export_menu.addAction("PDF (.pdf)", lambda: self._export(note, "pdf"))

        menu.addSeparator()
        menu.addAction("🗑️  Delete", lambda: self._delete_note(note_id))
        menu.exec(pos)

    def _toggle_pin(self, note: Note):
        note_service.pin_note(note.id, not note.is_pinned)

    def _archive_note(self, note_id: int):
        note_service.archive_note(note_id, True)

    def _delete_note(self, note_id: int):
        note_service.delete_note(note_id)

    def _export(self, note: Note, fmt: str):
        filters = {"txt": "Text (*.txt)", "md": "Markdown (*.md)", "pdf": "PDF (*.pdf)"}
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export as {fmt.upper()}", note.title,
            filters[fmt]
        )
        if path:
            note_service.export_note(note, fmt, path)


# ──────────────────────────────────────────────────────────────────
# MARKDOWN EDITOR
# ──────────────────────────────────────────────────────────────────

class MarkdownEditor(QTextEdit):
    """
    Plain-text markdown editor with syntax highlighting hints.
    Sends content_changed signal for autosave.
    """
    content_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setFont(QFont("Cascadia Code, Consolas, Courier New", 14))
        self.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setPlaceholderText(
            "Start writing… (Markdown supported)\n\n"
            "# Heading 1\n## Heading 2\n**bold**  *italic*  `code`\n- List item"
        )
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(500)
        self._debounce.timeout.connect(self._emit_changed)
        self.textChanged.connect(self._debounce.start)

    def _emit_changed(self):
        self.content_changed.emit(self.toPlainText())


# ──────────────────────────────────────────────────────────────────
# NOTE EDITOR PANEL
# ──────────────────────────────────────────────────────────────────

class NoteEditorPanel(QWidget):
    """
    Right panel: full note editor with title, toolbar, markdown area,
    tags, metadata footer, and autosave.
    """

    note_updated = Signal(int)   # signals list to refresh

    def __init__(self, parent=None):
        super().__init__(parent)
        self._note: Optional[Note] = None
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(3000)  # 3s autosave
        self._autosave_timer.timeout.connect(self._autosave)
        self._dirty = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Editor Toolbar ────────────────────────────
        self._toolbar = self._build_toolbar()
        layout.addWidget(self._toolbar)

        # ── Content area ─────────────────────────────
        content = QWidget()
        content.setStyleSheet(f"background: {theme.t('bg_primary')};")
        c_layout = QVBoxLayout(content)
        c_layout.setContentsMargins(40, 24, 40, 12)
        c_layout.setSpacing(8)

        # Title
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Note title…")
        self._title_edit.setFont(QFont("Segoe UI", 22, QFont.DemiBold))
        self._title_edit.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                border-bottom: 2px solid {theme.t('border_subtle')};
                border-radius: 0;
                color: {theme.t('text_primary')};
                padding: 4px 0;
            }}
            QLineEdit:focus {{ border-bottom-color: {theme.t('accent')}; }}
        """)
        self._title_edit.textChanged.connect(self._on_title_changed)
        c_layout.addWidget(self._title_edit)

        # Tags row
        self._tags_row = QWidget()
        self._tags_row.setStyleSheet("background: transparent;")
        tags_layout = QHBoxLayout(self._tags_row)
        tags_layout.setContentsMargins(0, 4, 0, 4)
        tags_layout.setSpacing(4)

        self._tags_container = QHBoxLayout()
        self._tags_container.setSpacing(4)
        tags_layout.addLayout(self._tags_container)

        add_tag_btn = QPushButton("+ tag")
        add_tag_btn.setFlat(True)
        add_tag_btn.setCursor(Qt.PointingHandCursor)
        add_tag_btn.setFixedHeight(20)
        add_tag_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {theme.t('text_tertiary')}; font-size: 11px;
            }}
            QPushButton:hover {{ color: {theme.t('accent')}; }}
        """)
        add_tag_btn.clicked.connect(self._add_tag_prompt)
        tags_layout.addWidget(add_tag_btn)
        tags_layout.addStretch()

        c_layout.addWidget(self._tags_row)

        # Markdown editor
        self._editor = MarkdownEditor()
        self._editor.content_changed.connect(self._on_content_changed)
        c_layout.addWidget(self._editor, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # ── Status bar ────────────────────────────────
        self._status_bar = self._build_status_bar()
        layout.addWidget(self._status_bar)

        # ── Empty state ───────────────────────────────
        self._empty = EmptyState(
            "📄", "Select a note", "or press ＋ to create a new one"
        )
        layout.addWidget(self._empty)

        self._show_empty(True)

    def _build_toolbar(self) -> QWidget:
        toolbar = QWidget()
        toolbar.setObjectName("Toolbar")
        toolbar.setFixedHeight(44)
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(12, 0, 12, 0)
        tl.setSpacing(2)

        def fmt_btn(symbol: str, tooltip: str, action) -> QPushButton:
            btn = QPushButton(symbol)
            btn.setObjectName("IconButton")
            btn.setFixedSize(34, 34)
            btn.setFont(QFont("Segoe UI", 14))
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(action)
            return btn

        tl.addWidget(fmt_btn("𝐁", "Bold (Ctrl+B)", self._fmt_bold))
        tl.addWidget(fmt_btn("𝐼", "Italic (Ctrl+I)", self._fmt_italic))
        tl.addWidget(fmt_btn("𝚄", "Underline (Ctrl+U)", self._fmt_underline))
        tl.addWidget(fmt_btn("`", "Inline code", self._fmt_code))
        tl.addWidget(fmt_btn("—", "Strikethrough", self._fmt_strike))

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedHeight(20)
        sep.setStyleSheet(f"color: {theme.t('border_subtle')};")
        tl.addWidget(sep)

        tl.addWidget(fmt_btn("H1", "Heading 1", lambda: self._fmt_heading(1)))
        tl.addWidget(fmt_btn("H2", "Heading 2", lambda: self._fmt_heading(2)))
        tl.addWidget(fmt_btn("H3", "Heading 3", lambda: self._fmt_heading(3)))

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setFixedHeight(20)
        sep2.setStyleSheet(f"color: {theme.t('border_subtle')};")
        tl.addWidget(sep2)

        tl.addWidget(fmt_btn("≡", "Bullet list", self._fmt_bullet))
        tl.addWidget(fmt_btn("1.", "Numbered list", self._fmt_numbered))
        tl.addWidget(fmt_btn("☐", "Task list item", self._fmt_task))
        tl.addWidget(fmt_btn("❝", "Blockquote", self._fmt_quote))

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.VLine)
        sep3.setFixedHeight(20)
        sep3.setStyleSheet(f"color: {theme.t('border_subtle')};")
        tl.addWidget(sep3)

        tl.addWidget(fmt_btn("🖼", "Insert image", self._insert_image))
        tl.addWidget(fmt_btn("🔗", "Insert link", self._fmt_link))

        tl.addStretch()

        self._save_indicator = QLabel("✓ Saved")
        self._save_indicator.setFont(QFont("Segoe UI", 11))
        self._save_indicator.setStyleSheet(
            f"color: {theme.t('text_tertiary')}; background: transparent;"
        )
        tl.addWidget(self._save_indicator)

        export_btn = QPushButton("Export ▾")
        export_btn.setFixedHeight(30)
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.clicked.connect(self._show_export_menu)
        tl.addWidget(export_btn)

        return toolbar

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(28)
        bar.setStyleSheet(
            f"background: {theme.t('bg_secondary')};"
            f"border-top: 1px solid {theme.t('border_subtle')};"
        )
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 0, 16, 0)
        bl.setSpacing(16)

        self._word_count_lbl = QLabel("0 words")
        self._char_count_lbl = QLabel("0 chars")
        self._modified_lbl = QLabel("")

        for lbl in (self._word_count_lbl, self._char_count_lbl, self._modified_lbl):
            lbl.setFont(QFont("Segoe UI", 11))
            lbl.setStyleSheet(
                f"color: {theme.t('text_tertiary')}; background: transparent;"
            )
            bl.addWidget(lbl)

        bl.addStretch()
        return bar

    # ── Public API ────────────────────────────────────────────────

    def load_note(self, note: Note):
        self._note = note
        self._dirty = False
        self._show_empty(False)

        self._title_edit.blockSignals(True)
        self._title_edit.setText(note.title)
        self._title_edit.blockSignals(False)

        self._editor.blockSignals(True)
        self._editor.setPlainText(note.content)
        self._editor.blockSignals(False)

        self._refresh_tags()
        self._update_status()
        self._save_indicator.setText("✓ Saved")

    def _show_empty(self, empty: bool):
        self._empty.setVisible(empty)
        self._toolbar.setVisible(not empty)
        self._title_edit.setVisible(not empty)
        self._tags_row.setVisible(not empty)
        self._editor.setVisible(not empty)
        self._status_bar.setVisible(not empty)

    # ── Editing events ────────────────────────────────────────────

    def _on_title_changed(self, text: str):
        if self._note:
            self._dirty = True
            self._save_indicator.setText("● Unsaved")
            self._autosave_timer.start()

    def _on_content_changed(self, content: str):
        if self._note:
            self._dirty = True
            self._save_indicator.setText("● Unsaved")
            self._update_status()
            self._autosave_timer.start()

    def _autosave(self):
        if not self._note or not self._dirty:
            return
        note_service.update_note(
            self._note.id,
            title=self._title_edit.text() or "Untitled Note",
            content=self._editor.toPlainText(),
        )
        self._dirty = False
        self._save_indicator.setText("✓ Saved")
        self.note_updated.emit(self._note.id)

    def _update_status(self):
        if not self._note:
            return
        content = self._editor.toPlainText()
        words = len(content.split()) if content.strip() else 0
        chars = len(content)
        self._word_count_lbl.setText(f"{words:,} words")
        self._char_count_lbl.setText(f"{chars:,} chars")
        if self._note.updated_at:
            self._modified_lbl.setText(
                f"Edited {self._note.updated_at.strftime('%b %d, %H:%M')}"
            )

    # ── Formatting helpers ────────────────────────────────────────

    def _wrap_selection(self, prefix: str, suffix: str = ""):
        cursor = self._editor.textCursor()
        suffix = suffix or prefix
        if cursor.hasSelection():
            text = cursor.selectedText()
            cursor.insertText(f"{prefix}{text}{suffix}")
        else:
            cursor.insertText(f"{prefix}{suffix}")
            cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, len(suffix))
        self._editor.setTextCursor(cursor)
        self._editor.setFocus()

    def _prepend_line(self, prefix: str):
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.StartOfLine)
        cursor.insertText(prefix)
        self._editor.setTextCursor(cursor)
        self._editor.setFocus()

    def _fmt_bold(self):         self._wrap_selection("**")
    def _fmt_italic(self):       self._wrap_selection("*")
    def _fmt_underline(self):    self._wrap_selection("<u>", "</u>")
    def _fmt_code(self):         self._wrap_selection("`")
    def _fmt_strike(self):       self._wrap_selection("~~")
    def _fmt_bullet(self):       self._prepend_line("- ")
    def _fmt_numbered(self):     self._prepend_line("1. ")
    def _fmt_task(self):         self._prepend_line("- [ ] ")
    def _fmt_quote(self):        self._prepend_line("> ")
    def _fmt_link(self):         self._wrap_selection("[", "](url)")

    def _fmt_heading(self, level: int):
        self._prepend_line("#" * level + " ")

    def _insert_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Insert Image", "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.svg)"
        )
        if path and self._note:
            attachment = note_service.add_attachment(self._note.id, path)
            self._editor.insertPlainText(f"\n![{attachment.filename}]({path})\n")

    # ── Tags ──────────────────────────────────────────────────────

    def _refresh_tags(self):
        while self._tags_container.count():
            item = self._tags_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if self._note:
            for tag in self._note.tags:
                pill = TagPill(tag, removable=True)
                pill.clicked.connect(lambda t, tid=tag.id: self._remove_tag(tid))
                self._tags_container.addWidget(pill)

    def _add_tag_prompt(self):
        if not self._note:
            return
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "Add Tag", "Tag name:")
        if ok and text.strip():
            tag = note_service.add_tag_to_note(self._note.id, text.strip().lower())
            self._note.tags.append(tag)
            self._refresh_tags()

    def _remove_tag(self, tag_id: int):
        if not self._note:
            return
        note_service.remove_tag_from_note(self._note.id, tag_id)
        self._note.tags = [t for t in self._note.tags if t.id != tag_id]
        self._refresh_tags()

    # ── Export ────────────────────────────────────────────────────

    def _show_export_menu(self):
        if not self._note:
            return
        menu = QMenu(self)
        menu.addAction("Export as Text (.txt)",     lambda: self._export("txt"))
        menu.addAction("Export as Markdown (.md)",  lambda: self._export("md"))
        menu.addAction("Export as PDF (.pdf)",      lambda: self._export("pdf"))
        menu.exec(self._toolbar.mapToGlobal(self._toolbar.rect().bottomRight()))

    def _export(self, fmt: str):
        if not self._note:
            return
        filters = {"txt": "Text (*.txt)", "md": "Markdown (*.md)", "pdf": "PDF (*.pdf)"}
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export Note", self._note.title, filters[fmt]
        )
        if path:
            self._autosave()  # save first
            note_service.export_note(self._note, fmt, path)


# ──────────────────────────────────────────────────────────────────
# NOTES VIEW (split pane)
# ──────────────────────────────────────────────────────────────────

class NotesView(QWidget):
    """
    Main notes view: list panel + editor panel in a resizable splitter.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_folder_id: Optional[int] = None
        self._build_ui()
        self._load_notes()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)

        self._list_panel = NoteListPanel()
        self._list_panel.note_selected.connect(self._on_note_selected)
        self._list_panel.note_create_requested.connect(self._create_note)

        self._editor_panel = NoteEditorPanel()
        self._editor_panel.note_updated.connect(self._on_note_updated)

        splitter.addWidget(self._list_panel)
        splitter.addWidget(self._editor_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 800])

        layout.addWidget(splitter)

    def _load_notes(self, folder_id: Optional[int] = None):
        self._current_folder_id = folder_id
        notes = note_service.get_all_notes(folder_id=folder_id)
        self._list_panel.load_notes(notes)

    def _on_note_selected(self, note_id: int):
        note = note_service.get_note(note_id)
        if note:
            self._editor_panel.load_note(note)

    def _create_note(self):
        note = note_service.create_note(folder_id=self._current_folder_id)
        self._load_notes(self._current_folder_id)
        self._list_panel.select_note(note.id)
        self._editor_panel.load_note(note)

    def _on_note_updated(self, note_id: int):
        # Refresh the card in the list
        note = note_service.get_note(note_id)
        if note and note_id in self._list_panel._card_map:
            self._list_panel._card_map[note_id].update_note(note)

    def set_folder(self, folder_id: Optional[int]):
        self._load_notes(folder_id)

    def set_archived(self, archived: bool):
        notes = note_service.get_all_notes(archived=archived)
        title = "Archive" if archived else "Notes"
        self._list_panel.load_notes(notes, title=title)

    def set_trash(self):
        notes = note_service.get_trash()
        self._list_panel.load_notes(notes, title="Trash")

    def show_search(self, query: str):
        self._list_panel._search.setText(query)

    def refresh(self):
        self._load_notes(self._current_folder_id)
