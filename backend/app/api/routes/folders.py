"""
api/routes/folders.py
─────────────────────
Folder, Tag, Search, Stats, Health endpoints.
"""

from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func, or_, text
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser, DBSession
from app.models.orm import Folder, Tag, Note, Task, NoteTag
from app.schemas.schemas import (
    FolderCreate, FolderUpdate, FolderOut,
    TagCreate, TagOut,
    SearchResult, NoteSummary, TaskOut,
    UserStats, HealthResponse,
)
from app.core.config import get_settings

settings = get_settings()

# ─────────────────────────────────────────────────────────────────
# FOLDERS
# ─────────────────────────────────────────────────────────────────

folders_router = APIRouter(prefix="/folders", tags=["folders"])


@folders_router.get("", response_model=list[FolderOut])
async def list_folders(db: DBSession, current_user: CurrentUser):
    result = await db.execute(
        select(Folder)
        .where(Folder.user_id == current_user.id)
        .order_by(Folder.sort_order.asc(), Folder.name.asc())
    )
    folders = list(result.scalars())
    out = []
    for f in folders:
        count = (await db.execute(
            select(func.count(Note.id)).where(
                Note.folder_id == f.id, Note.is_deleted == False
            )
        )).scalar_one()
        fo = FolderOut.model_validate(f)
        fo.note_count = count
        out.append(fo)
    return out


@folders_router.post("", response_model=FolderOut, status_code=201)
async def create_folder(data: FolderCreate, db: DBSession, current_user: CurrentUser):
    folder = Folder(user_id=current_user.id, **data.model_dump())
    db.add(folder)
    await db.flush()
    await db.refresh(folder)
    fo = FolderOut.model_validate(folder)
    fo.note_count = 0
    return fo


