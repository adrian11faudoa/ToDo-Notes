"""
api/routes/pomodoro.py
──────────────────────
Pomodoro session endpoints — create, complete, list, stats.
Sessions are linked optionally to a task for focus tracking.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func

from app.core.deps import CurrentUser, DBSession
from app.models.orm import PomodoroSession, Task
from app.schemas.schemas import PomodoroCreate, PomodoroComplete, PomodoroOut

router = APIRouter(prefix="/pomodoro", tags=["pomodoro"])


@router.get("", response_model=list[PomodoroOut])
async def list_sessions(
    db: DBSession,
    current_user: CurrentUser,
    limit: int = Query(default=20, le=100),
    session_type: Optional[str] = Query(None),
):
    """List recent pomodoro sessions for the current user."""
    conditions = [PomodoroSession.user_id == current_user.id]
    if session_type:
        conditions.append(PomodoroSession.session_type == session_type)

    from sqlalchemy import and_
    result = await db.execute(
        select(PomodoroSession)
        .where(and_(*conditions))
        .order_by(PomodoroSession.started_at.desc())
        .limit(limit)
    )
    return [PomodoroOut.model_validate(s) for s in result.scalars()]


@router.post("", response_model=PomodoroOut, status_code=201)
async def start_session(
    data: PomodoroCreate,
    db: DBSession,
    current_user: CurrentUser,
):
    """Start a new pomodoro session."""
    # Validate task belongs to user if provided
    if data.task_id:
        task = await db.execute(
            select(Task).where(
                Task.id == data.task_id,
                Task.user_id == current_user.id,
            )
        )
        if not task.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Task not found")

    session = PomodoroSession(
        user_id=current_user.id,
        task_id=data.task_id,
        duration=data.duration,
        session_type=data.session_type,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return PomodoroOut.model_validate(session)


@router.post("/{session_id}/complete", response_model=PomodoroOut)
async def complete_session(
    session_id: str,
    data: PomodoroComplete,
    db: DBSession,
    current_user: CurrentUser,
):
    """Mark a pomodoro session as completed."""
    result = await db.execute(
        select(PomodoroSession).where(
            PomodoroSession.id == session_id,
            PomodoroSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.completed = True
    session.ended_at = data.ended_at or datetime.now(timezone.utc)
    await db.flush()
    return PomodoroOut.model_validate(session)


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    db: DBSession,
    current_user: CurrentUser,
):
    """Delete a pomodoro session."""
    result = await db.execute(
        select(PomodoroSession).where(
            PomodoroSession.id == session_id,
            PomodoroSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(session)


@router.get("/summary", response_model=dict)
async def get_summary(
    db: DBSession,
    current_user: CurrentUser,
):
    """Aggregate focus statistics for the current user."""
    uid = current_user.id

    total_sessions = (await db.execute(
        select(func.count(PomodoroSession.id)).where(
            PomodoroSession.user_id == uid,
            PomodoroSession.completed == True,
            PomodoroSession.session_type == "work",
        )
    )).scalar_one()

    total_seconds = (await db.execute(
        select(func.coalesce(func.sum(PomodoroSession.duration), 0)).where(
            PomodoroSession.user_id == uid,
            PomodoroSession.completed == True,
            PomodoroSession.session_type == "work",
        )
    )).scalar_one()

    today = datetime.now(timezone.utc).date()
    today_sessions = (await db.execute(
        select(func.count(PomodoroSession.id)).where(
            PomodoroSession.user_id == uid,
            PomodoroSession.completed == True,
            PomodoroSession.session_type == "work",
            func.date(PomodoroSession.started_at) == today,
        )
    )).scalar_one()

    today_seconds = (await db.execute(
        select(func.coalesce(func.sum(PomodoroSession.duration), 0)).where(
            PomodoroSession.user_id == uid,
            PomodoroSession.completed == True,
            PomodoroSession.session_type == "work",
            func.date(PomodoroSession.started_at) == today,
        )
    )).scalar_one()

    return {
        "total_sessions":       total_sessions,
        "total_focus_minutes":  total_seconds // 60,
        "today_sessions":       today_sessions,
        "today_focus_minutes":  today_seconds // 60,
    }
