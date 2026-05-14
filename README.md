# ✦ NoteFlow

**A modern, offline-first Notes + To-Do application for Windows**

Built with Python, PySide6 (Qt), and SQLite — inspired by Notion, Obsidian, and TickTick.

---

## ✨ Features

### Notes System
- ✅ Rich Markdown editor with live formatting toolbar
- ✅ Auto-save every 3 seconds (configurable)
- ✅ Folders / categories with color labels
- ✅ Tags with color coding
- ✅ Pin favorite notes
- ✅ Instant full-text search (FTS5)
- ✅ Note previews in list view
- ✅ Word count & character count
- ✅ Last-edited timestamp
- ✅ Color labels (8 colors)
- ✅ Image & file attachments
- ✅ Export to TXT, Markdown, PDF
- ✅ Archive & Trash with restore

### To-Do System
- ✅ Task creation with priorities (Urgent / High / Medium / Low)
- ✅ Subtasks with progress bar
- ✅ Due dates with overdue detection
- ✅ Recurring tasks (daily / weekly / monthly / yearly)
- ✅ Projects / categories
- ✅ Completion tracking
- ✅ Kanban board (drag & drop between columns)
- ✅ Daily planner (Today view)
- ✅ Task tags and search
- ✅ System tray reminder notifications

### UI/UX
- ✅ Dark mode + Light mode
- ✅ 8 accent color options
- ✅ Sidebar navigation with folder/project/tag tree
- ✅ Split-pane layout (resizable)
- ✅ Top toolbar with global search
- ✅ Keyboard shortcuts for everything
- ✅ Right-click context menus
- ✅ System tray with minimize-to-tray
- ✅ Startup splash screen
- ✅ Quick-add popup (Ctrl+Space)
- ✅ Focus mode (F11)

### Pomodoro Timer
- ✅ Animated circular progress ring
- ✅ Work / Short Break / Long Break sessions
- ✅ Session cycle tracking
- ✅ System notifications on completion
- ✅ Link timer to active tasks

### Technical
- ✅ SQLite with WAL mode (fast concurrent reads)
- ✅ Full-text search via FTS5
- ✅ Modular MVVM-style architecture
- ✅ Theme engine with token system
- ✅ Centralized settings manager
- ✅ Automatic backup with 7-day rotation
- ✅ Crash handler with log files
- ✅ Window state persistence
- ✅ High-DPI support (Windows 10/11)

---

## 🗂️ Project Structure

```
NoteFlow/
├── main.py                     # Entry point
├── requirements.txt
├── noteflow.spec               # PyInstaller spec
├── app/
│   ├── assets/                 # Icons, fonts, images
│   ├── config/
│   │   └── settings_manager.py # Centralized settings
│   ├── database/
│   │   ├── schema.sql          # Full SQLite schema
│   │   └── connection.py       # Thread-safe DB manager
│   ├── models/
│   │   └── entities.py         # Dataclasses (Note, Task, etc.)
│   ├── services/
│   │   ├── note_service.py     # Notes business logic
│   │   ├── task_service.py     # Tasks business logic
│   │   ├── notification_service.py
│   │   └── backup_service.py
│   ├── themes/
│   │   └── theme_manager.py    # Full stylesheet generator
│   ├── views/
│   │   ├── main_window.py      # Main window & navigation
│   │   ├── notes_view.py       # Note list + editor
│   │   ├── tasks_view.py       # List / Kanban / Today
│   │   ├── pomodoro_view.py    # Pomodoro timer
│   │   └── settings_view.py    # Settings panel
│   └── widgets/
│       ├── common.py           # Reusable widgets
│       ├── sidebar.py          # Navigation sidebar
│       ├── splash_screen.py    # Startup splash
│       └── quick_add.py        # Quick-add popup
└── docs/
```

---

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.11 or 3.12
- Windows 10/11 (also works on macOS/Linux with minor adjustments)

### 2. Install dependencies

```bash
cd NoteFlow
pip install -r requirements.txt
```

### 3. Run the application

```bash
python main.py
```

---

## ⌨️ Keyboard Shortcuts

| Action              | Shortcut         |
|---------------------|------------------|
| New Note            | `Ctrl+N`         |
| New Task            | `Ctrl+T`         |
| Search              | `Ctrl+F`         |
| Quick Add Popup     | `Ctrl+Space`     |
| Bold                | `Ctrl+B`         |
| Italic              | `Ctrl+I`         |
| Toggle Sidebar      | `Ctrl+\`         |
| Focus Mode          | `F11`            |
| Toggle Theme        | `Ctrl+Shift+T`   |
| Go to Notes         | `Ctrl+1`         |
| Go to Tasks         | `Ctrl+2`         |
| Go to Today         | `Ctrl+3`         |
| Go to Kanban        | `Ctrl+4`         |
| Go to Pomodoro      | `Ctrl+5`         |

---

## 📦 Building the Windows Executable

### Install PyInstaller

```bash
pip install pyinstaller
```

### Build (single-folder, recommended)

```bash
pyinstaller noteflow.spec
```

The output is in `dist/NoteFlow/NoteFlow.exe`.

### One-file build (slower startup, but single .exe)

```bash
pyinstaller \
  --onefile \
  --windowed \
  --name NoteFlow \
  --add-data "app/database/schema.sql;app/database" \
  main.py
```

### Creating a Windows Installer (optional)

Use [Inno Setup](https://jrsoftware.org/isinfo.php) with the output of the `--onedir` build:

1. Download and install Inno Setup
2. Point it at `dist/NoteFlow/`
3. Set the main executable to `NoteFlow.exe`
4. Generate the installer script and compile

---

## 🗄️ Database

The SQLite database is stored at:

| Platform | Location |
|----------|----------|
| Windows  | `%APPDATA%\NoteFlow\noteflow.db` |
| macOS    | `~/Library/Application Support/NoteFlow/noteflow.db` |
| Linux    | `~/.local/share/NoteFlow/noteflow.db` |

Automatic backups are stored in the `backups/` subdirectory (7-day rotation).

---

## 🏗️ Architecture

NoteFlow follows a **layered architecture**:

```
Views (UI)
   ↓
Services (Business Logic)        ← All business rules here
   ↓
Database Manager (Data Access)   ← Single source of truth for SQL
   ↓
SQLite (Storage)
```

Key design decisions:
- **Services are singletons** — one instance per service, no re-instantiation
- **Views never touch the DB directly** — always go through services
- **Models are pure dataclasses** — no methods that touch the DB
- **Theme tokens** — all colors are named tokens, never hardcoded in widgets
- **Thread-local connections** — each thread gets its own SQLite connection

---

## 🔌 Extending NoteFlow

### Adding a new view

1. Create `app/views/my_view.py` with a `QWidget` subclass
2. Add it to `QStackedWidget` in `main_window.py`
3. Add a `NavButton` to the sidebar
4. Wire the navigation signal

### Adding a new service

1. Create `app/services/my_service.py` as a singleton
2. Import and use in views

### Changing the theme

Edit `app/themes/theme_manager.py`:
- Add tokens to `DARK_TOKENS` / `LIGHT_TOKENS`
- Use `theme.t("my_token")` in any widget

---

## 📋 Requirements

```
PySide6>=6.6.0
markdown2>=2.4.10
Pillow>=10.0.0
reportlab>=4.0.0
python-dateutil>=2.8.2
plyer>=2.1.0
pyinstaller>=6.0.0
```

---

## 📄 License

MIT License — free to use, modify, and distribute.
