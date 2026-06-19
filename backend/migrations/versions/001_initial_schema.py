"""
migrations/versions/001_initial_schema.py
─────────────────────────────────────────
Initial database schema.
Creates all tables + FTS triggers + pg_trgm extension.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ── Extensions ────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    # ── Users ─────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255)),
        sa.Column("avatar_url", sa.String(1024)),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("is_verified", sa.Boolean, default=False, nullable=False),
        sa.Column("settings", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(255), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("ip_address", sa.String(64)),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])

    # ── Folders ───────────────────────────────────────────────────
    op.create_table(
        "folders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("folders.id", ondelete="CASCADE")),
        sa.Column("color", sa.String(32), default="#6C6C6C"),
        sa.Column("icon", sa.String(64), default="folder"),
        sa.Column("sort_order", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_folders_user_id", "folders", ["user_id"])

    # ── Tags ──────────────────────────────────────────────────────
    op.create_table(
        "tags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(32), default="#6C6C6C"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "name", name="uq_tags_user_name"),
    )
    op.create_index("ix_tags_user_id", "tags", ["user_id"])

    # ── Notes ─────────────────────────────────────────────────────
    op.create_table(
        "notes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("folder_id", sa.String(36), sa.ForeignKey("folders.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(500), nullable=False, default="Untitled Note"),
        sa.Column("content", sa.Text, default=""),
        sa.Column("content_html", sa.Text, default=""),
        sa.Column("color_label", sa.String(32)),
        sa.Column("is_pinned", sa.Boolean, default=False),
        sa.Column("is_archived", sa.Boolean, default=False),
        sa.Column("is_deleted", sa.Boolean, default=False),
        sa.Column("word_count", sa.Integer, default=0),
        sa.Column("char_count", sa.Integer, default=0),
        sa.Column("sort_order", sa.Integer, default=0),
        sa.Column("search_vector", TSVECTOR),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_notes_user_id", "notes", ["user_id"])
    op.create_index("ix_notes_folder_id", "notes", ["folder_id"])
    op.create_index("ix_notes_updated_at", "notes", ["updated_at"])
    op.create_index("ix_notes_is_deleted", "notes", ["is_deleted"])
    op.execute(
        "CREATE INDEX ix_notes_search_vector ON notes USING gin(search_vector)"
    )

    op.create_table(
        "note_tags",
        sa.Column("note_id", sa.String(36), sa.ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.String(36), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "note_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("note_id", sa.String(36), sa.ForeignKey("notes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("s3_key", sa.String(1024), nullable=False),
        sa.Column("s3_bucket", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("file_size", sa.BigInteger, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_note_attachments_note_id", "note_attachments", ["note_id"])

    # ── Projects ──────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("color", sa.String(32), default="#6C6C6C"),
        sa.Column("icon", sa.String(64), default="briefcase"),
        sa.Column("description", sa.Text, default=""),
        sa.Column("sort_order", sa.Integer, default=0),
        sa.Column("is_archived", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    # ── Tasks ─────────────────────────────────────────────────────
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE")),
        sa.Column("title", sa.String(1000), nullable=False),
        sa.Column("description", sa.Text, default=""),
        sa.Column("status", sa.String(32), default="todo", nullable=False),
        sa.Column("priority", sa.Integer, default=3, nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True)),
        sa.Column("due_time", sa.String(8)),
        sa.Column("reminder_at", sa.DateTime(timezone=True)),
        sa.Column("recurrence_rule", sa.String(255)),
        sa.Column("is_pinned", sa.Boolean, default=False),
        sa.Column("sort_order", sa.Integer, default=0),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("kanban_column", sa.String(32), default="todo"),
        sa.Column("search_vector", TSVECTOR),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_due_date", "tasks", ["due_date"])
    op.execute(
        "CREATE INDEX ix_tasks_search_vector ON tasks USING gin(search_vector)"
    )

    op.create_table(
        "task_tags",
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.String(36), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )

    # ── Pomodoro ──────────────────────────────────────────────────
    op.create_table(
        "pomodoro_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL")),
        sa.Column("duration", sa.Integer, default=1500),
        sa.Column("session_type", sa.String(32), default="work"),
        sa.Column("completed", sa.Boolean, default=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_pomodoro_user_id", "pomodoro_sessions", ["user_id"])

    # ── FTS Triggers (PostgreSQL) ─────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION notes_fts_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(NEW.content, '')), 'B');
            NEW.updated_at := now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER notes_fts_trigger
        BEFORE INSERT OR UPDATE OF title, content ON notes
        FOR EACH ROW EXECUTE FUNCTION notes_fts_update();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION tasks_fts_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(NEW.description, '')), 'B');
            NEW.updated_at := now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER tasks_fts_trigger
        BEFORE INSERT OR UPDATE OF title, description ON tasks
        FOR EACH ROW EXECUTE FUNCTION tasks_fts_update();
    """)

    # ── updated_at auto-update triggers ───────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN NEW.updated_at = now(); RETURN NEW; END;
        $$ LANGUAGE plpgsql;
    """)
    for tbl in ("folders", "projects"):
        op.execute(f"""
            CREATE TRIGGER {tbl}_updated_at
            BEFORE UPDATE ON {tbl}
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """)


def downgrade():
    for tbl in ("pomodoro_sessions", "task_tags", "tasks", "projects",
                "note_attachments", "note_tags", "notes",
                "tags", "folders", "refresh_tokens", "users"):
        op.drop_table(tbl)
    op.execute("DROP FUNCTION IF EXISTS notes_fts_update() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS tasks_fts_update() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at() CASCADE")
