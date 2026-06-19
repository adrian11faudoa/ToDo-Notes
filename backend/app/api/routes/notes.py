"""
api/routes/notes.py
───────────────────
Notes CRUD + tags, attachments, export endpoints.
All routes are user-scoped via CurrentUser dependency.
"""

from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from sqlalchemy import select, func

from app.core.deps import CurrentUser, DBSession, PaginationDep
from app.models.orm import Folder
from app.schemas.schemas import (
    NoteCreate, NoteUpdate, NoteOut, NoteSummary,
    NoteListResponse, Page, PresignedUploadResponse,
    TagOut,
)
from app.services.note_service import note_service
from app.services.s3_service import s3_service

router = APIRouter(prefix="/notes", tags=["notes"])


# ── List / Search ─────────────────────────────────────────────────

@router.get("", response_model=NoteListResponse)
async def list_notes(
    db: DBSession,
    current_user: CurrentUser,
    pagination: PaginationDep,
    folder_id: Optional[str] = Query(None),
    tag_id: Optional[str] = Query(None),
    archived: bool = Query(False),
    pinned_first: bool = Query(True),
):
    notes, total = await note_service.list_notes(
        db, current_user.id,
        folder_id=folder_id,
        tag_id=tag_id,
        archived=archived,
        pinned_first=pinned_first,
        offset=pagination.offset,
        limit=pagination.size,
    )
    pages = max(1, -(-total // pagination.size))  # ceil division
    return NoteListResponse(
        items=[NoteSummary.model_validate(n) for n in notes],
        pagination=Page(
            page=pagination.page, size=pagination.size,
            total=total, pages=pages,
        ),
    )


@router.get("/search", response_model=NoteListResponse)
async def search_notes(
    q: str,
    db: DBSession,
    current_user: CurrentUser,
    pagination: PaginationDep,
):
    notes, total = await note_service.search(
        db, current_user.id, q,
        offset=pagination.offset,
        limit=pagination.size,
    )
    return NoteListResponse(
        items=[NoteSummary.model_validate(n) for n in notes],
        pagination=Page(
            page=pagination.page, size=pagination.size,
            total=total, pages=max(1, -(-total // pagination.size)),
        ),
    )


@router.get("/trash", response_model=list[NoteSummary])
async def get_trash(db: DBSession, current_user: CurrentUser):
    notes = await note_service.get_trash(db, current_user.id)
    return [NoteSummary.model_validate(n) for n in notes]


# ── CRUD ──────────────────────────────────────────────────────────

@router.post("", response_model=NoteOut, status_code=201)
async def create_note(
    data: NoteCreate, db: DBSession, current_user: CurrentUser
):
    if data.folder_id:
        folder = await db.get(Folder, data.folder_id)
        if not folder or folder.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Folder not found")
    note = await note_service.create(db, current_user.id, data)
    return NoteOut.model_validate(note)


@router.get("/{note_id}", response_model=NoteOut)
async def get_note(note_id: str, db: DBSession, current_user: CurrentUser):
    note = await note_service.get_by_id(db, note_id, current_user.id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    # Enrich attachments with presigned download URLs
    out = NoteOut.model_validate(note)
    for att in out.attachments:
        att.presigned_url = s3_service.create_presigned_download(att.s3_key, att.filename)
    return out


@router.patch("/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: str, data: NoteUpdate, db: DBSession, current_user: CurrentUser
):
    note = await note_service.get_by_id(db, note_id, current_user.id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    note = await note_service.update(db, note, data)
    return NoteOut.model_validate(note)


@router.delete("/{note_id}", status_code=204)
async def delete_note(note_id: str, db: DBSession, current_user: CurrentUser,
                      permanent: bool = Query(False)):
    note = await note_service.get_by_id(db, note_id, current_user.id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if permanent:
        s3_keys = await note_service.hard_delete(db, note)
        s3_service.delete_attachments_batch(s3_keys)
    else:
        await note_service.soft_delete(db, note)


@router.post("/{note_id}/restore", response_model=NoteOut)
async def restore_note(note_id: str, db: DBSession, current_user: CurrentUser):
    result = await db.execute(
        __import__("sqlalchemy", fromlist=["select"]).select(
            __import__("app.models.orm", fromlist=["Note"]).Note
        ).where(
            __import__("app.models.orm", fromlist=["Note"]).Note.id == note_id,
            __import__("app.models.orm", fromlist=["Note"]).Note.user_id == current_user.id,
        )
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    await note_service.restore(db, note)
    return NoteOut.model_validate(note)


@router.delete("/trash/empty", status_code=204)
async def empty_trash(db: DBSession, current_user: CurrentUser):
    s3_keys = await note_service.empty_trash(db, current_user.id)
    s3_service.delete_attachments_batch(s3_keys)


# ── Pin / Archive ─────────────────────────────────────────────────

@router.post("/{note_id}/pin", response_model=NoteOut)
async def pin_note(note_id: str, pinned: bool, db: DBSession, current_user: CurrentUser):
    note = await note_service.get_by_id(db, note_id, current_user.id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    await note_service.pin(db, note, pinned)
    return NoteOut.model_validate(note)


@router.post("/{note_id}/archive", response_model=NoteOut)
async def archive_note(note_id: str, archived: bool, db: DBSession, current_user: CurrentUser):
    note = await note_service.get_by_id(db, note_id, current_user.id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    await note_service.archive(db, note, archived)
    return NoteOut.model_validate(note)


# ── Tags ──────────────────────────────────────────────────────────

@router.post("/{note_id}/tags/{tag_name}", response_model=TagOut)
async def add_tag(note_id: str, tag_name: str, db: DBSession, current_user: CurrentUser):
    note = await note_service.get_by_id(db, note_id, current_user.id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    tag = await note_service.add_tag(db, note, current_user.id, tag_name)
    return TagOut.model_validate(tag)


@router.delete("/{note_id}/tags/{tag_id}", status_code=204)
async def remove_tag(note_id: str, tag_id: str, db: DBSession, current_user: CurrentUser):
    note = await note_service.get_by_id(db, note_id, current_user.id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    await note_service.remove_tag(db, note, tag_id)


# ── Attachments (S3 presigned upload) ────────────────────────────

@router.post("/{note_id}/attachments/presign", response_model=PresignedUploadResponse)
async def presign_attachment_upload(
    note_id: str,
    filename: str,
    content_type: Optional[str] = None,
    db: DBSession = None,
    current_user: CurrentUser = None,
):
    note = await note_service.get_by_id(db, note_id, current_user.id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    result = s3_service.create_presigned_upload(
        current_user.id, note_id, filename, content_type
    )
    # Record attachment in DB (confirmed when client finishes upload)
    from app.models.orm import NoteAttachment
    att = NoteAttachment(
        id=result["attachment_id"],
        note_id=note_id,
        filename=filename,
        s3_key=result["s3_key"],
        s3_bucket=s3_service._attachments_bucket,
        content_type=content_type or "application/octet-stream",
    )
    db.add(att)
    await db.flush()

    return PresignedUploadResponse(**result)


@router.delete("/{note_id}/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    note_id: str, attachment_id: str, db: DBSession, current_user: CurrentUser
):
    from sqlalchemy import select
    from app.models.orm import NoteAttachment, Note
    result = await db.execute(
        select(NoteAttachment)
        .join(Note)
        .where(
            NoteAttachment.id == attachment_id,
            NoteAttachment.note_id == note_id,
            Note.user_id == current_user.id,
        )
    )
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")
    s3_service.delete_attachment(att.s3_key)
    await db.delete(att)


# ── Export ────────────────────────────────────────────────────────

@router.get("/{note_id}/export/{format}")
async def export_note(
    note_id: str, format: str, db: DBSession, current_user: CurrentUser
):
    if format not in ("txt", "md", "pdf"):
        raise HTTPException(status_code=400, detail="Format must be txt, md, or pdf")

    note = await note_service.get_by_id(db, note_id, current_user.id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    renderers = {
        "txt": note_service.render_txt,
        "md":  note_service.render_md,
        "pdf": note_service.render_pdf,
    }
    content = renderers[format](note)
    download_url = s3_service.upload_export(
        current_user.id, note_id, content, format, note.title
    )
    return {"download_url": download_url, "expires_in": 3600}
