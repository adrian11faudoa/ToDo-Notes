"""
services/note_service.py
────────────────────────
Business logic layer for Notes.
All note operations go through here — never query the DB from views.
"""

from __future__ import annotations
import json
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.database.connection import db
from app.models.entities import Note, Folder, Tag, NoteAttachment

logger = logging.getLogger(__name__)


def _row_to_note(row) -> Note:
    """Convert a sqlite3.Row to a Note dataclass."""
    d = dict(row)
    return Note(
        id=d["id"],
        title=d["title"],
        content=d.get("content", ""),
        content_html=d.get("content_html", ""),
        folder_id=d.get("folder_id"),
        color_label=d.get("color_label"),
        is_pinned=bool(d.get("is_pinned", 0)),
        is_archived=bool(d.get("is_archived", 0)),
        is_deleted=bool(d.get("is_deleted", 0)),
        word_count=d.get("word_count", 0),
        char_count=d.get("char_count", 0),
        sort_order=d.get("sort_order", 0),
        created_at=_parse_dt(d.get("created_at")),
        updated_at=_parse_dt(d.get("updated_at")),
        folder_name=d.get("folder_name", ""),
    )


def _parse_dt(val) -> datetime:
    if val is None:
        return datetime.now()
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except ValueError:
        return datetime.now()


def _count_words(text: str) -> tuple[int, int]:
    """Return (word_count, char_count) for plain text."""
    clean = re.sub(r'[#*_`\[\]()>~]', '', text)
    words = len(clean.split()) if clean.strip() else 0
    chars = len(clean)
    return words, chars


