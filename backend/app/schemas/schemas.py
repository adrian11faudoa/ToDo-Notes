"""
schemas/schemas.py
──────────────────
Pydantic v2 schemas for all API request/response models.
Separate In (request) / Out (response) models for every entity.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator
import re


# ── Shared helpers ────────────────────────────────────────────────

class OrmBase(BaseModel):
    model_config = {"from_attributes": True}


# ── AUTH ─────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: Optional[str] = Field(None, max_length=255)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int      # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(OrmBase):
    id: str
    email: str
    full_name: Optional[str]
    avatar_url: Optional[str]
    is_active: bool
    is_verified: bool
    settings: Optional[dict]
    created_at: datetime
    last_login_at: Optional[datetime]


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=255)
    settings: Optional[dict] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


# ── FOLDER ────────────────────────────────────────────────────────

class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: Optional[str] = None
    color: str = "#6C6C6C"
    icon: str = "folder"
    sort_order: int = 0


class FolderUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    parent_id: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None


class FolderOut(OrmBase):
    id: str
    name: str
    parent_id: Optional[str]
    color: str
    icon: str
    sort_order: int
    note_count: int = 0
    created_at: datetime
    updated_at: datetime


# ── TAG ───────────────────────────────────────────────────────────

class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = "#6C6C6C"


class TagOut(OrmBase):
    id: str
    name: str
    color: str
    created_at: datetime


# ── NOTE ──────────────────────────────────────────────────────────

class NoteCreate(BaseModel):
    title: str = Field(default="Untitled Note", max_length=500)
    content: str = ""
    folder_id: Optional[str] = None
    color_label: Optional[str] = None
    is_pinned: bool = False
    tags: List[str] = Field(default_factory=list)   # tag names


class NoteUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    content: Optional[str] = None
    folder_id: Optional[str] = None
    color_label: Optional[str] = None
    is_pinned: Optional[bool] = None
    is_archived: Optional[bool] = None
    sort_order: Optional[int] = None


class NoteAttachmentOut(OrmBase):
    id: str
    filename: str
    s3_key: str
    content_type: str
    file_size: int
    created_at: datetime
    presigned_url: Optional[str] = None   # populated on demand


class NoteOut(OrmBase):
    id: str
    title: str
    content: str
    content_html: str
    folder_id: Optional[str]
    color_label: Optional[str]
    is_pinned: bool
    is_archived: bool
    word_count: int
    char_count: int
    sort_order: int
    created_at: datetime
    updated_at: datetime
    tags: List[TagOut] = []
    attachments: List[NoteAttachmentOut] = []

    @property
    def preview(self) -> str:
        clean = re.sub(r"[#*_`\[\]()>~]", "", self.content)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean[:200] + ("…" if len(clean) > 200 else "")


class NoteSummary(OrmBase):
    """Lightweight note for list views — no full content."""
    id: str
    title: str
    content: str = Field(exclude=True)
    folder_id: Optional[str]
    color_label: Optional[str]
    is_pinned: bool
    is_archived: bool
    word_count: int
    updated_at: datetime
    tags: List[TagOut] = []

    @property
    def preview(self) -> str:
        clean = re.sub(r"[#*_`\[\]()>~]", "", self.content)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean[:200] + ("…" if len(clean) > 200 else "")


# ── PROJECT ───────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    color: str = "#6C6C6C"
    icon: str = "briefcase"
    description: str = ""


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    color: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_archived: Optional[bool] = None


class ProjectOut(OrmBase):
    id: str
    name: str
    color: str
    icon: str
    description: str
    sort_order: int
    is_archived: bool
    task_count: int = 0
    completed_count: int = 0
    created_at: datetime
    updated_at: datetime


# ── TASK ──────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=1000)
    description: str = ""
    project_id: Optional[str] = None
    parent_id: Optional[str] = None
    priority: int = Field(default=3, ge=1, le=4)
    due_date: Optional[datetime] = None
    due_time: Optional[str] = None
    reminder_at: Optional[datetime] = None
    recurrence_rule: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=1000)
    description: Optional[str] = None
    project_id: Optional[str] = None
    priority: Optional[int] = Field(None, ge=1, le=4)
    status: Optional[str] = None
    due_date: Optional[datetime] = None
    due_time: Optional[str] = None
    reminder_at: Optional[datetime] = None
    recurrence_rule: Optional[str] = None
    is_pinned: Optional[bool] = None
    sort_order: Optional[int] = None
    kanban_column: Optional[str] = None


class TaskOut(OrmBase):
    id: str
    title: str
    description: str
    project_id: Optional[str]
    parent_id: Optional[str]
    status: str
    priority: int
    due_date: Optional[datetime]
    due_time: Optional[str]
    reminder_at: Optional[datetime]
    recurrence_rule: Optional[str]
    is_pinned: bool
    sort_order: int
    completed_at: Optional[datetime]
    kanban_column: str
    created_at: datetime
    updated_at: datetime
    tags: List[TagOut] = []
    subtasks: List["TaskOut"] = []

    @property
    def is_overdue(self) -> bool:
        return bool(
            self.due_date
            and self.status not in ("done", "cancelled")
            and self.due_date < datetime.utcnow()
        )

    @property
    def progress(self) -> float:
        if not self.subtasks:
            return 1.0 if self.status == "done" else 0.0
        done = sum(1 for t in self.subtasks if t.status == "done")
        return done / len(self.subtasks)


# ── POMODORO ──────────────────────────────────────────────────────

class PomodoroCreate(BaseModel):
    task_id: Optional[str] = None
    duration: int = Field(default=1500, ge=60, le=7200)
    session_type: str = Field(default="work", pattern="^(work|short_break|long_break)$")


class PomodoroComplete(BaseModel):
    ended_at: Optional[datetime] = None


class PomodoroOut(OrmBase):
    id: str
    task_id: Optional[str]
    duration: int
    session_type: str
    completed: bool
    started_at: datetime
    ended_at: Optional[datetime]


# ── SEARCH ────────────────────────────────────────────────────────

class SearchResult(BaseModel):
    notes: List[NoteSummary] = []
    tasks: List[TaskOut] = []
    total_notes: int = 0
    total_tasks: int = 0


# ── PAGINATION ────────────────────────────────────────────────────

class Page(BaseModel):
    page: int = 1
    size: int = 50
    total: int = 0
    pages: int = 0


class NoteListResponse(BaseModel):
    items: List[NoteSummary]
    pagination: Page


class TaskListResponse(BaseModel):
    items: List[TaskOut]
    pagination: Page


# ── UPLOAD ────────────────────────────────────────────────────────

class PresignedUploadResponse(BaseModel):
    upload_url: str
    attachment_id: str
    s3_key: str
    expires_in: int


# ── STATS ─────────────────────────────────────────────────────────

class UserStats(BaseModel):
    total_notes: int
    total_tasks: int
    completed_tasks: int
    overdue_tasks: int
    today_tasks: int
    completion_rate: float
    total_pomodoros: int
    total_focus_minutes: int


# ── HEALTH ────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    db: bool
    redis: bool
    s3: bool
