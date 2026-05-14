"""
services/backup_service.py
──────────────────────────
Automated backup system with rotation. Keeps last 7 daily backups.
"""
from __future__ import annotations
import logging
import shutil
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class BackupService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._db_path = ""
            cls._instance._backup_dir = Path()
        return cls._instance

    def initialize(self, db_path: str, backup_dir: str):
        self._db_path = db_path
        self._backup_dir = Path(backup_dir)
        self._backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = self._backup_dir / f"noteflow_backup_{ts}.db"
        from app.database.connection import db
        db.backup(str(dest))
        self._rotate_backups(keep=7)
        logger.info(f"Backup created: {dest}")
        return str(dest)

    def _rotate_backups(self, keep: int = 7):
        backups = sorted(
            self._backup_dir.glob("noteflow_backup_*.db"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        for old in backups[keep:]:
            try:
                old.unlink()
            except Exception as e:
                logger.warning(f"Could not remove {old}: {e}")

    def list_backups(self) -> list[Path]:
        return sorted(
            self._backup_dir.glob("noteflow_backup_*.db"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )

    def restore_backup(self, backup_path: str):
        shutil.copy2(backup_path, self._db_path)
        logger.info(f"Restored backup from {backup_path}")


backup_service = BackupService()