class NoteService:
    """CRUD + search + export for Notes."""

    # ── CREATE ──────────────────────────────────────────

    def create_note(self, title: str = "Untitled Note",
                    folder_id: Optional[int] = None) -> Note:
        with db.transaction() as conn:
            cur = conn.execute(
                """INSERT INTO notes (title, content, folder_id, created_at, updated_at)
                   VALUES (?, '', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                (title, folder_id)
            )
            note_id = cur.lastrowid
            self._snapshot(conn, "note", note_id, "create", {"title": title})
        return self.get_note(note_id)

    # ── READ ─────────────────────────────────────────────

    def get_note(self, note_id: int) -> Optional[Note]:
        row = db.fetchone(
            """SELECT n.*, f.name AS folder_name
               FROM notes n
               LEFT JOIN folders f ON n.folder_id = f.id
               WHERE n.id = ? AND n.is_deleted = 0""",
            (note_id,)
        )
        if not row:
            return None
        note = _row_to_note(row)
        note.tags = self._get_note_tags(note_id)
        note.attachments = self._get_note_attachments(note_id)
        return note

    def get_all_notes(self, folder_id: Optional[int] = None,
                      archived: bool = False,
                      pinned_first: bool = True) -> list[Note]:
        conditions = ["n.is_deleted = 0", f"n.is_archived = {1 if archived else 0}"]
        params: list = []

        if folder_id is not None:
            conditions.append("n.folder_id = ?")
            params.append(folder_id)

        where = " AND ".join(conditions)
        order = "n.is_pinned DESC, n.updated_at DESC" if pinned_first else "n.updated_at DESC"

        rows = db.fetchall(
            f"""SELECT n.*, f.name AS folder_name
                FROM notes n
                LEFT JOIN folders f ON n.folder_id = f.id
                WHERE {where}
                ORDER BY {order}""",
            params
        )
        notes = [_row_to_note(r) for r in rows]
        # Batch-load tags
        if notes:
            tag_map = self._batch_load_tags([n.id for n in notes])
            for n in notes:
                n.tags = tag_map.get(n.id, [])
        return notes

    def get_notes_by_tag(self, tag_id: int) -> list[Note]:
        rows = db.fetchall(
            """SELECT n.*, f.name AS folder_name
               FROM notes n
               LEFT JOIN folders f ON n.folder_id = f.id
               JOIN note_tags nt ON nt.note_id = n.id
               WHERE nt.tag_id = ? AND n.is_deleted = 0
               ORDER BY n.updated_at DESC""",
            (tag_id,)
        )
        return [_row_to_note(r) for r in rows]

    def search_notes(self, query: str) -> list[Note]:
        """Full-text search using FTS5."""
        if not query.strip():
            return self.get_all_notes()
        safe_query = query.replace('"', '""')
        rows = db.fetchall(
            """SELECT n.*, f.name AS folder_name,
                      snippet(notes_fts, 1, '<b>', '</b>', '…', 15) AS snippet
               FROM notes_fts
               JOIN notes n ON notes_fts.rowid = n.id
               LEFT JOIN folders f ON n.folder_id = f.id
               WHERE notes_fts MATCH ? AND n.is_deleted = 0
               ORDER BY rank""",
            (f'"{safe_query}"',)
        )
        return [_row_to_note(r) for r in rows]

    # ── UPDATE ───────────────────────────────────────────

    def update_note(self, note_id: int, **kwargs) -> bool:
        """
        Update arbitrary note fields.
        Pass keyword args matching column names.
        Auto-calculates word/char count if content changes.
        """
        allowed = {
            "title", "content", "content_html", "folder_id",
            "color_label", "is_pinned", "is_archived", "sort_order"
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False

        if "content" in updates:
            wc, cc = _count_words(updates["content"])
            updates["word_count"] = wc
            updates["char_count"] = cc

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [note_id]

        with db.transaction() as conn:
            conn.execute(
                f"UPDATE notes SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                values
            )
            self._snapshot(conn, "note", note_id, "update", updates)
        return True

    def pin_note(self, note_id: int, pinned: bool):
        self.update_note(note_id, is_pinned=int(pinned))

    def archive_note(self, note_id: int, archived: bool):
        self.update_note(note_id, is_archived=int(archived))

    def move_note(self, note_id: int, folder_id: Optional[int]):
        self.update_note(note_id, folder_id=folder_id)

    def set_color_label(self, note_id: int, color: Optional[str]):
        self.update_note(note_id, color_label=color)

    # ── DELETE ───────────────────────────────────────────

    def delete_note(self, note_id: int, permanent: bool = False):
        with db.transaction() as conn:
            if permanent:
                conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            else:
                conn.execute(
                    "UPDATE notes SET is_deleted = 1, deleted_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (note_id,)
                )
            self._snapshot(conn, "note", note_id, "delete", {})

    def restore_note(self, note_id: int):
        with db.transaction() as conn:
            conn.execute(
                "UPDATE notes SET is_deleted = 0, deleted_at = NULL WHERE id = ?",
                (note_id,)
            )

    def empty_trash(self):
        with db.transaction() as conn:
            conn.execute("DELETE FROM notes WHERE is_deleted = 1")

    # ── TAGS ─────────────────────────────────────────────

    def _get_note_tags(self, note_id: int) -> list[Tag]:
        rows = db.fetchall(
            """SELECT t.* FROM tags t
               JOIN note_tags nt ON nt.tag_id = t.id
               WHERE nt.note_id = ?""",
            (note_id,)
        )
        return [Tag(id=r["id"], name=r["name"], color=r["color"]) for r in rows]

    def _batch_load_tags(self, note_ids: list[int]) -> dict[int, list[Tag]]:
        placeholders = ",".join("?" * len(note_ids))
        rows = db.fetchall(
            f"""SELECT nt.note_id, t.id, t.name, t.color
                FROM note_tags nt JOIN tags t ON nt.tag_id = t.id
                WHERE nt.note_id IN ({placeholders})""",
            note_ids
        )
        result: dict[int, list[Tag]] = {}
        for r in rows:
            result.setdefault(r["note_id"], []).append(
                Tag(id=r["id"], name=r["name"], color=r["color"])
            )
        return result

    def add_tag_to_note(self, note_id: int, tag_name: str) -> Tag:
        tag = self._get_or_create_tag(tag_name)
        with db.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)",
                (note_id, tag.id)
            )
        return tag

    def remove_tag_from_note(self, note_id: int, tag_id: int):
        with db.transaction() as conn:
            conn.execute(
                "DELETE FROM note_tags WHERE note_id = ? AND tag_id = ?",
                (note_id, tag_id)
            )

    def _get_or_create_tag(self, name: str) -> Tag:
        row = db.fetchone("SELECT * FROM tags WHERE name = ?", (name,))
        if row:
            return Tag(id=row["id"], name=row["name"], color=row["color"])
        with db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO tags (name) VALUES (?)", (name,)
            )
            return Tag(id=cur.lastrowid, name=name)

    def get_all_tags(self) -> list[Tag]:
        rows = db.fetchall("SELECT * FROM tags ORDER BY name")
        return [Tag(id=r["id"], name=r["name"], color=r["color"]) for r in rows]

    # ── FOLDERS ──────────────────────────────────────────

    def get_all_folders(self) -> list[Folder]:
        rows = db.fetchall(
            """SELECT f.*,
                      (SELECT COUNT(*) FROM notes n WHERE n.folder_id = f.id AND n.is_deleted = 0) AS note_count
               FROM folders f ORDER BY f.sort_order, f.name"""
        )
        return [Folder(
            id=r["id"], name=r["name"], parent_id=r["parent_id"],
            color=r["color"], icon=r["icon"], sort_order=r["sort_order"],
            note_count=r["note_count"],
        ) for r in rows]

    def create_folder(self, name: str, color: str = "#6C6C6C",
                      parent_id: Optional[int] = None) -> Folder:
        with db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO folders (name, color, parent_id) VALUES (?, ?, ?)",
                (name, color, parent_id)
            )
        return Folder(id=cur.lastrowid, name=name, color=color, parent_id=parent_id)

    def update_folder(self, folder_id: int, **kwargs):
        allowed = {"name", "color", "icon", "sort_order", "parent_id"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        with db.transaction() as conn:
            conn.execute(
                f"UPDATE folders SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                list(updates.values()) + [folder_id]
            )

    def delete_folder(self, folder_id: int):
        with db.transaction() as conn:
            # Move notes to no folder
            conn.execute("UPDATE notes SET folder_id = NULL WHERE folder_id = ?", (folder_id,))
            conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))

    # ── ATTACHMENTS ──────────────────────────────────────

    def _get_note_attachments(self, note_id: int) -> list[NoteAttachment]:
        rows = db.fetchall(
            "SELECT * FROM note_attachments WHERE note_id = ? ORDER BY created_at",
            (note_id,)
        )
        return [NoteAttachment(
            id=r["id"], note_id=r["note_id"], filename=r["filename"],
            filepath=r["filepath"], filetype=r["filetype"], filesize=r["filesize"],
        ) for r in rows]

    def add_attachment(self, note_id: int, filepath: str) -> NoteAttachment:
        p = Path(filepath)
        with db.transaction() as conn:
            cur = conn.execute(
                """INSERT INTO note_attachments (note_id, filename, filepath, filetype, filesize)
                   VALUES (?, ?, ?, ?, ?)""",
                (note_id, p.name, str(p), p.suffix.lower(), p.stat().st_size)
            )
        return NoteAttachment(
            id=cur.lastrowid, note_id=note_id, filename=p.name,
            filepath=str(p), filetype=p.suffix.lower(), filesize=p.stat().st_size
        )

    def remove_attachment(self, attachment_id: int):
        with db.transaction() as conn:
            conn.execute("DELETE FROM note_attachments WHERE id = ?", (attachment_id,))

    # ── EXPORT ───────────────────────────────────────────

    def export_note(self, note: Note, format: str, dest_path: str):
        """Export a note to txt, md, or pdf."""
        if format == "txt":
            self._export_txt(note, dest_path)
        elif format == "md":
            self._export_md(note, dest_path)
        elif format == "pdf":
            self._export_pdf(note, dest_path)
        else:
            raise ValueError(f"Unknown export format: {format}")

    def _export_txt(self, note: Note, path: str):
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{note.title}\n")
            f.write("=" * len(note.title) + "\n\n")
            f.write(note.content)

    def _export_md(self, note: Note, path: str):
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {note.title}\n\n")
            if note.tags:
                tags_str = " ".join(f"#{t.name}" for t in note.tags)
                f.write(f"{tags_str}\n\n")
            f.write(note.content)

    def _export_pdf(self, note: Note, path: str):
        try:
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import mm

            doc = SimpleDocTemplate(path, pagesize=A4,
                                    leftMargin=20*mm, rightMargin=20*mm,
                                    topMargin=20*mm, bottomMargin=20*mm)
            styles = getSampleStyleSheet()
            story = [
                Paragraph(note.title, styles["Title"]),
                Spacer(1, 6*mm),
            ]
            for line in note.content.split("\n"):
                if line.strip():
                    story.append(Paragraph(line, styles["Normal"]))
                    story.append(Spacer(1, 2*mm))
            doc.build(story)
        except ImportError:
            logger.error("reportlab not installed — PDF export unavailable")
            raise

    # ── HISTORY / UNDO ───────────────────────────────────

    def _snapshot(self, conn, entity_type: str, entity_id: int,
                  action: str, data: dict):
        conn.execute(
            """INSERT INTO history (entity_type, entity_id, action, snapshot)
               VALUES (?, ?, ?, ?)""",
            (entity_type, entity_id, action, json.dumps(data))
        )

    def get_trash(self) -> list[Note]:
        rows = db.fetchall(
            """SELECT n.*, f.name AS folder_name FROM notes n
               LEFT JOIN folders f ON n.folder_id = f.id
               WHERE n.is_deleted = 1 ORDER BY n.deleted_at DESC"""
        )
        return [_row_to_note(r) for r in rows]


note_service = NoteService()
