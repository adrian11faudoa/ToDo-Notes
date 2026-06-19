"""
models/orm.py
─────────────
SQLAlchemy ORM models for all NoteFlow entities.
Maps directly to the PostgreSQL schema.
Multi-tenant: every row scoped to user_id.
"""

from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, String, Text, Boolean, Integer, DateTime,
    ForeignKey, UniqueConstraint, Index, Enum,
    BigInteger, func, text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


# ── USERS ─────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(1024))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    settings: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    notes = relationship("Note", back_populates="owner", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="owner", cascade="all, delete-orphan")
    folders = relationship("Folder", back_populates="owner", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")
    tags = relationship("Tag", back_populates="owner", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_agent: Mapped[Optional[str]] = mapped_column(String(512))
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))

    user = relationship("User", back_populates="refresh_tokens")

    __table_args__ = (
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_token_hash", "token_hash"),
    )


# ── FOLDERS ───────────────────────────────────────────────────────

class Folder(Base):
    __tablename__ = "folders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("folders.id", ondelete="CASCADE"))
    color: Mapped[str] = mapped_column(String(32), default="#6C6C6C")
    icon: Mapped[str] = mapped_column(String(64), default="folder")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner = relationship("User", back_populates="folders")
    notes = relationship("Note", back_populates="folder")
    children = relationship("Folder", backref=__import__("sqlalchemy.orm", fromlist=["backref"]).backref("parent", remote_side=[id]))

    __table_args__ = (Index("ix_folders_user_id", "user_id"),)


# ── TAGS ──────────────────────────────────────────────────────────

class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str] = mapped_column(String(32), default="#6C6C6C")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_tags_user_name"),
        Index("ix_tags_user_id", "user_id"),
    )


# ── NOTE ──────────────────────────────────────────────────────────

class Note(Base):
    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    folder_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("folders.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="Untitled Note")
    content: Mapped[str] = mapped_column(Text, default="")
    content_html: Mapped[str] = mapped_column(Text, default="")
    color_label: Mapped[Optional[str]] = mapped_column(String(32))
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # Full-text search vector (updated by trigger)
    search_vector: Mapped[Optional[object]] = mapped_column(TSVECTOR)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    owner = relationship("User", back_populates="notes")
    folder = relationship("Folder", back_populates="notes")
    tags = relationship("Tag", secondary="note_tags", lazy="selectin")
    attachments = relationship("NoteAttachment", back_populates="note", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_notes_user_id", "user_id"),
        Index("ix_notes_folder_id", "folder_id"),
        Index("ix_notes_updated_at", "updated_at"),
        Index("ix_notes_is_deleted", "is_deleted"),
        Index("ix_notes_search_vector", "search_vector", postgresql_using="gin"),
    )


class NoteTag(Base):
    __tablename__ = "note_tags"

    note_id: Mapped[str] = mapped_column(String(36), ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[str] = mapped_column(String(36), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class NoteAttachment(Base):
    __tablename__ = "note_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    note_id: Mapped[str] = mapped_column(String(36), ForeignKey("notes.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)   # S3 object key
    s3_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    note = relationship("Note", back_populates="attachments")

    __table_args__ = (Index("ix_note_attachments_note_id", "note_id"),)


# ── PROJECTS ──────────────────────────────────────────────────────

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    color: Mapped[str] = mapped_column(String(32), default="#6C6C6C")
    icon: Mapped[str] = mapped_column(String(64), default="briefcase")
    description: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner = relationship("User", back_populates="projects")
    tasks = relationship("Task", back_populates="project")

    __table_args__ = (Index("ix_projects_user_id", "user_id"),)


# ── TASK ──────────────────────────────────────────────────────────

class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"))
    parent_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="todo", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    due_time: Mapped[Optional[str]] = mapped_column(String(8))
    reminder_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    recurrence_rule: Mapped[Optional[str]] = mapped_column(String(255))
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    kanban_column: Mapped[str] = mapped_column(String(32), default="todo")
    search_vector: Mapped[Optional[object]] = mapped_column(TSVECTOR)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner = relationship("User", back_populates="tasks")
    project = relationship("Project", back_populates="tasks")
    subtasks = relationship("Task", backref=__import__("sqlalchemy.orm", fromlist=["backref"]).backref("parent_task", remote_side=[id]))
    tags = relationship("Tag", secondary="task_tags", lazy="selectin")

    __table_args__ = (
        Index("ix_tasks_user_id", "user_id"),
        Index("ix_tasks_project_id", "project_id"),
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_due_date", "due_date"),
        Index("ix_tasks_search_vector", "search_vector", postgresql_using="gin"),
    )


class TaskTag(Base):
    __tablename__ = "task_tags"

    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[str] = mapped_column(String(36), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


# ── POMODORO ──────────────────────────────────────────────────────

class PomodoroSession(Base):
    __tablename__ = "pomodoro_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="SET NULL"))
    duration: Mapped[int] = mapped_column(Integer, default=1500)
    session_type: Mapped[str] = mapped_column(String(32), default="work")
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_pomodoro_user_id", "user_id"),)
