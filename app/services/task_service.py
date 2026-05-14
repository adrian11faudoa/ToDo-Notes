"""
services/task_service.py
────────────────────────
Business logic layer for Tasks / To-Do system.
Handles CRUD, subtasks, recurrence, Kanban, daily planner.
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, date, timedelta
from typing import Optional

from app.database.connection import db
from app.models.entities import Task, Project, Tag, Priority, TaskStatus

logger = logging.getLogger(__name__)


def _parse_dt(val) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except ValueError:
        return None


def _row_to_task(row) -> Task:
    d = dict(row)
    return Task(
        id=d["id"],
        title=d["title"],
        description=d.get("description", ""),
        project_id=d.get("project_id"),
        parent_id=d.get("parent_id"),
        status=d.get("status", TaskStatus.TODO),
        priority=d.get("priority", Priority.MEDIUM),
        due_date=_parse_dt(d.get("due_date")),
        due_time=d.get("due_time"),
        reminder_at=_parse_dt(d.get("reminder_at")),
        recurrence_rule=d.get("recurrence_rule"),
        is_pinned=bool(d.get("is_pinned", 0)),
        sort_order=d.get("sort_order", 0),
        completed_at=_parse_dt(d.get("completed_at")),
        kanban_column=d.get("kanban_column", "todo"),
        created_at=_parse_dt(d.get("created_at")) or datetime.now(),
        updated_at=_parse_dt(d.get("updated_at")) or datetime.now(),
        project_name=d.get("project_name", ""),
    )


class TaskService:
    """Full task management — CRUD, subtasks, recurrence, Kanban."""

    # ── CREATE ──────────────────────────────────────────

    def create_task(self, title: str,
                    project_id: Optional[int] = None,
                    parent_id: Optional[int] = None,
                    priority: int = Priority.MEDIUM,
                    due_date: Optional[datetime] = None) -> Task:
        with db.transaction() as conn:
            cur = conn.execute(
                """INSERT INTO tasks
                   (title, project_id, parent_id, priority, due_date,
                    status, kanban_column, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'todo', 'todo',
                           CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                (title, project_id, parent_id, priority,
                 due_date.isoformat() if due_date else None)
            )
            task_id = cur.lastrowid
        return self.get_task(task_id)

    # ── READ ─────────────────────────────────────────────

    def get_task(self, task_id: int) -> Optional[Task]:
        row = db.fetchone(
            """SELECT t.*, p.name AS project_name
               FROM tasks t
               LEFT JOIN projects p ON t.project_id = p.id
               WHERE t.id = ?""",
            (task_id,)
        )
        if not row:
            return None
        task = _row_to_task(row)
        task.subtasks = self.get_subtasks(task_id)
        task.tags = self._get_task_tags(task_id)
        return task

    def get_all_tasks(self, project_id: Optional[int] = None,
                      status: Optional[str] = None,
                      include_subtasks: bool = False) -> list[Task]:
        conditions = ["t.parent_id IS NULL" if not include_subtasks else "1=1"]
        params: list = []

        if project_id is not None:
            conditions.append("t.project_id = ?")
            params.append(project_id)
        if status:
            conditions.append("t.status = ?")
            params.append(status)

        where = " AND ".join(conditions)
        rows = db.fetchall(
            f"""SELECT t.*, p.name AS project_name
                FROM tasks t
                LEFT JOIN projects p ON t.project_id = p.id
                WHERE {where}
                ORDER BY t.is_pinned DESC, t.priority ASC, t.sort_order ASC, t.created_at DESC""",
            params
        )
        tasks = [_row_to_task(r) for r in rows]
        if tasks and not include_subtasks:
            sub_map = self._batch_load_subtasks([t.id for t in tasks])
            for t in tasks:
                t.subtasks = sub_map.get(t.id, [])
        return tasks

    def get_subtasks(self, parent_id: int) -> list[Task]:
        rows = db.fetchall(
            """SELECT t.*, p.name AS project_name
               FROM tasks t
               LEFT JOIN projects p ON t.project_id = p.id
               WHERE t.parent_id = ?
               ORDER BY t.sort_order ASC, t.created_at ASC""",
            (parent_id,)
        )
        return [_row_to_task(r) for r in rows]

    def _batch_load_subtasks(self, parent_ids: list[int]) -> dict[int, list[Task]]:
        if not parent_ids:
            return {}
        placeholders = ",".join("?" * len(parent_ids))
        rows = db.fetchall(
            f"""SELECT t.*, p.name AS project_name
                FROM tasks t
                LEFT JOIN projects p ON t.project_id = p.id
                WHERE t.parent_id IN ({placeholders})
                ORDER BY t.sort_order ASC""",
            parent_ids
        )
        result: dict[int, list[Task]] = {}
        for r in rows:
            t = _row_to_task(r)
            result.setdefault(t.parent_id, []).append(t)
        return result

    def get_today_tasks(self) -> list[Task]:
        today = date.today().isoformat()
        rows = db.fetchall(
            """SELECT t.*, p.name AS project_name
               FROM tasks t
               LEFT JOIN projects p ON t.project_id = p.id
               WHERE (DATE(t.due_date) = ? OR t.status = 'in_progress')
                 AND t.status != 'done' AND t.status != 'cancelled'
               ORDER BY t.priority ASC, t.due_date ASC""",
            (today,)
        )
        return [_row_to_task(r) for r in rows]

    def get_overdue_tasks(self) -> list[Task]:
        now = datetime.now().isoformat()
        rows = db.fetchall(
            """SELECT t.*, p.name AS project_name
               FROM tasks t
               LEFT JOIN projects p ON t.project_id = p.id
               WHERE t.due_date < ? AND t.status NOT IN ('done', 'cancelled')
               ORDER BY t.due_date ASC""",
            (now,)
        )
        return [_row_to_task(r) for r in rows]

    def get_upcoming_tasks(self, days: int = 7) -> list[Task]:
        start = date.today()
        end = start + timedelta(days=days)
        rows = db.fetchall(
            """SELECT t.*, p.name AS project_name
               FROM tasks t
               LEFT JOIN projects p ON t.project_id = p.id
               WHERE DATE(t.due_date) BETWEEN ? AND ?
                 AND t.status NOT IN ('done', 'cancelled')
               ORDER BY t.due_date ASC, t.priority ASC""",
            (start.isoformat(), end.isoformat())
        )
        return [_row_to_task(r) for r in rows]

    def get_kanban_board(self, project_id: Optional[int] = None) -> dict[str, list[Task]]:
        """Return tasks grouped by kanban_column."""
        conditions = ["t.parent_id IS NULL"]
        params: list = []
        if project_id:
            conditions.append("t.project_id = ?")
            params.append(project_id)
        where = " AND ".join(conditions)
        rows = db.fetchall(
            f"""SELECT t.*, p.name AS project_name
                FROM tasks t
                LEFT JOIN projects p ON t.project_id = p.id
                WHERE {where}
                ORDER BY t.sort_order ASC""",
            params
        )
        columns: dict[str, list[Task]] = {
            "todo": [], "in_progress": [], "done": [], "cancelled": []
        }
        for r in rows:
            t = _row_to_task(r)
            col = t.kanban_column or "todo"
            columns.setdefault(col, []).append(t)
        return columns

    def search_tasks(self, query: str) -> list[Task]:
        if not query.strip():
            return self.get_all_tasks()
        safe = query.replace('"', '""')
        rows = db.fetchall(
            """SELECT t.*, p.name AS project_name
               FROM tasks_fts
               JOIN tasks t ON tasks_fts.rowid = t.id
               LEFT JOIN projects p ON t.project_id = p.id
               WHERE tasks_fts MATCH ?
               ORDER BY rank""",
            (f'"{safe}"',)
        )
        return [_row_to_task(r) for r in rows]

    # ── UPDATE ───────────────────────────────────────────

    def update_task(self, task_id: int, **kwargs) -> bool:
        allowed = {
            "title", "description", "project_id", "priority", "status",
            "due_date", "due_time", "reminder_at", "recurrence_rule",
            "is_pinned", "sort_order", "kanban_column", "completed_at"
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False

        # Auto-set completed_at when marking done
        if updates.get("status") == TaskStatus.DONE:
            updates["completed_at"] = datetime.now().isoformat()
        elif "status" in updates and updates["status"] != TaskStatus.DONE:
            updates["completed_at"] = None

        # Serialize datetime objects
        for k in ("due_date", "reminder_at", "completed_at"):
            if k in updates and isinstance(updates[k], datetime):
                updates[k] = updates[k].isoformat()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [task_id]
        with db.transaction() as conn:
            conn.execute(
                f"UPDATE tasks SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                values
            )
        return True

    def complete_task(self, task_id: int):
        """Mark task done and handle recurrence."""
        task = self.get_task(task_id)
        if not task:
            return
        self.update_task(task_id, status=TaskStatus.DONE)

        # Handle recurrence: create next occurrence
        if task.recurrence_rule and task.due_date:
            next_due = self._next_recurrence(task.due_date, task.recurrence_rule)
            if next_due:
                self.create_task(
                    title=task.title,
                    project_id=task.project_id,
                    priority=task.priority,
                    due_date=next_due,
                )

    def _next_recurrence(self, from_date: datetime, rule: str) -> Optional[datetime]:
        """Simple recurrence: daily/weekly/monthly/yearly."""
        rule = rule.lower()
        if rule == "daily":
            return from_date + timedelta(days=1)
        if rule == "weekly":
            return from_date + timedelta(weeks=1)
        if rule == "monthly":
            d = from_date
            month = d.month + 1 if d.month < 12 else 1
            year = d.year if d.month < 12 else d.year + 1
            try:
                return d.replace(year=year, month=month)
            except ValueError:
                return None
        if rule == "yearly":
            try:
                return from_date.replace(year=from_date.year + 1)
            except ValueError:
                return None
        return None

    def move_to_kanban(self, task_id: int, column: str):
        status_map = {
            "todo": TaskStatus.TODO,
            "in_progress": TaskStatus.IN_PROGRESS,
            "done": TaskStatus.DONE,
            "cancelled": TaskStatus.CANCELLED,
        }
        self.update_task(
            task_id,
            kanban_column=column,
            status=status_map.get(column, TaskStatus.TODO)
        )

    def reorder_task(self, task_id: int, new_order: int):
        self.update_task(task_id, sort_order=new_order)

    # ── DELETE ───────────────────────────────────────────

    def delete_task(self, task_id: int):
        with db.transaction() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ? OR parent_id = ?",
                         (task_id, task_id))

    # ── TAGS ─────────────────────────────────────────────

    def _get_task_tags(self, task_id: int) -> list[Tag]:
        rows = db.fetchall(
            """SELECT t.* FROM tags t
               JOIN task_tags tt ON tt.tag_id = t.id
               WHERE tt.task_id = ?""",
            (task_id,)
        )
        return [Tag(id=r["id"], name=r["name"], color=r["color"]) for r in rows]

    def add_tag_to_task(self, task_id: int, tag_name: str) -> Tag:
        tag = self._get_or_create_tag(tag_name)
        with db.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO task_tags (task_id, tag_id) VALUES (?, ?)",
                (task_id, tag.id)
            )
        return tag

    def _get_or_create_tag(self, name: str) -> Tag:
        row = db.fetchone("SELECT * FROM tags WHERE name = ?", (name,))
        if row:
            return Tag(id=row["id"], name=row["name"], color=row["color"])
        with db.transaction() as conn:
            cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
            return Tag(id=cur.lastrowid, name=name)

    # ── PROJECTS ─────────────────────────────────────────

    def get_all_projects(self) -> list[Project]:
        rows = db.fetchall(
            """SELECT p.*,
                      COUNT(t.id) AS task_count,
                      SUM(CASE WHEN t.status='done' THEN 1 ELSE 0 END) AS completed_count
               FROM projects p
               LEFT JOIN tasks t ON t.project_id = p.id AND t.parent_id IS NULL
               WHERE p.is_archived = 0
               GROUP BY p.id
               ORDER BY p.sort_order ASC, p.name ASC"""
        )
        return [Project(
            id=r["id"], name=r["name"], color=r["color"], icon=r["icon"],
            description=r["description"], sort_order=r["sort_order"],
            task_count=r["task_count"] or 0,
            completed_count=r["completed_count"] or 0,
        ) for r in rows]

    def create_project(self, name: str, color: str = "#6C6C6C",
                       description: str = "") -> Project:
        with db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO projects (name, color, description) VALUES (?, ?, ?)",
                (name, color, description)
            )
        return Project(id=cur.lastrowid, name=name, color=color, description=description)

    def update_project(self, project_id: int, **kwargs):
        allowed = {"name", "color", "icon", "description", "sort_order"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        with db.transaction() as conn:
            conn.execute(
                f"UPDATE projects SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                list(updates.values()) + [project_id]
            )

    def delete_project(self, project_id: int):
        with db.transaction() as conn:
            conn.execute("UPDATE tasks SET project_id = NULL WHERE project_id = ?",
                         (project_id,))
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    # ── STATS ─────────────────────────────────────────────

    def get_stats(self) -> dict:
        total = db.fetchone("SELECT COUNT(*) AS c FROM tasks WHERE parent_id IS NULL")["c"]
        done = db.fetchone(
            "SELECT COUNT(*) AS c FROM tasks WHERE status='done' AND parent_id IS NULL"
        )["c"]
        today_due = db.fetchone(
            "SELECT COUNT(*) AS c FROM tasks WHERE DATE(due_date)=DATE('now') AND status!='done'"
        )["c"]
        overdue = db.fetchone(
            "SELECT COUNT(*) AS c FROM tasks WHERE due_date < DATETIME('now') AND status NOT IN ('done','cancelled')"
        )["c"]
        return {
            "total": total, "done": done,
            "today_due": today_due, "overdue": overdue,
            "completion_rate": round(done / total * 100, 1) if total else 0,
        }


task_service = TaskService()
