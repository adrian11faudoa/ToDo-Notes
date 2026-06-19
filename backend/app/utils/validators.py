"""
utils/validators.py
───────────────────
Reusable validation helpers used by services and routes.
"""

from __future__ import annotations
import re
import uuid


# Valid colour label names accepted by the API
VALID_COLOR_LABELS = frozenset({
    "red", "orange", "yellow", "green",
    "teal", "blue", "purple", "pink",
})

# Valid Kanban column names
VALID_KANBAN_COLUMNS = frozenset({
    "todo", "in_progress", "done", "cancelled"
})

# Valid task status values
VALID_TASK_STATUSES = frozenset({
    "todo", "in_progress", "done", "cancelled"
})

# Valid recurrence rules
VALID_RECURRENCE_RULES = frozenset({
    "daily", "weekly", "monthly", "yearly"
})

# Valid export formats
VALID_EXPORT_FORMATS = frozenset({"txt", "md", "pdf"})


def is_valid_uuid(value: str) -> bool:
    """Return True if value is a valid UUID string."""
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


def is_valid_color_label(value: str | None) -> bool:
    if value is None:
        return True
    return value.lower() in VALID_COLOR_LABELS


def is_valid_hex_color(value: str) -> bool:
    """Return True for strings like #RRGGBB or #RGB."""
    return bool(re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", value))


def sanitise_tag_name(name: str) -> str:
    """Lowercase, strip whitespace and special chars from tag names."""
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9_\-]", "", name)
    return name[:100]


def sanitise_filename(filename: str) -> str:
    """Strip directory traversal and dangerous characters from filenames."""
    # Remove path separators
    filename = re.sub(r"[/\\]", "_", filename)
    # Remove null bytes
    filename = filename.replace("\x00", "")
    # Limit length
    if len(filename) > 255:
        ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
        base = filename[: 250 - len(ext)]
        filename = f"{base}.{ext}" if ext else base
    return filename
