"""
api/routes/tasks.py
───────────────────
Task management endpoints: CRUD, subtasks, kanban, recurrence.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser, DBSession, PaginationDep
from app.models.orm import Task, Project, Tag, TaskTag
from app.schemas.schemas import (
    TaskCreate, TaskUpdate, TaskOut, TaskListResponse, Page,
    ProjectCreate, ProjectUpdate, ProjectOut,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────

async def _get_task_or_404(db: DBSession, task_id: str, user_id: str) -> Task:
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.tags), selectinload(Task.subtasks))
        .where(Task.id == task_id, Task.user_id == user_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


async def _get_or_create_tag(db: DBSession, user_id: str, name: str) -> Tag:
    name = name.strip().lower()
    result = await db.execute(select(Tag).where(Tag.user_id == user_id, Tag.name == name))
    tag = result.scalar_one_or_none()
    if not tag:
        tag = Tag(user_id=user_id, name=name)
        db.add(tag)
        await db.flush()
    return tag


def _next_recurrence(due_date: datetime, rule: str) -> Optional[datetime]:
    from datetime import timedelta
    rule = rule.lower()
    if rule == "daily":
        return due_date + timedelta(days=1)
    if rule == "weekly":
        return due_date + timedelta(weeks=1)
    if rule == "monthly":
        m = due_date.month + 1 if due_date.month < 12 else 1
        y = due_date.year if due_date.month < 12 else due_date.year + 1
        try:
            return due_date.replace(year=y, month=m)
        except ValueError:
            return None
    if rule == "yearly":
        try:
            return due_date.replace(year=due_date.year + 1)
        except ValueError:
            return None
    return None


# ─────────────────────────────────────────────────────────────────
# TASK CRUD
# ─────────────────────────────────────────────────────────────────

@router.get("", response_model=TaskListResponse)
async def list_tasks(
    db: DBSession,
    current_user: CurrentUser,
    pagination: PaginationDep,
    project_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[int] = Query(None),
    due_today: bool = Query(False),
    overdue: bool = Query(False),
    include_subtasks: bool = Query(False),
):
    conditions = [Task.user_id == current_user.id]
    if not include_subtasks:
        conditions.append(Task.parent_id.is_(None))
    if project_id:
        conditions.append(Task.project_id == project_id)
    if status:
        conditions.append(Task.status == status)
    if priority:
        conditions.append(Task.priority == priority)
    if due_today:
        today = datetime.now(timezone.utc).date()
        conditions.append(func.date(Task.due_date) == today)
    if overdue:
        conditions.append(
            Task.due_date < datetime.now(timezone.utc),
            Task.status.notin_(["done", "cancelled"]),
        )

    q = (
        select(Task)
        .options(selectinload(Task.tags), selectinload(Task.subtasks))
        .where(and_(*conditions))
        .order_by(Task.is_pinned.desc(), Task.priority.asc(), Task.sort_order.asc())
    )
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    result = await db.execute(q.offset(pagination.offset).limit(pagination.size))
    tasks = list(result.scalars())

    return TaskListResponse(
        items=[TaskOut.model_validate(t) for t in tasks],
        pagination=Page(
            page=pagination.page, size=pagination.size,
            total=total, pages=max(1, -(-total // pagination.size)),
        ),
    )


@router.get("/kanban", response_model=dict)
async def get_kanban(
    db: DBSession,
    current_user: CurrentUser,
    project_id: Optional[str] = Query(None),
):
    """Return tasks grouped by kanban_column."""
    conditions = [Task.user_id == current_user.id, Task.parent_id.is_(None)]
    if project_id:
        conditions.append(Task.project_id == project_id)

    result = await db.execute(
        select(Task)
        .options(selectinload(Task.tags), selectinload(Task.subtasks))
        .where(and_(*conditions))
        .order_by(Task.sort_order.asc())
    )
    tasks = list(result.scalars())
    columns: dict[str, list] = {
        "todo": [], "in_progress": [], "done": [], "cancelled": []
    }
    for t in tasks:
        col = t.kanban_column or "todo"
        columns.setdefault(col, []).append(TaskOut.model_validate(t))
    return columns


@router.get("/today", response_model=list[TaskOut])
async def get_today_tasks(db: DBSession, current_user: CurrentUser):
    today = datetime.now(timezone.utc).date()
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.tags), selectinload(Task.subtasks))
        .where(
            Task.user_id == current_user.id,
            func.date(Task.due_date) == today,
            Task.status.notin_(["done", "cancelled"]),
        )
        .order_by(Task.priority.asc(), Task.due_date.asc())
    )
    return [TaskOut.model_validate(t) for t in result.scalars()]


@router.get("/overdue", response_model=list[TaskOut])
async def get_overdue_tasks(db: DBSession, current_user: CurrentUser):
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.tags), selectinload(Task.subtasks))
        .where(
            Task.user_id == current_user.id,
            Task.due_date < datetime.now(timezone.utc),
            Task.status.notin_(["done", "cancelled"]),
        )
        .order_by(Task.due_date.asc())
    )
    return [TaskOut.model_validate(t) for t in result.scalars()]


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(data: TaskCreate, db: DBSession, current_user: CurrentUser):
    task = Task(
        user_id=current_user.id,
        title=data.title,
        description=data.description,
        project_id=data.project_id,
        parent_id=data.parent_id,
        priority=data.priority,
        due_date=data.due_date,
        due_time=data.due_time,
        reminder_at=data.reminder_at,
        recurrence_rule=data.recurrence_rule,
    )
    db.add(task)
    await db.flush()

    if data.tags:
        for name in data.tags:
            tag = await _get_or_create_tag(db, current_user.id, name)
            task.tags.append(tag)
        await db.flush()

    await db.refresh(task, attribute_names=["tags", "subtasks"])
    return TaskOut.model_validate(task)


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: str, db: DBSession, current_user: CurrentUser):
    return TaskOut.model_validate(await _get_task_or_404(db, task_id, current_user.id))


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: str, data: TaskUpdate, db: DBSession, current_user: CurrentUser
):
    task = await _get_task_or_404(db, task_id, current_user.id)
    update_data = data.model_dump(exclude_unset=True)

    if update_data.get("status") == "done" and not task.completed_at:
        update_data["completed_at"] = datetime.now(timezone.utc)
    elif "status" in update_data and update_data["status"] != "done":
        update_data["completed_at"] = None

    for k, v in update_data.items():
        setattr(task, k, v)
    await db.flush()
    await db.refresh(task, attribute_names=["tags", "subtasks"])
    return TaskOut.model_validate(task)


@router.post("/{task_id}/complete", response_model=TaskOut)
async def complete_task(task_id: str, db: DBSession, current_user: CurrentUser):
    """Mark done + spawn next recurrence if applicable."""
    task = await _get_task_or_404(db, task_id, current_user.id)
    task.status = "done"
    task.completed_at = datetime.now(timezone.utc)
    await db.flush()

    # Spawn next recurrence
    if task.recurrence_rule and task.due_date:
        next_due = _next_recurrence(task.due_date, task.recurrence_rule)
        if next_due:
            new_task = Task(
                user_id=current_user.id,
                title=task.title,
                description=task.description,
                project_id=task.project_id,
                priority=task.priority,
                due_date=next_due,
                recurrence_rule=task.recurrence_rule,
            )
            db.add(new_task)
            await db.flush()

    await db.refresh(task, attribute_names=["tags", "subtasks"])
    return TaskOut.model_validate(task)


@router.post("/{task_id}/move", response_model=TaskOut)
async def move_kanban(
    task_id: str, column: str, db: DBSession, current_user: CurrentUser
):
    """Move a task to a different Kanban column."""
    valid = {"todo", "in_progress", "done", "cancelled"}
    if column not in valid:
        raise HTTPException(status_code=400, detail=f"Column must be one of {valid}")
    task = await _get_task_or_404(db, task_id, current_user.id)
    task.kanban_column = column
    status_map = {"todo": "todo", "in_progress": "in_progress",
                  "done": "done", "cancelled": "cancelled"}
    task.status = status_map[column]
    if column == "done":
        task.completed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(task, attribute_names=["tags", "subtasks"])
    return TaskOut.model_validate(task)


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str, db: DBSession, current_user: CurrentUser):
    task = await _get_task_or_404(db, task_id, current_user.id)
    await db.delete(task)


# ─────────────────────────────────────────────────────────────────
# PROJECTS
# ─────────────────────────────────────────────────────────────────

projects_router = APIRouter(prefix="/projects", tags=["projects"])


@projects_router.get("", response_model=list[ProjectOut])
async def list_projects(db: DBSession, current_user: CurrentUser):
    result = await db.execute(
        select(Project)
        .where(Project.user_id == current_user.id, Project.is_archived == False)
        .order_by(Project.sort_order.asc(), Project.name.asc())
    )
    projects = list(result.scalars())
    out = []
    for p in projects:
        task_count = (await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == p.id, Task.parent_id.is_(None)
            )
        )).scalar_one()
        done_count = (await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == p.id, Task.status == "done", Task.parent_id.is_(None)
            )
        )).scalar_one()
        po = ProjectOut.model_validate(p)
        po.task_count = task_count
        po.completed_count = done_count
        out.append(po)
    return out


@projects_router.post("", response_model=ProjectOut, status_code=201)
async def create_project(data: ProjectCreate, db: DBSession, current_user: CurrentUser):
    project = Project(user_id=current_user.id, **data.model_dump())
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return ProjectOut.model_validate(project)


@projects_router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: str, data: ProjectUpdate, db: DBSession, current_user: CurrentUser
):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(project, k, v)
    await db.flush()
    return ProjectOut.model_validate(project)


@projects_router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, db: DBSession, current_user: CurrentUser):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    # Unlink tasks first
    await db.execute(
        __import__("sqlalchemy", fromlist=["update"]).update(Task)
        .where(Task.project_id == project_id)
        .values(project_id=None)
    )
    await db.delete(project)
