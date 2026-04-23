"""
Telegram Admin Service für ExecQueue.

Verwaltet Benutzer-Berechtigungen und System-Statistiken.
"""

import logging
from typing import Optional, Dict, Any, List
from sqlmodel import Session, select, func

from execqueue.db.session import get_session
from execqueue.models.telegram_user import TelegramUser
from execqueue.models.task import Task
from execqueue.models.requirement import Requirement

logger = logging.getLogger(__name__)


class TelegramAdminService:
    """Service fuer Admin-Funktionen im Telegram-Bot."""
    
    def __init__(self, session: Optional[Session] = None):
        self.session = session or get_session()
    
    def list_all_users(self) -> List[TelegramUser]:
        """Listet alle Telegram-Benutzer."""
        with self.session as sess:
            return sess.exec(
                select(TelegramUser).order_by(TelegramUser.created_at)
            ).all()
    
    def get_user_by_telegram_id(self, telegram_id: str) -> Optional[TelegramUser]:
        """Ermittelt Benutzer nach Telegram-ID."""
        with self.session as sess:
            return sess.exec(
                select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
            ).first()
    
    def grant_admin_role(self, telegram_id: str) -> TelegramUser:
        """Verleiht einem Benutzer Admin-Rolle."""
        with self.session as sess:
            user = sess.exec(
                select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
            ).first()
            
            if not user:
                # Benutzer nicht gefunden - erstellen
                user = TelegramUser(
                    telegram_id=telegram_id,
                    role="admin",
                    username=None,
                    is_test=False
                )
                logger.info(f"Created new admin user: {telegram_id}")
            else:
                old_role = user.role
                user.role = "admin"
                logger.info(f"Upgraded user {telegram_id} from {old_role} to admin")
            
            sess.add(user)
            sess.commit()
            sess.refresh(user)
            return user
    
    def revoke_admin_role(self, telegram_id: str) -> bool:
        """Entzieht einem Benutzer Admin-Rolle."""
        with self.session as sess:
            user = sess.exec(
                select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
            ).first()
            
            if not user:
                logger.warning(f"Cannot revoke admin: user {telegram_id} not found")
                return False
            
            if user.role != "admin":
                logger.warning(f"Cannot revoke admin: user {telegram_id} is not admin")
                return False
            
            user.role = "operator"
            logger.info(f"Revoked admin role from {telegram_id}")
            
            sess.add(user)
            sess.commit()
            return True
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Ermittelt System-Statistiken."""
        with self.session as sess:
            task_count = sess.exec(select(func.count()).select_from(Task)).one()
            requirement_count = sess.exec(
                select(func.count()).select_from(Requirement)
            ).one()
            user_count = sess.exec(
                select(func.count()).select_from(TelegramUser)
            ).one()
            admin_count = sess.exec(
                select(func.count()).select_from(TelegramUser)
                .where(TelegramUser.role == "admin")
            ).one()
            
            return {
                "tasks": task_count,
                "requirements": requirement_count,
                "telegram_users": user_count,
                "admin_users": admin_count,
            }
    
    def get_user_stats(self) -> Dict[str, int]:
        """Ermittelt Benutzer-Statistiken nach Rolle."""
        with self.session as sess:
            observer_count = sess.exec(
                select(func.count()).select_from(TelegramUser)
                .where(TelegramUser.role == "observer")
            ).one()
            
            operator_count = sess.exec(
                select(func.count()).select_from(TelegramUser)
                .where(TelegramUser.role == "operator")
            ).one()
            
            admin_count = sess.exec(
                select(func.count()).select_from(TelegramUser)
                .where(TelegramUser.role == "admin")
            ).one()
            
            return {
                "observers": observer_count,
                "operators": operator_count,
                "admins": admin_count,
            }
    
    def format_user_list(self, users: List[TelegramUser]) -> str:
        """Formatiert Benutzer-Liste für Telegram."""
        if not users:
            return "👥 *Keine Benutzer registriert.*"
        
        lines = ["👥 *Alle Telegram-Benutzer:*\n"]
        
        for i, user in enumerate(users, 1):
            role_emoji = {
                "observer": "👁️",
                "operator": "⚙️",
                "admin": "🔴"
            }.get(user.role, "❓")
            
            name = user.username or user.first_name or f"User {user.telegram_id}"
            status = "✅" if user.is_active else "❌"
            
            lines.append(f"{i}. {role_emoji} {name} ({user.role}) {status}")
        
        return "\n".join(lines)
    
    def format_stats(self, stats: Dict[str, Any]) -> str:
        """Formatiert Statistiken für Telegram."""
        lines = [
            "📊 *System-Statistiken:*",
            "",
            f"📋 Tasks: {stats.get('tasks', 0)}",
            f"📄 Requirements: {stats.get('requirements', 0)}",
            f"👥 Telegram Benutzer: {stats.get('telegram_users', 0)}",
            f"  ├─ Observer: {self.get_user_stats().get('observers', 0)}",
            f"  ├─ Operator: {self.get_user_stats().get('operators', 0)}",
            f"  └─ Admin: {stats.get('admin_users', 0)}",
        ]
        
        return "\n".join(lines)


def log_admin_action(
    user_id: str,
    action: str,
    target_user_id: Optional[str] = None,
    success: bool = True
):
    """Loggt Admin-Aktion für Audit-Trail."""
    message = f"AUDIT: User {user_id} performed {action}"
    if target_user_id:
        message += f" on target {target_user_id}"
    if not success:
        message += " [FAILED]"
    
    logger.warning(message)
