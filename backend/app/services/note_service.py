"""
services/note_service.py
────────────────────────
Async note business logic — CRUD, FTS search, export.
All methods scoped to user_id for multi-tenancy.
"""

from __future__ import annotations
import re
import math
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, text, update, delete
from sqlalchemy.orm import selectinload

from app.models.orm import Note, Folder, Tag, NoteTag, NoteAttachment
from app.schemas.schemas import NoteCreate, NoteUpdate, NoteOut, NoteSummary
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _word_count(content: str) -> tuple[int, int]:
    clean = re.sub(r"[#*_`\[\]()>~]", "", content)
    words = len(clean.split()) if clean.strip() else 0
    return words, len(clean)


def _render_html(content: str) -> str:
    """Convert markdown to HTML for caching."""
    try:
        import markdown2
        return markdown2.markdown(
            content,
            extras=["fenced-code-blocks", "tables", "task_list", "strike"],
        )
    except Exception:
        return content


class NoteService:

    # ── Create ────────────────────────────────────────────────────

    async def create(
        self, db: AsyncSession, user_id: str, data: NoteCreate
    ) -> Note:
        wc, cc = _word_count(data.content)
        note = Note(
            user_id=user_id,
            title=data.title,
            content=data.content,
            content_html=_render_html(data.content),
            folder_id=data.folder_id,
            color_label=data.color_label,
            is_pinned=data.is_pinned,
            word_count=wc,
            char_count=cc,
        )
        db.add(note)
        await db.flush()

        # Handle tags
        if data.tags:
            await self._sync_tags(db, note, user_id, data.tags)

        await db.refresh(note)
        return note

    # ── Read ──────────────────────────────────────────────────────

    async def get_by_id(
        self, db: AsyncSession, note_id: str, user_id: str
    ) -> Optional[Note]:
        result = await db.execute(
            select(Note)
            .options(
                selectinload(Note.tags),
                selectinload(Note.attachments),
                selectinload(Note.folder),
            )
            .where(Note.id == note_id, Note.user_id == user_id, Note.is_deleted == False)
        )
        return result.scalar_one_or_none()

    async def list_notes(
        self,
        db: AsyncSession,
        user_id: str,
        folder_id: Optional[str] = None,
        tag_id: Optional[str] = None,
        archived: bool = False,
        pinned_first: bool = True,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Note], int]:
        conditions = [
            Note.user_id == user_id,
            Note.is_deleted == False,
            Note.is_archived == archived,
        ]
        if folder_id:
            conditions.append(Note.folder_id == folder_id)

        q = select(Note).options(selectinload(Note.tags)).where(and_(*conditions))

        if tag_id:
            q = q.join(NoteTag, NoteTag.note_id == Note.id).where(NoteTag.tag_id == tag_id)

        order = []
        if pinned_first:
            order.append(Note.is_pinned.desc())
        order.append(Note.updated_at.desc())
        q = q.order_by(*order)

        total_q = select(func.count()).select_from(q.subquery())
        total = (await db.execute(total_q)).scalar_one()

        q = q.offset(offset).limit(limit)
        result = await db.execute(q)
        notes = list(result.scalars().all())
        return notes, total

    async def search(
        self,
        db: AsyncSession,
        user_id: str,
        query: str,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Note], int]:
        """PostgreSQL full-text search with ts_rank ranking."""
        if not query.strip():
            return await self.list_notes(db, user_id, offset=offset, limit=limit)

        ts_query = func.plainto_tsquery("english", query)
        conditions = [
            Note.user_id == user_id,
            Note.is_deleted == False,
            Note.search_vector.op("@@")(ts_query),
        ]

        q = (
            select(Note)
            .options(selectinload(Note.tags))
            .where(and_(*conditions))
            .order_by(
                func.ts_rank(Note.search_vector, ts_query).desc(),
                Note.updated_at.desc(),
            )
        )
        total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        result = await db.execute(q.offset(offset).limit(limit))
        return list(result.scalars()), total

    async def get_trash(
        self, db: AsyncSession, user_id: str
    ) -> list[Note]:
        result = await db.execute(
            select(Note)
            .where(Note.user_id == user_id, Note.is_deleted == True)
            .order_by(Note.deleted_at.desc())
        )
        return list(result.scalars())

    # ── Update ────────────────────────────────────────────────────

    async def update(
        self, db: AsyncSession, note: Note, data: NoteUpdate
    ) -> Note:
        update_data = data.model_dump(exclude_unset=True)

        if "content" in update_data:
            wc, cc = _word_count(update_data["content"])
            update_data["word_count"] = wc
            update_data["char_count"] = cc
            update_data["content_html"] = _render_html(update_data["content"])

        for k, v in update_data.items():
            setattr(note, k, v)

        await db.flush()
        await db.refresh(note, attribute_names=["tags", "attachments"])
        return note

    async def pin(self, db: AsyncSession, note: Note, pinned: bool) -> Note:
        note.is_pinned = pinned
        await db.flush()
        return note

    async def archive(self, db: AsyncSession, note: Note, archived: bool) -> Note:
        note.is_archived = archived
        await db.flush()
        return note

    # ── Delete ────────────────────────────────────────────────────

    async def soft_delete(self, db: AsyncSession, note: Note):
        note.is_deleted = True
        note.deleted_at = datetime.utcnow()
        await db.flush()

    async def restore(self, db: AsyncSession, note: Note):
        note.is_deleted = False
        note.deleted_at = None
        await db.flush()

    async def hard_delete(self, db: AsyncSession, note: Note) -> list[str]:
        """Permanently delete. Returns list of S3 keys to clean up."""
        s3_keys = [a.s3_key for a in note.attachments]
        await db.delete(note)
        await db.flush()
        return s3_keys

    async def empty_trash(self, db: AsyncSession, user_id: str) -> list[str]:
        result = await db.execute(
            select(Note)
            .options(selectinload(Note.attachments))
            .where(Note.user_id == user_id, Note.is_deleted == True)
        )
        notes = list(result.scalars())
        s3_keys = []
        for note in notes:
            s3_keys.extend(a.s3_key for a in note.attachments)
            await db.delete(note)
        await db.flush()
        return s3_keys

    # ── Tags ──────────────────────────────────────────────────────

    async def _sync_tags(
        self, db: AsyncSession, note: Note, user_id: str, tag_names: list[str]
    ):
        tags = []
        for name in tag_names:
            name = name.strip().lower()
            if not name:
                continue
            result = await db.execute(
                select(Tag).where(Tag.user_id == user_id, Tag.name == name)
            )
            tag = result.scalar_one_or_none()
            if not tag:
                tag = Tag(user_id=user_id, name=name)
                db.add(tag)
                await db.flush()
            tags.append(tag)
        note.tags = tags

    async def add_tag(
        self, db: AsyncSession, note: Note, user_id: str, tag_name: str
    ) -> Tag:
        result = await db.execute(
            select(Tag).where(Tag.user_id == user_id, Tag.name == tag_name.lower())
        )
        tag = result.scalar_one_or_none()
        if not tag:
            tag = Tag(user_id=user_id, name=tag_name.lower())
            db.add(tag)
            await db.flush()
        if tag not in note.tags:
            note.tags.append(tag)
            await db.flush()
        return tag

    async def remove_tag(self, db: AsyncSession, note: Note, tag_id: str):
        note.tags = [t for t in note.tags if t.id != tag_id]
        await db.flush()

    # ── Export helpers ────────────────────────────────────────────

    def render_txt(self, note: Note) -> bytes:
        lines = [note.title, "=" * len(note.title), "", note.content]
        return "\n".join(lines).encode("utf-8")

    def render_md(self, note: Note) -> bytes:
        tags_str = " ".join(f"#{t.name}" for t in note.tags)
        parts = [f"# {note.title}", ""]
        if tags_str:
            parts += [tags_str, ""]
        parts.append(note.content)
        return "\n".join(parts).encode("utf-8")

    def render_pdf(self, note: Note) -> bytes:
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        import io

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                leftMargin=20*mm, rightMargin=20*mm,
                                topMargin=20*mm, bottomMargin=20*mm)
        styles = getSampleStyleSheet()
        story = [Paragraph(note.title, styles["Title"]), Spacer(1, 6*mm)]
        for line in note.content.split("\n"):
            if line.strip():
                story.append(Paragraph(line, styles["Normal"]))
                story.append(Spacer(1, 2*mm))
        doc.build(story)
        return buffer.getvalue()


note_service = NoteService()
