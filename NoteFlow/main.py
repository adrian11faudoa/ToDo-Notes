"""
main.py
───────
NoteFlow application entry point.

Boot sequence:
  1. Configure logging
  2. Resolve data/config directories
  3. Show splash screen
  4. Initialize database
  5. Initialize services (settings, theme, backup)
  6. Launch main window
  7. Enter Qt event loop
"""

import sys
import os
import logging
import traceback
from pathlib import Path

# ── Ensure 'app' package is importable regardless of CWD ──────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ── Qt High-DPI policy (must be set before QApplication) ──────────
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont


# ──────────────────────────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────────────────────────

def _configure_logging(log_dir: Path):
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "noteflow.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.getLogger("PySide6").setLevel(logging.WARNING)
    return logging.getLogger("main")


# ──────────────────────────────────────────────────────────────────
# DATA DIRECTORIES
# ──────────────────────────────────────────────────────────────────

def _resolve_paths() -> dict[str, Path]:
    """Return all data/config paths for the current OS."""
    if sys.platform == "win32":
        base = Path(os.getenv("APPDATA", Path.home())) / "NoteFlow"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "NoteFlow"
    else:
        base = Path.home() / ".local" / "share" / "NoteFlow"

    paths = {
        "data":     base,
        "db":       base / "noteflow.db",
        "backup":   base / "backups",
        "logs":     base / "logs",
        "exports":  base / "exports",
        "plugins":  base / "plugins",
    }
    for p in paths.values():
        if p.suffix == "":          # directory
            p.mkdir(parents=True, exist_ok=True)
    return paths


# ──────────────────────────────────────────────────────────────────
# CRASH HANDLER
# ──────────────────────────────────────────────────────────────────

