"""
config/settings_manager.py
──────────────────────────
Centralized settings management.
Reads/writes to the SQLite settings table.
Also manages a JSON config file for non-DB preferences.
"""

from __future__ import annotations
import json
import os
import logging
from pathlib import Path
from typing import Any

from app.database.connection import db
from app.models.entities import AppSettings

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(os.getenv("APPDATA", Path.home())) / "NoteFlow"
CONFIG_FILE = CONFIG_DIR / "config.json"


class SettingsManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache: dict[str, str] = {}
            cls._instance._initialized = False
        return cls._instance

    def initialize(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._load_from_db()
        self._initialized = True

    def _load_from_db(self):
        try:
            rows = db.fetchall("SELECT key, value FROM settings")
            self._cache = {r["key"]: r["value"] for r in rows}
        except Exception as e:
            logger.warning(f"Could not load settings from DB: {e}")
            self._cache = {}

    def get(self, key: str, default: Any = None) -> str | None:
        return self._cache.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self._cache.get(key, default))
        except (ValueError, TypeError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        val = self._cache.get(key, "1" if default else "0")
        return val in ("1", "true", "True", "yes")

    def set(self, key: str, value: Any):
        str_val = str(value)
        self._cache[key] = str_val
        try:
            with db.transaction() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (key, str_val)
                )
        except Exception as e:
            logger.error(f"Failed to save setting {key}: {e}")

    def set_many(self, updates: dict[str, Any]):
        for k, v in updates.items():
            self._cache[k] = str(v)
        try:
            with db.transaction() as conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    [(k, str(v)) for k, v in updates.items()]
                )
        except Exception as e:
            logger.error(f"Failed to save settings batch: {e}")

    def to_app_settings(self) -> AppSettings:
        return AppSettings(
            theme=self.get("theme", "dark"),
            accent_color=self.get("accent_color", "#4A9EFF"),
            font_size=self.get_int("font_size", 14),
            autosave_interval=self.get_int("autosave_interval", 3),
            language=self.get("language", "en"),
            pomodoro_work=self.get_int("pomodoro_work", 1500),
            pomodoro_short_break=self.get_int("pomodoro_short_break", 300),
            pomodoro_long_break=self.get_int("pomodoro_long_break", 900),
            startup_page=self.get("startup_page", "notes"),
            backup_enabled=self.get_bool("backup_enabled", True),
            backup_interval=self.get_int("backup_interval", 86400),
            show_word_count=self.get_bool("show_word_count", True),
            default_view=self.get("default_view", "list"),
        )

    def save_app_settings(self, s: AppSettings):
        self.set_many({
            "theme": s.theme,
            "accent_color": s.accent_color,
            "font_size": s.font_size,
            "autosave_interval": s.autosave_interval,
            "language": s.language,
            "pomodoro_work": s.pomodoro_work,
            "pomodoro_short_break": s.pomodoro_short_break,
            "pomodoro_long_break": s.pomodoro_long_break,
            "startup_page": s.startup_page,
            "backup_enabled": "1" if s.backup_enabled else "0",
            "backup_interval": s.backup_interval,
            "show_word_count": "1" if s.show_word_count else "0",
            "default_view": s.default_view,
        })


settings_manager = SettingsManager()