@folders_router.patch("/{folder_id}", response_model=FolderOut)
async def update_folder(
    folder_id: str, data: FolderUpdate, db: DBSession, current_user: CurrentUser
):
    result = await db.execute(
        select(Folder).where(Folder.id == folder_id, Folder.user_id == current_user.id)
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(folder, k, v)
    await db.flush()
    return FolderOut.model_validate(folder)


@folders_router.delete("/{folder_id}", status_code=204)
async def delete_folder(folder_id: str, db: DBSession, current_user: CurrentUser):
    result = await db.execute(
        select(Folder).where(Folder.id == folder_id, Folder.user_id == current_user.id)
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    # Move notes out of folder before deleting
    await db.execute(
        __import__("sqlalchemy", fromlist=["update"]).update(Note)
        .where(Note.folder_id == folder_id)
        .values(folder_id=None)
    )
    await db.delete(folder)


# ─────────────────────────────────────────────────────────────────
# TAGS
# ─────────────────────────────────────────────────────────────────

tags_router = APIRouter(prefix="/tags", tags=["tags"])


@tags_router.get("", response_model=list[TagOut])
async def list_tags(db: DBSession, current_user: CurrentUser):
    result = await db.execute(
        select(Tag)
        .where(Tag.user_id == current_user.id)
        .order_by(Tag.name.asc())
    )
    return [TagOut.model_validate(t) for t in result.scalars()]


@tags_router.post("", response_model=TagOut, status_code=201)
async def create_tag(data: TagCreate, db: DBSession, current_user: CurrentUser):
    existing = await db.execute(
        select(Tag).where(Tag.user_id == current_user.id, Tag.name == data.name.lower())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Tag already exists")
    tag = Tag(user_id=current_user.id, name=data.name.lower(), color=data.color)
    db.add(tag)
    await db.flush()
    await db.refresh(tag)
    return TagOut.model_validate(tag)


@tags_router.delete("/{tag_id}", status_code=204)
async def delete_tag(tag_id: str, db: DBSession, current_user: CurrentUser):
    result = await db.execute(
        select(Tag).where(Tag.id == tag_id, Tag.user_id == current_user.id)
    )
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    await db.delete(tag)


# ─────────────────────────────────────────────────────────────────
# GLOBAL SEARCH
# ─────────────────────────────────────────────────────────────────

search_router = APIRouter(prefix="/search", tags=["search"])


@search_router.get("", response_model=SearchResult)
async def global_search(
    q: str,
    db: DBSession,
    current_user: CurrentUser,
    limit: int = Query(default=10, le=50),
):
    """Full-text search across both notes and tasks."""
    if not q.strip():
        return SearchResult()

    ts_query = func.plainto_tsquery("english", q)

    # Notes FTS
    notes_result = await db.execute(
        select(Note)
        .options(selectinload(Note.tags))
        .where(
            Note.user_id == current_user.id,
            Note.is_deleted == False,
            Note.search_vector.op("@@")(ts_query),
        )
        .order_by(func.ts_rank(Note.search_vector, ts_query).desc())
        .limit(limit)
    )
    notes = list(notes_result.scalars())

    # Tasks FTS
    tasks_result = await db.execute(
        select(Task)
        .options(selectinload(Task.tags), selectinload(Task.subtasks))
        .where(
            Task.user_id == current_user.id,
            Task.search_vector.op("@@")(ts_query),
        )
        .order_by(func.ts_rank(Task.search_vector, ts_query).desc())
        .limit(limit)
    )
    tasks = list(tasks_result.scalars())

    return SearchResult(
        notes=[NoteSummary.model_validate(n) for n in notes],
        tasks=[TaskOut.model_validate(t) for t in tasks],
        total_notes=len(notes),
        total_tasks=len(tasks),
    )


# ─────────────────────────────────────────────────────────────────
# STATS
# ─────────────────────────────────────────────────────────────────

stats_router = APIRouter(prefix="/stats", tags=["stats"])


@stats_router.get("", response_model=UserStats)
async def get_user_stats(db: DBSession, current_user: CurrentUser):
    from datetime import timezone
    from app.models.orm import PomodoroSession

    uid = current_user.id

    total_notes = (await db.execute(
        select(func.count(Note.id)).where(Note.user_id == uid, Note.is_deleted == False)
    )).scalar_one()

    total_tasks = (await db.execute(
        select(func.count(Task.id)).where(Task.user_id == uid, Task.parent_id.is_(None))
    )).scalar_one()

    completed_tasks = (await db.execute(
        select(func.count(Task.id)).where(
            Task.user_id == uid, Task.status == "done", Task.parent_id.is_(None)
        )
    )).scalar_one()

    from datetime import datetime
    overdue_tasks = (await db.execute(
        select(func.count(Task.id)).where(
            Task.user_id == uid,
            Task.due_date < datetime.now(timezone.utc),
            Task.status.notin_(["done", "cancelled"]),
        )
    )).scalar_one()

    today = datetime.now(timezone.utc).date()
    today_tasks = (await db.execute(
        select(func.count(Task.id)).where(
            Task.user_id == uid,
            func.date(Task.due_date) == today,
            Task.status.notin_(["done", "cancelled"]),
        )
    )).scalar_one()

    total_pomodoros = (await db.execute(
        select(func.count(PomodoroSession.id)).where(
            PomodoroSession.user_id == uid, PomodoroSession.completed == True
        )
    )).scalar_one()

    focus_seconds = (await db.execute(
        select(func.coalesce(func.sum(PomodoroSession.duration), 0)).where(
            PomodoroSession.user_id == uid,
            PomodoroSession.completed == True,
            PomodoroSession.session_type == "work",
        )
    )).scalar_one()

    return UserStats(
        total_notes=total_notes,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        overdue_tasks=overdue_tasks,
        today_tasks=today_tasks,
        completion_rate=round(completed_tasks / total_tasks * 100, 1) if total_tasks else 0.0,
        total_pomodoros=total_pomodoros,
        total_focus_minutes=focus_seconds // 60,
    )


# ─────────────────────────────────────────────────────────────────
# HEALTH
# ─────────────────────────────────────────────────────────────────

health_router = APIRouter(tags=["health"])


@health_router.get("/health", response_model=HealthResponse)
async def health_check(db: DBSession):
    """ECS/ALB health check endpoint. Returns 200 only when all deps are up."""
    from app.db.session import check_db_connection
    from app.services.s3_service import s3_service

    db_ok = await check_db_connection()

    # Redis check
    redis_ok = False
    try:
        from app.services.cache_service import cache_service
        redis_ok = await cache_service.ping()
    except Exception:
        pass

    s3_ok = s3_service.health_check()

    all_ok = db_ok and redis_ok and s3_ok
    status_code = 200 if all_ok else 503

    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status_code,
        content=HealthResponse(
            status="healthy" if all_ok else "degraded",
            version=settings.APP_VERSION,
            environment=settings.ENVIRONMENT,
            db=db_ok,
            redis=redis_ok,
            s3=s3_ok,
        ).model_dump(),
    )


@health_router.get("/ready")
async def readiness():
    """Kubernetes/ECS readiness probe — lightweight, no DB call."""
    return {"status": "ready"}
