"""
models/entities.py
──────────────────
Pure data models — no database logic here.
These are plain dataclasses used throughout the app.
Controllers and services work with these objects; views display them.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ─────────────────────────────────────────────
# NOTES
# ─────────────────────────────────────────────

@dataclass
class Tag:
    id: int = 0
    name: str = ""
    color: str = "#6C6C6C"
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Folder:
    id: int = 0
    name: str = "Untitled Folder"
    parent_id: Optional[int] = None
    color: str = "#6C6C6C"
    icon: str = "folder"
    sort_order: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    # Runtime-only
    children: list[Folder] = field(default_factory=list)
    note_count: int = 0


@dataclass
class NoteAttachment:
    id: int = 0
    note_id: int = 0
    filename: str = ""
    filepath: str = ""
    filetype: str = ""
    filesize: int = 0
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Note:
    id: int = 0
    title: str = "Untitled Note"
    content: str = ""           # Raw markdown
    content_html: str = ""      # Rendered HTML cache
    folder_id: Optional[int] = None
    color_label: Optional[str] = None
    is_pinned: bool = False
    is_archived: bool = False
    is_deleted: bool = False
    word_count: int = 0
    char_count: int = 0
    sort_order: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    deleted_at: Optional[datetime] = None
    # Runtime-only (populated by join queries)
    tags: list[Tag] = field(default_factory=list)
    attachments: list[NoteAttachment] = field(default_factory=list)
    folder_name: str = ""

    @property
    def preview(self) -> str:
        """First 200 chars of content stripped of markdown symbols."""
        import re
        text = re.sub(r'[#*_`\[\]()>~]', '', self.content)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:200] + ("…" if len(text) > 200 else "")

    @property
    def updated_relative(self) -> str:
        """Human-readable relative timestamp."""
        delta = datetime.now() - self.updated_at
        if delta.seconds < 60:
            return "Just now"
        if delta.seconds < 3600:
            return f"{delta.seconds // 60}m ago"
        if delta.days == 0:
            return f"{delta.seconds // 3600}h ago"
        if delta.days == 1:
            return "Yesterday"
        if delta.days < 7:
            return f"{delta.days}d ago"
        return self.updated_at.strftime("%b %d, %Y")


# ─────────────────────────────────────────────
# TASKS
# ─────────────────────────────────────────────

class Priority:
    URGENT = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4

    LABELS = {1: "Urgent", 2: "High", 3: "Medium", 4: "Low"}
    COLORS = {1: "#FF4444", 2: "#FF8C00", 3: "#4A9EFF", 4: "#6C6C6C"}

    @classmethod
    def label(cls, p: int) -> str:
        return cls.LABELS.get(p, "Medium")

    @classmethod
    def color(cls, p: int) -> str:
        return cls.COLORS.get(p, "#4A9EFF")


class TaskStatus:
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"

    LABELS = {
        "todo": "To Do",
        "in_progress": "In Progress",
        "done": "Done",
        "cancelled": "Cancelled",
    }


@dataclass
class Project:
    id: int = 0
    name: str = "Untitled Project"
    color: str = "#6C6C6C"
    icon: str = "briefcase"
    description: str = ""
    sort_order: int = 0
    is_archived: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    # Runtime
    task_count: int = 0
    completed_count: int = 0


@dataclass
class Task:
    id: int = 0
    title: str = ""
    description: str = ""
    project_id: Optional[int] = None
    parent_id: Optional[int] = None
    status: str = TaskStatus.TODO
    priority: int = Priority.MEDIUM
    due_date: Optional[datetime] = None
    due_time: Optional[str] = None
    reminder_at: Optional[datetime] = None
    recurrence_rule: Optional[str] = None
    is_pinned: bool = False
    sort_order: int = 0
    completed_at: Optional[datetime] = None
    kanban_column: str = "todo"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    # Runtime
    subtasks: list[Task] = field(default_factory=list)
    tags: list[Tag] = field(default_factory=list)
    project_name: str = ""

    @property
    def is_done(self) -> bool:
        return self.status == TaskStatus.DONE

    @property
    def is_overdue(self) -> bool:
        if self.due_date and not self.is_done:
            return self.due_date < datetime.now()
        return False

    @property
    def progress(self) -> float:
        """0.0–1.0 based on subtask completion."""
        if not self.subtasks:
            return 1.0 if self.is_done else 0.0
        done = sum(1 for t in self.subtasks if t.is_done)
        return done / len(self.subtasks)

    @property
    def due_label(self) -> str:
        if not self.due_date:
            return ""
        delta = self.due_date.date() - datetime.now().date()
        days = delta.days
        if days < 0:
            return f"Overdue {abs(days)}d"
        if days == 0:
            return "Today"
        if days == 1:
            return "Tomorrow"
        if days < 7:
            return f"In {days}d"
        return self.due_date.strftime("%b %d")


# ─────────────────────────────────────────────
# POMODORO
# ─────────────────────────────────────────────

@dataclass
class PomodoroSession:
    id: int = 0
    task_id: Optional[int] = None
    duration: int = 1500
    type: str = "work"
    completed: bool = False
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: Optional[datetime] = None


# ─────────────────────────────────────────────
# APP SETTINGS
# ─────────────────────────────────────────────

@dataclass
class AppSettings:
    theme: str = "dark"
    accent_color: str = "#4A9EFF"
    font_size: int = 14
    autosave_interval: int = 3
    language: str = "en"
    pomodoro_work: int = 1500
    pomodoro_short_break: int = 300
    pomodoro_long_break: int = 900
    startup_page: str = "notes"
    backup_enabled: bool = True
    backup_interval: int = 86400
    show_word_count: bool = True
    default_view: str = "list"
