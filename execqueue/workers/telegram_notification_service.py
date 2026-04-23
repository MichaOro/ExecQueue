"""
Telegram Notification Service für ExecQueue.

Verwaltet Benachrichtigungen bei Task-Events und Scheduler-Statusänderungen.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlmodel import Session, select

from telegram import Bot
from execqueue.db.session import get_session
from execqueue.models.telegram_user import TelegramUser
from execqueue.models.telegram_notification import TelegramNotification

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TelegramNotificationService:
    """Service für Versendung von Telegram-Benachrichtigungen."""
    
    def __init__(self, bot: Optional[Bot] = None):
        self.bot = bot
    
    async def send_notification(
        self,
        user_telegram_id: str,
        event_type: str,
        message: str,
        task_id: Optional[int] = None
    ):
        """Sendet Benachrichtigung an Benutzer."""
        with get_session() as session:
            # Prüfe ob Benutzer Event abonniert hat
            user = session.exec(
                select(TelegramUser).where(TelegramUser.telegram_id == user_telegram_id)
            ).first()
            
            if not user or not user.is_active:
                logger.debug(f"User {user_telegram_id} not found or inactive")
                return
            
            subscriptions = json.loads(user.subscribed_events or "{}")
            if not subscriptions.get(event_type):
                logger.debug(f"User {user_telegram_id} not subscribed to {event_type}")
                return
            
            # Wenn Bot verfügbar, direkt senden
            if self.bot:
                try:
                    await self.bot.send_message(
                        chat_id=user_telegram_id,
                        text=message,
                        parse_mode="Markdown"
                    )
                    logger.info(f"Notification sent to {user_telegram_id}: {event_type}")
                except Exception as e:
                    logger.error(f"Failed to send notification to {user_telegram_id}: {e}")
                    # Fallback: In DB speichern
                    await self._save_notification(
                        session, user_telegram_id, event_type, message, task_id
                    )
            else:
                # Kein Bot: Nur in DB speichern
                await self._save_notification(
                    session, user_telegram_id, event_type, message, task_id
                )
    
    async def _save_notification(
        self,
        session: Session,
        user_telegram_id: str,
        event_type: str,
        message: str,
        task_id: Optional[int] = None
    ):
        """Speichert Notification in DB für späteren Versende-Versuch."""
        notification = TelegramNotification(
            user_telegram_id=user_telegram_id,
            event_type=event_type,
            message=message,
            task_id=task_id,
            is_read=False,
            sent_at=None,
            is_test=False
        )
        session.add(notification)
        session.commit()
        logger.info(f"Notification saved in DB for {user_telegram_id}: {event_type}")
    
    async def notify_task_completed(self, task: Dict[str, Any]):
        """Benachrichtigt alle Abonnenten über Task-Abschluss."""
        message = (
            f"✅ *Task #{task.get('id')} abgeschlossen*\n\n"
            f"*Titel:* {task.get('title', 'Ohne Titel')}\n"
            f"*Summary:* {task.get('validation_summary', 'N/A')[:100]}"
        )
        
        # Hole alle abonnierten Benutzer
        await self._notify_subscribers("task_completed", message, task.get("id"))
    
    async def notify_validation_failed(self, task: Dict[str, Any]):
        """Benachrichtigt über Validierungsfehler."""
        message = (
            f"⚠️ *Task #{task.get('id')} - Validierung fehlgeschlagen*\n\n"
            f"*Titel:* {task.get('title', 'Ohne Titel')}\n"
            f"*Retry:* {task.get('retry_count', 0)}/{task.get('max_retries', 5)}"
        )
        
        await self._notify_subscribers("validation_failed", message, task.get("id"))
    
    async def notify_retry_exhausted(self, task: Dict[str, Any]):
        """Benachrichtigt über erschöpftes Retry-Limit."""
        message = (
            f"🚨 *Task #{task.get('id')} - Retry-Limit erreicht*\n\n"
            f"*Titel:* {task.get('title', 'Ohne Titel')}\n"
            f"Manuelle Intervention erforderlich."
        )
        
        # Admins erhalten immer diese Notification
        await self._notify_admins("retry_exhausted", message, task.get("id"))
    
    async def notify_scheduler_started(self):
        """Benachrichtigt Admins über Scheduler-Start."""
        message = "▶️ *Scheduler gestartet*"
        await self._notify_admins("scheduler_started", message)
    
    async def notify_scheduler_stopped(self):
        """Benachrichtigt Admins über Scheduler-Stop."""
        message = "⏹️ *Scheduler gestoppt*"
        await self._notify_admins("scheduler_stopped", message)
    
    async def _notify_subscribers(
        self,
        event_type: str,
        message: str,
        task_id: Optional[int] = None
    ):
        """Sendet Notification an alle abonnierten Benutzer."""
        with get_session() as session:
            subscribers = session.exec(
                select(TelegramUser).where(
                    TelegramUser.is_active == True
                )
            ).all()
            
            for user in subscribers:
                subscriptions = json.loads(user.subscribed_events or "{}")
                if subscriptions.get(event_type):
                    await self.send_notification(
                        user_telegram_id=user.telegram_id,
                        event_type=event_type,
                        message=message,
                        task_id=task_id
                    )
    
    async def _notify_admins(
        self,
        event_type: str,
        message: str,
        task_id: Optional[int] = None
    ):
        """Sendet Notification nur an Admin-Benutzer."""
        admin_ids = self._get_admin_user_ids()
        
        for admin_id in admin_ids:
            await self.send_notification(
                user_telegram_id=admin_id,
                event_type=event_type,
                message=message,
                task_id=task_id
            )
    
    def _get_admin_user_ids(self) -> set[str]:
        """Ermittelt alle Admin-User-IDs (DB + Environment)."""
        admin_ids = set()
        
        # Von Environment
        env_admins = os.getenv("TELEGRAM_ADMIN_USER_IDS", "")
        if env_admins:
            admin_ids.update(id.strip() for id in env_admins.split(",") if id.strip())
        
        # Von Datenbank
        with get_session() as session:
            db_admins = session.exec(
                select(TelegramUser.telegram_id).where(
                    TelegramUser.role == "admin",
                    TelegramUser.is_active == True
                )
            ).all()
            admin_ids.update(db_admins)
        
        return admin_ids
    
    async def retry_pending_notifications(self, limit: int = 100):
        """Versendet gespeicherte Notifications bei verfügbarer API."""
        if not self.bot:
            logger.warning("Bot not available, cannot retry notifications")
            return
        
        with get_session() as session:
            pending = session.exec(
                select(TelegramNotification)
                .where(TelegramNotification.sent_at == None)
                .order_by(TelegramNotification.created_at)
                .limit(limit)
            ).all()
            
            for notification in pending:
                try:
                    await self.bot.send_message(
                        chat_id=notification.user_telegram_id,
                        text=notification.message,
                        parse_mode="Markdown"
                    )
                    
                    notification.sent_at = utcnow()
                    notification.is_read = True
                    session.add(notification)
                    logger.info(f"Retried notification {notification.id}")
                    
                except Exception as e:
                    logger.error(f"Failed to retry notification {notification.id}: {e}")
            
            session.commit()


async def create_notification_service() -> TelegramNotificationService:
    """Factory-Funktion zur Erzeugung des Notification-Services."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    bot = None
    
    if bot_token:
        bot = Bot(token=bot_token)
    
    return TelegramNotificationService(bot=bot)
