-- NoteFlow Database Schema v1.0
-- SQLite3

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA synchronous=NORMAL;

-- ─────────────────────────────────────────────
-- NOTES SYSTEM
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS folders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    parent_id   INTEGER REFERENCES folders(id) ON DELETE CASCADE,
    color       TEXT DEFAULT '#6C6C6C',
    icon        TEXT DEFAULT 'folder',
    sort_order  INTEGER DEFAULT 0,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    color       TEXT DEFAULT '#6C6C6C',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL DEFAULT 'Untitled Note',
    content         TEXT DEFAULT '',
    content_html    TEXT DEFAULT '',
    folder_id       INTEGER REFERENCES folders(id) ON DELETE SET NULL,
    color_label     TEXT DEFAULT NULL,
    is_pinned       INTEGER DEFAULT 0,
    is_archived     INTEGER DEFAULT 0,
    is_deleted      INTEGER DEFAULT 0,
    word_count      INTEGER DEFAULT 0,
    char_count      INTEGER DEFAULT 0,
    sort_order      INTEGER DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    deleted_at      DATETIME DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS note_tags (
    note_id     INTEGER REFERENCES notes(id) ON DELETE CASCADE,
    tag_id      INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, tag_id)
);

CREATE TABLE IF NOT EXISTS note_attachments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id     INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    filename    TEXT NOT NULL,
    filepath    TEXT NOT NULL,
    filetype    TEXT NOT NULL,
    filesize    INTEGER DEFAULT 0,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────────────────────
-- TODO SYSTEM
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    color       TEXT DEFAULT '#6C6C6C',
    icon        TEXT DEFAULT 'briefcase',
    description TEXT DEFAULT '',
    sort_order  INTEGER DEFAULT 0,
    is_archived INTEGER DEFAULT 0,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    description     TEXT DEFAULT '',
    project_id      INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    parent_id       INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    status          TEXT DEFAULT 'todo' CHECK(status IN ('todo','in_progress','done','cancelled')),
    priority        INTEGER DEFAULT 2 CHECK(priority IN (1,2,3,4)),  -- 1=urgent,2=high,3=medium,4=low
    due_date        DATETIME DEFAULT NULL,
    due_time        TEXT DEFAULT NULL,
    reminder_at     DATETIME DEFAULT NULL,
    recurrence_rule TEXT DEFAULT NULL,  -- iCal RRULE format
    is_pinned       INTEGER DEFAULT 0,
    sort_order      INTEGER DEFAULT 0,
    completed_at    DATETIME DEFAULT NULL,
    kanban_column   TEXT DEFAULT 'todo',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS task_tags (
    task_id     INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    tag_id      INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, tag_id)
);

-- ─────────────────────────────────────────────
-- POMODORO SYSTEM
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pomodoro_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    duration    INTEGER NOT NULL DEFAULT 1500,  -- seconds
    type        TEXT DEFAULT 'work' CHECK(type IN ('work','short_break','long_break')),
    completed   INTEGER DEFAULT 0,
    started_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at    DATETIME DEFAULT NULL
);

-- ─────────────────────────────────────────────
-- SETTINGS & CONFIG
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────────────────────
-- UNDO/REDO HISTORY
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,  -- 'note' | 'task'
    entity_id   INTEGER NOT NULL,
    action      TEXT NOT NULL,  -- 'create' | 'update' | 'delete'
    snapshot    TEXT NOT NULL,  -- JSON snapshot of the record
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────────────────────
-- FULL-TEXT SEARCH
-- ─────────────────────────────────────────────

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    title, content, content='notes', content_rowid='id'
);

CREATE VIRTUAL TABLE IF NOT EXISTS tasks_fts USING fts5(
    title, description, content='tasks', content_rowid='id'
);

-- ─────────────────────────────────────────────
-- TRIGGERS: keep FTS, timestamps, word count in sync
-- ─────────────────────────────────────────────

CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, title, content) VALUES ('delete', old.id, old.title, old.content);
END;

CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, title, content) VALUES ('delete', old.id, old.title, old.content);
    INSERT INTO notes_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
    UPDATE notes SET updated_at = CURRENT_TIMESTAMP WHERE id = new.id;
END;

CREATE TRIGGER IF NOT EXISTS tasks_ai AFTER INSERT ON tasks BEGIN
    INSERT INTO tasks_fts(rowid, title, description) VALUES (new.id, new.title, new.description);
END;

CREATE TRIGGER IF NOT EXISTS tasks_ad AFTER DELETE ON tasks BEGIN
    INSERT INTO tasks_fts(tasks_fts, rowid, title, description) VALUES ('delete', old.id, old.title, old.description);
END;

CREATE TRIGGER IF NOT EXISTS tasks_au AFTER UPDATE ON tasks BEGIN
    INSERT INTO tasks_fts(tasks_fts, rowid, title, description) VALUES ('delete', old.id, old.title, old.description);
    INSERT INTO tasks_fts(rowid, title, description) VALUES (new.id, new.title, new.description);
    UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = new.id;
END;

-- ─────────────────────────────────────────────
-- DEFAULT DATA
-- ─────────────────────────────────────────────

INSERT OR IGNORE INTO folders (id, name, color, icon) VALUES (1, 'Personal', '#4A9EFF', 'user');
INSERT OR IGNORE INTO folders (id, name, color, icon) VALUES (2, 'Work', '#FF6B6B', 'briefcase');
INSERT OR IGNORE INTO folders (id, name, color, icon) VALUES (3, 'Ideas', '#FFD93D', 'lightbulb');

INSERT OR IGNORE INTO projects (id, name, color, icon) VALUES (1, 'Personal', '#4A9EFF', 'user');
INSERT OR IGNORE INTO projects (id, name, color, icon) VALUES (2, 'Work', '#FF6B6B', 'briefcase');

INSERT OR IGNORE INTO settings (key, value) VALUES ('theme', 'dark');
INSERT OR IGNORE INTO settings (key, value) VALUES ('accent_color', '#4A9EFF');
INSERT OR IGNORE INTO settings (key, value) VALUES ('font_size', '14');
INSERT OR IGNORE INTO settings (key, value) VALUES ('autosave_interval', '3');
INSERT OR IGNORE INTO settings (key, value) VALUES ('language', 'en');
INSERT OR IGNORE INTO settings (key, value) VALUES ('pomodoro_work', '1500');
INSERT OR IGNORE INTO settings (key, value) VALUES ('pomodoro_short_break', '300');
INSERT OR IGNORE INTO settings (key, value) VALUES ('pomodoro_long_break', '900');
INSERT OR IGNORE INTO settings (key, value) VALUES ('startup_page', 'notes');
INSERT OR IGNORE INTO settings (key, value) VALUES ('backup_enabled', '1');
INSERT OR IGNORE INTO settings (key, value) VALUES ('backup_interval', '86400');
INSERT OR IGNORE INTO settings (key, value) VALUES ('show_word_count', '1');
INSERT OR IGNORE INTO settings (key, value) VALUES ('default_view', 'list');
