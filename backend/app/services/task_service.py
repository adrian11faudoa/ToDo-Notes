"""
services/task_service.py
────────────────────────
Async task business logic — CRUD, subtasks, recurrence, kanban.
All methods scoped to user_id for multi-tenancy.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from app.models.orm import Task, Project, Tag, TaskTag
from app.schemas.schemas import TaskCreate, TaskUpdate

logger = logging.getLogger(__name__)


def _next_recurrence(due_date: datetime, rule: str) -> Optional[datetime]:
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


class TaskService:

    # ── Helpers ───────────────────────────────────────────────────

    async def _get_or_create_tag(
        self, db: AsyncSession, user_id: str, name: str
    ) -> Tag:
        name = name.strip().lower()
        result = await db.execute(
            select(Tag).where(Tag.user_id == user_id, Tag.name == name)
        )
        tag = result.scalar_one_or_none()
        if not tag:
            tag = Tag(user_id=user_id, name=name)
            db.add(tag)
            await db.flush()
        return tag

    # ── Create ────────────────────────────────────────────────────

    async def create(
        self, db: AsyncSession, user_id: str, data: TaskCreate
    ) -> Task:
        task = Task(
            user_id=user_id,
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
                tag = await self._get_or_create_tag(db, user_id, name)
                task.tags.append(tag)
            await db.flush()

        await db.refresh(task, attribute_names=["tags", "subtasks"])
        return task

    # ── Read ──────────────────────────────────────────────────────

    async def get_by_id(
        self, db: AsyncSession, task_id: str, user_id: str
    ) -> Optional[Task]:
        result = await db.execute(
            select(Task)
            .options(selectinload(Task.tags), selectinload(Task.subtasks))
            .where(Task.id == task_id, Task.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        db: AsyncSession,
        user_id: str,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        include_subtasks: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Task], int]:
        conditions = [Task.user_id == user_id]
        if not include_subtasks:
            conditions.append(Task.parent_id.is_(None))
        if project_id:
            conditions.append(Task.project_id == project_id)
        if status:
            conditions.append(Task.status == status)

        q = (
            select(Task)
            .options(selectinload(Task.tags), selectinload(Task.subtasks))
            .where(and_(*conditions))
            .order_by(Task.is_pinned.desc(), Task.priority.asc(), Task.sort_order.asc())
        )
        total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        result = await db.execute(q.offset(offset).limit(limit))
        return list(result.scalars()), total

    async def get_today(self, db: AsyncSession, user_id: str) -> list[Task]:
        today = datetime.now(timezone.utc).date()
        result = await db.execute(
            select(Task)
            .options(selectinload(Task.tags), selectinload(Task.subtasks))
            .where(
                Task.user_id == user_id,
                func.date(Task.due_date) == today,
                Task.status.notin_(["done", "cancelled"]),
            )
            .order_by(Task.priority.asc(), Task.due_date.asc())
        )
        return list(result.scalars())

    async def get_overdue(self, db: AsyncSession, user_id: str) -> list[Task]:
        result = await db.execute(
            select(Task)
            .options(selectinload(Task.tags), selectinload(Task.subtasks))
            .where(
                Task.user_id == user_id,
                Task.due_date < datetime.now(timezone.utc),
                Task.status.notin_(["done", "cancelled"]),
            )
            .order_by(Task.due_date.asc())
        )
        return list(result.scalars())

    async def get_kanban(
        self, db: AsyncSession, user_id: str, project_id: Optional[str] = None
    ) -> dict[str, list[Task]]:
        conditions = [Task.user_id == user_id, Task.parent_id.is_(None)]
        if project_id:
            conditions.append(Task.project_id == project_id)
        result = await db.execute(
            select(Task)
            .options(selectinload(Task.tags), selectinload(Task.subtasks))
            .where(and_(*conditions))
            .order_by(Task.sort_order.asc())
        )
        columns: dict[str, list[Task]] = {
            "todo": [], "in_progress": [], "done": [], "cancelled": []
        }
        for t in result.scalars():
            columns.setdefault(t.kanban_column or "todo", []).append(t)
        return columns

    async def search(
        self, db: AsyncSession, user_id: str, query: str,
        offset: int = 0, limit: int = 50,
    ) -> tuple[list[Task], int]:
        if not query.strip():
            return await self.list_tasks(db, user_id, offset=offset, limit=limit)
        ts_query = func.plainto_tsquery("english", query)
        q = (
            select(Task)
            .options(selectinload(Task.tags), selectinload(Task.subtasks))
            .where(
                Task.user_id == user_id,
                Task.search_vector.op("@@")(ts_query),
            )
            .order_by(func.ts_rank(Task.search_vector, ts_query).desc())
        )
        total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        result = await db.execute(q.offset(offset).limit(limit))
        return list(result.scalars()), total

    # ── Update ────────────────────────────────────────────────────

    async def update(
        self, db: AsyncSession, task: Task, data: TaskUpdate
    ) -> Task:
        update_data = data.model_dump(exclude_unset=True)

        if update_data.get("status") == "done" and not task.completed_at:
            update_data["completed_at"] = datetime.now(timezone.utc)
        elif "status" in update_data and update_data["status"] != "done":
            update_data["completed_at"] = None

        for k, v in update_data.items():
            setattr(task, k, v)
        await db.flush()
        await db.refresh(task, attribute_names=["tags", "subtasks"])
        return task

    async def complete(
        self, db: AsyncSession, task: Task, user_id: str
    ) -> Task:
        """Mark done and spawn next recurrence if applicable."""
        task.status = "done"
        task.completed_at = datetime.now(timezone.utc)
        await db.flush()

        if task.recurrence_rule and task.due_date:
            next_due = _next_recurrence(task.due_date, task.recurrence_rule)
            if next_due:
                new_task = Task(
                    user_id=user_id,
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
        return task

    async def move_kanban(
        self, db: AsyncSession, task: Task, column: str
    ) -> Task:
        status_map = {
            "todo": "todo", "in_progress": "in_progress",
            "done": "done", "cancelled": "cancelled",
        }
        task.kanban_column = column
        task.status = status_map.get(column, "todo")
        if column == "done":
            task.completed_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(task, attribute_names=["tags", "subtasks"])
        return task

    # ── Delete ────────────────────────────────────────────────────

    async def delete(self, db: AsyncSession, task: Task):
        await db.delete(task)

    # ── Tags ──────────────────────────────────────────────────────

    async def add_tag(
        self, db: AsyncSession, task: Task, user_id: str, tag_name: str
    ) -> Tag:
        tag = await self._get_or_create_tag(db, user_id, tag_name)
        if tag not in task.tags:
            task.tags.append(tag)
            await db.flush()
        return tag

    async def remove_tag(self, db: AsyncSession, task: Task, tag_id: str):
        task.tags = [t for t in task.tags if t.id != tag_id]
        await db.flush()

    # ── Projects ──────────────────────────────────────────────────

    async def list_projects(
        self, db: AsyncSession, user_id: str
    ) -> list[Project]:
        result = await db.execute(
            select(Project)
            .where(Project.user_id == user_id, Project.is_archived == False)
            .order_by(Project.sort_order.asc(), Project.name.asc())
        )
        return list(result.scalars())

    async def create_project(
        self, db: AsyncSession, user_id: str, name: str,
        color: str = "#6C6C6C", description: str = ""
    ) -> Project:
        project = Project(
            user_id=user_id, name=name, color=color, description=description
        )
        db.add(project)
        await db.flush()
        await db.refresh(project)
        return project

    async def update_project(
        self, db: AsyncSession, project: Project, **kwargs
    ) -> Project:
        for k, v in kwargs.items():
            if hasattr(project, k):
                setattr(project, k, v)
        await db.flush()
        return project

    async def delete_project(self, db: AsyncSession, project: Project):
        # Unlink tasks first
        result = await db.execute(
            select(Task).where(Task.project_id == project.id)
        )
        for task in result.scalars():
            task.project_id = None
        await db.flush()
        await db.delete(project)

    # ── Stats ─────────────────────────────────────────────────────

    async def get_stats(self, db: AsyncSession, user_id: str) -> dict:
        total = (await db.execute(
            select(func.count(Task.id)).where(
                Task.user_id == user_id, Task.parent_id.is_(None)
            )
        )).scalar_one()

        done = (await db.execute(
            select(func.count(Task.id)).where(
                Task.user_id == user_id,
                Task.status == "done",
                Task.parent_id.is_(None),
            )
        )).scalar_one()

        today = datetime.now(timezone.utc).date()
        today_due = (await db.execute(
            select(func.count(Task.id)).where(
                Task.user_id == user_id,
                func.date(Task.due_date) == today,
                Task.status.notin_(["done", "cancelled"]),
            )
        )).scalar_one()

        overdue = (await db.execute(
            select(func.count(Task.id)).where(
                Task.user_id == user_id,
                Task.due_date < datetime.now(timezone.utc),
                Task.status.notin_(["done", "cancelled"]),
            )
        )).scalar_one()

        return {
            "total": total,
            "done": done,
            "today_due": today_due,
            "overdue": overdue,
            "completion_rate": round(done / total * 100, 1) if total else 0.0,
        }


task_service = TaskService()
