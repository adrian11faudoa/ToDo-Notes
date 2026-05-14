"""
services/notification_service.py
──────────────────────────────────
Handles system tray notifications and task reminders.
Uses plyer for cross-platform notifications with Windows toast support.
Polls for due reminders every minute via a QTimer.
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QTimer, QObject, Signal
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PySide6.QtGui import QIcon, QAction

from app.database.connection import db

logger = logging.getLogger(__name__)


class NotificationService(QObject):
    """
    Manages system tray icon and desktop notifications.
    Also polls the DB for due reminders every 60 seconds.
    """

    reminder_due = Signal(int, str)  # task_id, title

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tray: Optional[QSystemTrayIcon] = None
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._check_reminders)
        self._notified_ids: set[int] = set()

    def setup_tray(self, main_window, icon_path: Optional[str] = None):
        """Initialize the system tray icon."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray not available")
            return

        self._tray = QSystemTrayIcon(main_window)

        if icon_path:
            self._tray.setIcon(QIcon(icon_path))
        else:
            # Use a colored fallback icon
            from PySide6.QtGui import QPixmap, QPainter, QColor, QBrush
            px = QPixmap(32, 32)
            px.fill(QColor("#4A9EFF"))
            self._tray.setIcon(QIcon(px))

        self._tray.setToolTip("NoteFlow")

        # Context menu
        menu = QMenu()
        show_action = QAction("Show NoteFlow", menu)
        show_action.triggered.connect(main_window.show)
        show_action.triggered.connect(main_window.raise_)

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(QApplication.instance().quit)

        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

        # Store reference to main window
        self._main_window = main_window

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            if hasattr(self, "_main_window"):
                self._main_window.show()
                self._main_window.raise_()
                self._main_window.activateWindow()

    def start_polling(self, interval_ms: int = 60_000):
        self._poll_timer.start(interval_ms)
        # Check immediately
        self._check_reminders()

    def stop_polling(self):
        self._poll_timer.stop()

    def _check_reminders(self):
        """Query DB for tasks whose reminder_at is now past and not yet notified."""
        try:
            now = datetime.now().isoformat()
            rows = db.fetchall(
                """SELECT id, title FROM tasks
                   WHERE reminder_at <= ? AND reminder_at IS NOT NULL
                   AND status NOT IN ('done','cancelled')""",
                (now,),
            )
            for row in rows:
                task_id = row["id"]
                if task_id not in self._notified_ids:
                    self._notified_ids.add(task_id)
                    self.reminder_due.emit(task_id, row["title"])
                    self.show_notification(
                        "Task Reminder",
                        f"⏰ {row['title']}",
                        notification_type="reminder",
                    )
                    # Clear reminder so it doesn't fire again
                    with db.transaction() as conn:
                        conn.execute(
                            "UPDATE tasks SET reminder_at=NULL WHERE id=?", (task_id,)
                        )
        except Exception as e:
            logger.error(f"Reminder polling error: {e}")

    def show_notification(
        self,
        title: str,
        message: str,
        notification_type: str = "info",
        duration: int = 5,
    ):
        """Show a desktop notification."""
        # Try plyer first (system notifications)
        try:
            from plyer import notification
            icon_map = {
                "info": "",
                "reminder": "⏰",
                "success": "✅",
                "warning": "⚠️",
            }
            notification.notify(
                title=title,
                message=message,
                app_name="NoteFlow",
                timeout=duration,
            )
            return
        except Exception:
            pass

        # Fallback to Qt tray balloon
        if self._tray and self._tray.isVisible():
            icon_map_qt = {
                "info": QSystemTrayIcon.MessageIcon.Information,
                "reminder": QSystemTrayIcon.MessageIcon.Warning,
                "success": QSystemTrayIcon.MessageIcon.Information,
                "warning": QSystemTrayIcon.MessageIcon.Warning,
            }
            self._tray.showMessage(
                title,
                message,
                icon_map_qt.get(notification_type, QSystemTrayIcon.MessageIcon.Information),
                duration * 1000,
            )

    def update_tray_tooltip(self, text: str):
        if self._tray:
            self._tray.setToolTip(f"NoteFlow — {text}")

    def hide_tray(self):
        if self._tray:
            self._tray.hide()


notification_service = NotificationService()