def _install_crash_handler(log_dir: Path):
    crash_log = log_dir / "crash.log"

    def handle_exception(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.getLogger("crash").critical(f"Unhandled exception:\n{msg}")
        try:
            crash_log.write_text(msg, encoding="utf-8")
        except Exception:
            pass
        # Show error dialog if QApplication is up
        app = QApplication.instance()
        if app:
            dlg = QMessageBox()
            dlg.setIcon(QMessageBox.Critical)
            dlg.setWindowTitle("NoteFlow — Unexpected Error")
            dlg.setText("NoteFlow encountered an unexpected error and needs to close.")
            dlg.setDetailedText(msg)
            dlg.exec()
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = handle_exception


# ──────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────

def main():
    # ── QApplication ──────────────────────────────────────────────
    app = QApplication(sys.argv)
    app.setApplicationName("NoteFlow")
    app.setOrganizationName("NoteFlow")
    app.setApplicationVersion("1.0.0")
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # ── Paths & logging ───────────────────────────────────────────
    paths = _resolve_paths()
    logger = _configure_logging(paths["logs"])
    _install_crash_handler(paths["logs"])
    logger.info("NoteFlow starting up…")
    logger.info(f"Data directory: {paths['data']}")

    # ── Splash screen ──────────────────────────────────────────────
    from app.widgets.splash_screen import SplashScreen
    splash = SplashScreen()
    splash.show()
    app.processEvents()

    try:
        # ── Database ──────────────────────────────────────────────
        splash.set_message("Initializing database…")
        app.processEvents()
        from app.database.connection import db
        db.initialize(str(paths["db"]))

        # ── Settings ──────────────────────────────────────────────
        splash.set_message("Loading settings…")
        app.processEvents()
        from app.config.settings_manager import settings_manager
        settings_manager.initialize()

        # ── Theme ─────────────────────────────────────────────────
        splash.set_message("Applying theme…")
        app.processEvents()
        from app.themes.theme_manager import theme
        theme.initialize(
            theme=settings_manager.get("theme", "dark"),
            accent=settings_manager.get("accent_color", "#4A9EFF"),
        )
        theme._apply_stylesheet()

        # ── Global font ───────────────────────────────────────────
        font_size = settings_manager.get_int("font_size", 14)
        app_font = QFont("Segoe UI", font_size)
        app_font.setStyleStrategy(QFont.PreferAntialias)
        app.setFont(app_font)

        # ── Backup service ────────────────────────────────────────
        splash.set_message("Setting up backup…")
        app.processEvents()
        from app.services.backup_service import backup_service
        backup_service.initialize(str(paths["db"]), str(paths["backup"]))

        # ── Seed example data (first run) ─────────────────────────
        splash.set_message("Loading your data…")
        app.processEvents()
        _seed_example_data_if_empty()

        # ── Main window ───────────────────────────────────────────
        splash.set_message("Launching NoteFlow…")
        app.processEvents()
        from app.views.main_window import MainWindow
        window = MainWindow()

        # Close splash and show window after a brief pause
        def _launch():
            splash.finish(window)
            window.show()

        QTimer.singleShot(600, _launch)

    except Exception as e:
        logger.critical(f"Startup failed: {e}", exc_info=True)
        splash.hide()
        QMessageBox.critical(
            None, "Startup Error",
            f"NoteFlow failed to start:\n\n{e}\n\nSee logs at:\n{paths['logs']}"
        )
        return 1

    exit_code = app.exec()
    logger.info(f"NoteFlow exited with code {exit_code}")
    return exit_code


# ──────────────────────────────────────────────────────────────────
# EXAMPLE DATA SEEDING
# ──────────────────────────────────────────────────────────────────

def _seed_example_data_if_empty():
    """
    Insert sample notes and tasks on first run.
    Checks if any notes exist before inserting.
    """
    from app.database.connection import db
    count = db.fetchone("SELECT COUNT(*) AS c FROM notes")["c"]
    if count > 0:
        return  # Already has data

    from app.services.note_service import note_service
    from app.services.task_service import task_service
    from datetime import datetime, timedelta

    # Sample notes
    welcome = note_service.create_note(
        title="👋 Welcome to NoteFlow!", folder_id=1
    )
    note_service.update_note(welcome.id, content="""# Welcome to NoteFlow! ✦

NoteFlow is your offline-first notes and tasks hub.

## Quick Start

- Press **Ctrl+N** to create a new note
- Press **Ctrl+T** to create a new task
- Press **Ctrl+Space** for quick-add
- Press **Ctrl+F** to search

## Features

- 📝 **Rich markdown notes** with auto-save
- ✅ **Full task management** with subtasks and due dates
- 🗂️ **Kanban board** for visual project tracking
- 🍅 **Pomodoro timer** for focused work sessions
- 🌙 **Dark and light themes** with accent colors
- 💾 **Automatic backups** to keep your data safe

## Markdown Support

You can use **bold**, *italic*, `inline code`, and much more!

```python
# Even code blocks work
def hello():
    return "Hello, NoteFlow!"
```

> Blockquotes look great too.

---

Start writing — your notes auto-save every few seconds.
""", is_pinned=True)

    md_note = note_service.create_note(title="📋 Markdown Cheatsheet", folder_id=1)
    note_service.update_note(md_note.id, content="""# Markdown Cheatsheet

## Headings
# H1  ## H2  ### H3

## Emphasis
**Bold text**  *Italic text*  ~~Strikethrough~~

## Lists
- Unordered item
- Another item
  - Nested item

1. Ordered item
2. Second item

## Tasks
- [ ] Unchecked task
- [x] Completed task

## Code
`inline code`

```python
code block
```

## Links & Images
[Link text](https://example.com)
![Alt text](image.png)

## Blockquote
> This is a quote

## Table
| Column 1 | Column 2 |
|----------|----------|
| Cell 1   | Cell 2   |
""")

    idea_note = note_service.create_note(title="💡 Project Ideas", folder_id=3)
    note_service.update_note(idea_note.id, content="""# Project Ideas

## App Ideas
- [ ] Personal finance tracker
- [ ] Recipe manager with meal planner
- [ ] Habit tracker with streaks
- [ ] Reading list manager

## Work Ideas
- Research new frameworks
- Improve CI/CD pipeline
- Write technical documentation

## Learning Goals
- Master async Python
- Learn Rust basics
- Improve SQL skills
""", color_label="yellow")

    note_service.add_tag_to_note(welcome.id, "welcome")
    note_service.add_tag_to_note(idea_note.id, "ideas")
    note_service.add_tag_to_note(idea_note.id, "projects")

    # Sample tasks
    now = datetime.now()
    tasks_data = [
        {
            "title": "Review NoteFlow documentation",
            "project_id": 1,
            "priority": 3,
            "due_date": now + timedelta(days=1),
        },
        {
            "title": "Set up daily task review habit",
            "project_id": 1,
            "priority": 2,
            "due_date": now,
        },
        {
            "title": "Explore Kanban board",
            "project_id": 2,
            "priority": 3,
            "due_date": now + timedelta(days=2),
        },
        {
            "title": "Try the Pomodoro timer",
            "project_id": 1,
            "priority": 3,
            "due_date": now + timedelta(days=3),
        },
        {
            "title": "Configure your preferred theme",
            "project_id": 1,
            "priority": 4,
        },
    ]
    for td in tasks_data:
        task_service.create_task(**td)


# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.exit(main())
