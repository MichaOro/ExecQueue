"""
Telegram Bot Worker für ExecQueue Remote-Steuerung.

Ermöglicht die Steuerung von ExecQueue via Telegram-Bot mit Commands wie:
/start, /help, /queue, /status, /health, /create, /cancel, etc.
"""

import os
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from collections import defaultdict

from sqlmodel import Session, select
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from typing import Any

from execqueue.db.session import get_session
from execqueue.models.telegram_user import TelegramUser
from execqueue.models.task import Task
from execqueue.services.telegram_admin_service import TelegramAdminService, log_admin_action

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TelegramBotWorker:
    """Telegram Bot Worker für ExecQueue Remote-Steuerung."""
    
    def __init__(self):
        self.bot: Optional[Bot] = None
        self.application: Optional[Application] = None
        self.admin_user_ids: set[str] = set()
        self.rate_limits: Dict[str, List[datetime]] = defaultdict(list)
        self.rate_limit_per_minute = int(os.getenv("TELEGRAM_RATE_LIMIT_PER_MINUTE", "30"))
        self.api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api")
        
    async def start(self):
        """Startet den Bot (Polling-Modus)."""
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN nicht gesetzt - Bot startet nicht")
            return
        
        # Admin-User-IDs aus Environment laden
        admin_ids = os.getenv("TELEGRAM_ADMIN_USER_IDS", "")
        if admin_ids:
            self.admin_user_ids = set(id.strip() for id in admin_ids.split(",") if id.strip())
        
        # Bot initialisieren
        self.application = Application.builder().token(bot_token).build()
        
        # Command-Handler registrieren
        self._register_commands()
        
        # Bot starten
        logger.info("Telegram Bot startet im Polling-Modus...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Telegram Bot läuft")
        
        # Blockieren bis Stopp
        await self.application.idle()
    
    async def stop(self):
        """Stoppt den Bot graceful."""
        if self.application:
            logger.info("Telegram Bot stoppt...")
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            logger.info("Telegram Bot gestoppt")
    
    def _register_commands(self):
        """Registriert alle Command-Handler."""
        commands = [
            ("start", self.handle_start, "Bot-Start mit Begrüßung"),
            ("help", self.handle_help, "Zeige alle verfügbaren Commands"),
            ("queue", self.handle_queue, "Zeige aktuelle Task-Queue"),
            ("status", self.handle_status, "Detail-Status eines Tasks"),
            ("health", self.handle_health, "System-Status anzeigen"),
            ("tasks", self.handle_tasks, "Übersicht aller Tasks"),
            ("create", self.handle_create, "Neuen Task anlegen"),
            ("cancel", self.handle_cancel, "Task abbrechen"),
            ("retry", self.handle_retry, "Failed-Task erneut ausführen"),
            ("requirements", self.handle_requirements, "Liste aller Requirements"),
            ("subscribe", self.handle_subscribe, "Event abonnieren"),
            ("unsubscribe", self.handle_unsubscribe, "Event abbestellen"),
            ("notifications", self.handle_notifications, "Deine Subscriptions anzeigen"),
            ("start_scheduler", self.handle_start_scheduler, "Scheduler aktivieren (Admin)"),
            ("stop_scheduler", self.handle_stop_scheduler, "Scheduler deaktivieren (Admin)"),
            ("admin_users", self.handle_admin_users, "Liste aller Benutzer (Admin)"),
            ("admin_grant", self.handle_admin_grant, "Admin-Rolle vergeben (Admin)"),
            ("admin_revoke", self.handle_admin_revoke, "Admin-Rolle entziehen (Admin)"),
            ("admin_stats", self.handle_admin_stats, "System-Statistiken (Admin)"),
        ]
        
        for cmd, handler, description in commands:
            self.application.add_handler(CommandHandler(cmd, handler))
        
        logger.info(f"{len(commands)} Command-Handler registriert")
    
    def check_rate_limit(self, user_id: str) -> bool:
        """Prüft Rate-Limit für Benutzer (Sliding Window)."""
        now = utcnow()
        window_start = now - timedelta(minutes=1)
        
        # Alte Einträge entfernen
        self.rate_limits[user_id] = [
            ts for ts in self.rate_limits[user_id] if ts > window_start
        ]
        
        # Prüfen ob Limit erreicht
        if len(self.rate_limits[user_id]) >= self.rate_limit_per_minute:
            return False
        
        # Neuen Eintrag hinzufügen
        self.rate_limits[user_id].append(now)
        return True
    
    async def get_or_create_user(self, telegram_id: str, update_data: Dict) -> TelegramUser:
        """Erstellt oder aktualisiert TelegramUser in der Datenbank."""
        with get_session() as session:
            user = session.exec(
                select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
            ).first()
            
            if not user:
                user = TelegramUser(
                    telegram_id=telegram_id,
                    username=update_data.get("username"),
                    first_name=update_data.get("first_name"),
                    last_name=update_data.get("last_name"),
                    role="observer",  # Default-Rolle
                    is_test=False
                )
                session.add(user)
            else:
                # Daten aktualisieren
                if update_data.get("username"):
                    user.username = update_data["username"]
                if update_data.get("first_name"):
                    user.first_name = update_data["first_name"]
                if update_data.get("last_name"):
                    user.last_name = update_data["last_name"]
                user.last_active = utcnow()
                user.is_active = True
            
            session.commit()
            session.refresh(user)
            return user
    
    async def check_user_permission(self, user_id: str, required_role: str) -> bool:
        """Prüft ob Benutzer die erforderliche Rolle hat."""
        with get_session() as session:
            user = session.exec(
                select(TelegramUser).where(TelegramUser.telegram_id == user_id)
            ).first()
            
            if not user:
                return False
            
            # Rolle-Check
            role_hierarchy = {"observer": 0, "operator": 1, "admin": 2}
            user_level = role_hierarchy.get(user.role, 0)
            required_level = role_hierarchy.get(required_role, 0)
            
            return user_level >= required_level
    
    def format_task_list(self, tasks: List[Dict]) -> str:
        """Formatiert Task-Liste für Telegram."""
        if not tasks:
            return "❌ Keine Tasks in der Queue."
        
        lines = ["📋 *Aktuelle Task-Queue:*", ""]
        for task in tasks[:10]:  # Max 10
            status_emoji = {
                "queued": "⏳",
                "in_progress": "🔄",
                "validation": "🔍",
                "done": "✅",
                "failed": "❌",
                "retry": "🔁"
            }.get(task.get("status", "unknown"), "❓")
            
            title = task.get("title", "Ohne Titel")[:40]
            lines.append(f"{status_emoji} `#{task.get('id')}` - {title}")
            lines.append(f"   Status: {task.get('status')}, Priority: {task.get('execution_order', 0)}")
        
        if len(tasks) > 10:
            lines.append(f"\n... und {len(tasks) - 10} weitere")
        
        return "\n".join(lines)
    
    def format_task_detail(self, task: Dict) -> str:
        """Formatiert Task-Detail für Telegram."""
        status_emoji = {
            "queued": "⏳",
            "in_progress": "🔄",
            "validation": "🔍",
            "done": "✅",
            "failed": "❌",
            "retry": "🔁"
        }.get(task.get("status", "unknown"), "❓")
        
        lines = [
            f"{status_emoji} *Task #{task.get('id')}*",
            f"*Titel:* {task.get('title', 'Ohne Titel')}",
            f"*Status:* {task.get('status')}",
            f"*Priority:* {task.get('execution_order', 0)}",
            f"*Retry:* {task.get('retry_count', 0)}/{task.get('max_retries', 5)}",
            f"*Erstellt:* {task.get('created_at', 'N/A')}",
        ]
        
        if task.get("last_result"):
            result = task["last_result"][:200]
            if len(task["last_result"]) > 200:
                result += "..."
            lines.append(f"*Letztes Ergebnis:* {result}")
        
        return "\n".join(lines)
    
    async def call_api(self, endpoint: str, method: str = "GET", data: Dict = None) -> Dict:
        """Ruft ExecQueue API auf."""
        import httpx
        
        url = f"{self.api_base_url}/{endpoint}"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                if method == "GET":
                    response = await client.get(url, params=data)
                elif method == "POST":
                    response = await client.post(url, json=data)
                elif method == "PATCH":
                    response = await client.patch(url, json=data)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException:
                raise BotError("API nicht erreichbar (Timeout)")
            except httpx.HTTPStatusError as e:
                raise BotError(f"API-Fehler: {e.response.status_code}")
    
    # ==================== Command Handlers ====================
    
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/start - Bot-Start mit Begrüßung."""
        user_id = str(update.effective_user.id)
        user_data = {
            "username": update.effective_user.username,
            "first_name": update.effective_user.first_name,
            "last_name": update.effective_user.last_name,
        }
        
        await self.get_or_create_user(user_id, user_data)
        
        message = (
            "👋 *Willkommen bei ExecQueue Bot!*\n\n"
            "Ich steuere deine Task-Queue und Requirements.\n\n"
            "Verfügbare Commands:\n"
            "/help - Alle Commands anzeigen\n"
            "/queue - Aktuelle Task-Queue\n"
            "/status <id> - Task-Details\n"
            "/health - System-Status\n"
            "/create <prompt> - Neuer Task\n"
        )
        
        await update.message.reply_text(message, parse_mode="Markdown")
        logger.info(f"User {user_id} started the bot")
    
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/help - Zeige alle Commands."""
        user_id = str(update.effective_user.id)
        
        # Prüfe Rolle für Command-Liste
        is_admin = await self.check_user_permission(user_id, "admin")
        is_operator = await self.check_user_permission(user_id, "operator")
        
        commands = [
            "📖 *Verfügbare Commands:*\n",
            "🔹 *Allgemein:*\n",
            "  /start - Bot starten\n",
            "  /help - Diese Hilfe\n",
            "  /queue - Task-Queue (max 10)\n",
            "  /status <id> - Task-Details\n",
            "  /tasks - Alle Tasks\n",
            "  /health - System-Status\n",
            "  /requirements - Requirements\n",
            "  /subscribe <event> - Event abonnieren\n",
            "  /unsubscribe <event> - Abbestellen\n",
            "  /notifications - Meine Subscriptions\n",
        ]
        
        if is_operator:
            commands.extend([
                "\n🔸 *Operator:*\n",
                "  /create <prompt> - Neuer Task\n",
                "  /cancel <id> - Task abbrechen\n",
                "  /retry <id> - Retry Task\n",
            ])
        
        if is_admin:
            commands.extend([
                "\n🔴 *Admin:*\n",
                "  /start_scheduler - Scheduler starten\n",
                "  /stop_scheduler - Scheduler stoppen\n",
            ])
        
        await update.message.reply_text("\n".join(commands), parse_mode="Markdown")
        logger.info(f"User {user_id} requested help")
    
    async def handle_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/queue - Zeige aktuelle Task-Queue."""
        user_id = str(update.effective_user.id)
        
        if not self.check_rate_limit(user_id):
            await update.message.reply_text("❌ Rate-Limit erreicht. Warte eine Minute.")
            return
        
        try:
            tasks = await self.call_api("tasks")
            message = self.format_task_list(tasks)
            await update.message.reply_text(message, parse_mode="Markdown")
        except BotError as e:
            await update.message.reply_text(f"❌ Fehler: {e}")
        except Exception as e:
            logger.error(f"Error in /queue: {e}")
            await update.message.reply_text("❌ Service temporarily unavailable")
    
    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/status <task_id> - Detail-Status eines Tasks."""
        user_id = str(update.effective_user.id)
        
        if not self.check_rate_limit(user_id):
            await update.message.reply_text("❌ Rate-Limit erreicht.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Task-ID erforderlich.\nVerwendung: /status <task_id>"
            )
            return
        
        task_id = context.args[0]
        
        try:
            task = await self.call_api(f"tasks/{task_id}")
            message = self.format_task_detail(task)
            await update.message.reply_text(message, parse_mode="Markdown")
        except BotError as e:
            if "404" in str(e):
                await update.message.reply_text(f"❌ Task #{task_id} nicht gefunden")
            else:
                await update.message.reply_text(f"❌ Fehler: {e}")
        except Exception as e:
            logger.error(f"Error in /status: {e}")
            await update.message.reply_text("❌ Service temporarily unavailable")
    
    async def handle_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/health - System-Status."""
        user_id = str(update.effective_user.id)
        
        if not self.check_rate_limit(user_id):
            await update.message.reply_text("❌ Rate-Limit erreicht.")
            return
        
        try:
            health = await self.call_api("health")
            
            lines = [
                "🏥 *System-Status:*",
                "",
                f"✅ API: {health.get('status', 'unknown')}",
                f"🗄️ Database: {'✅' if health.get('database_connected') else '❌'}",
            ]
            
            scheduler = health.get("scheduler", {})
            lines.append(f"⚙️ Scheduler: {'✅' if scheduler.get('running') else '⏹️'}")
            
            if scheduler.get("running"):
                lines.append(f"   Workers: {scheduler.get('active_workers', 0)}")
            
            metrics = health.get("metrics", {})
            if metrics:
                lines.extend([
                    "",
                    "📊 *Metrics:*",
                    f"   Queued: {metrics.get('queued_tasks', 0)}",
                    f"   Running: {metrics.get('running_tasks', 0)}",
                    f"   Done: {metrics.get('completed_tasks', 0)}",
                ])
            
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error in /health: {e}")
            await update.message.reply_text("❌ Service temporarily unavailable")
    
    async def handle_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/tasks - Übersicht aller Tasks."""
        user_id = str(update.effective_user.id)
        
        if not self.check_rate_limit(user_id):
            await update.message.reply_text("❌ Rate-Limit erreicht.")
            return
        
        try:
            tasks = await self.call_api("tasks")
            
            # Gruppieren nach Status
            status_groups = defaultdict(list)
            for task in tasks:
                status_groups[task.get("status", "unknown")].append(task)
            
            lines = ["📋 *Alle Tasks:*\n"]
            for status, task_list in sorted(status_groups.items()):
                emoji = {
                    "queued": "⏳",
                    "in_progress": "🔄",
                    "done": "✅",
                    "failed": "❌"
                }.get(status, "❓")
                lines.append(f"{emoji} *{status}:* {len(task_list)}")
            
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error in /tasks: {e}")
            await update.message.reply_text("❌ Service temporarily unavailable")
    
    async def handle_create(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/create <prompt> - Neuer Task."""
        user_id = str(update.effective_user.id)
        
        # Rolle-Check
        if not await self.check_user_permission(user_id, "operator"):
            await update.message.reply_text("❌ Access denied. Operator-Rolle erforderlich.")
            return
        
        if not self.check_rate_limit(user_id):
            await update.message.reply_text("❌ Rate-Limit erreicht.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "❌ Prompt erforderlich.\nVerwendung: /create <dein prompt>"
            )
            return
        
        prompt = " ".join(context.args)
        
        try:
            task = await self.call_api("tasks", method="POST", data={
                "source_type": "telegram",
                "source_id": int(user_id),
                "title": prompt[:50],
                "prompt": prompt
            })
            
            await update.message.reply_text(
                f"✅ *Task erstellt!*\n\n"
                f"ID: #{task.get('id')}\n"
                f"Status: {task.get('status')}",
                parse_mode="Markdown"
            )
        except BotError as e:
            await update.message.reply_text(f"❌ Fehler: {e}")
        except Exception as e:
            logger.error(f"Error in /create: {e}")
            await update.message.reply_text("❌ Service temporarily unavailable")
    
    async def handle_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/cancel <task_id> - Task abbrechen."""
        user_id = str(update.effective_user.id)
        
        if not await self.check_user_permission(user_id, "operator"):
            await update.message.reply_text("❌ Access denied.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text("❌ Task-ID erforderlich.")
            return
        
        task_id = context.args[0]
        
        try:
            await self.call_api(f"tasks/{task_id}/cancel", method="PATCH")
            await update.message.reply_text(f"✅ Task #{task_id} wurde abgebrochen")
        except BotError as e:
            await update.message.reply_text(f"❌ Fehler: {e}")
        except Exception as e:
            logger.error(f"Error in /cancel: {e}")
            await update.message.reply_text("❌ Service temporarily unavailable")
    
    async def handle_retry(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/retry <task_id> - Failed-Task erneut ausführen."""
        user_id = str(update.effective_user.id)
        
        if not await self.check_user_permission(user_id, "operator"):
            await update.message.reply_text("❌ Access denied.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text("❌ Task-ID erforderlich.")
            return
        
        task_id = context.args[0]
        
        try:
            await self.call_api(f"tasks/{task_id}/retry", method="POST")
            await update.message.reply_text(f"✅ Task #{task_id} wurde neu in die Queue gestellt")
        except BotError as e:
            await update.message.reply_text(f"❌ Fehler: {e}")
        except Exception as e:
            logger.error(f"Error in /retry: {e}")
            await update.message.reply_text("❌ Service temporarily unavailable")
    
    async def handle_requirements(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/requirements - Liste aller Requirements."""
        user_id = str(update.effective_user.id)
        
        if not self.check_rate_limit(user_id):
            await update.message.reply_text("❌ Rate-Limit erreicht.")
            return
        
        try:
            requirements = await self.call_api("requirements")
            
            lines = ["📋 *Requirements:*\n"]
            for req in requirements[:10]:
                title = req.get("title", "Ohne Titel")[:40]
                status = req.get("status", "unknown")
                lines.append(f"📄 *{title}*")
                lines.append(f"   Status: {status}")
            
            if len(requirements) > 10:
                lines.append(f"\n... und {len(requirements) - 10} weitere")
            
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error in /requirements: {e}")
            await update.message.reply_text("❌ Service temporarily unavailable")
    
    async def handle_subscribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/subscribe <event> - Event abonnieren."""
        user_id = str(update.effective_user.id)
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Event-Typ erforderlich.\n"
                "Verfügbar: task_completed, validation_failed, retry_exhausted"
            )
            return
        
        event_type = context.args[0]
        valid_events = ["task_completed", "validation_failed", "retry_exhausted"]
        
        if event_type not in valid_events:
            await update.message.reply_text(
                f"❌ Ungültiger Event-Typ.\nVerfügbar: {', '.join(valid_events)}"
            )
            return
        
        with get_session() as session:
            user = session.exec(
                select(TelegramUser).where(TelegramUser.telegram_id == user_id)
            ).first()
            
            if not user:
                await update.message.reply_text("❌ Benutzer nicht gefunden. Nutze /start zuerst.")
                return
            
            import json
            subscriptions = json.loads(user.subscribed_events or "{}")
            subscriptions[event_type] = True
            user.subscribed_events = json.dumps(subscriptions)
            session.add(user)
            session.commit()
        
        await update.message.reply_text(f"✅ Du hast *{event_type}* abonniert", parse_mode="Markdown")
    
    async def handle_unsubscribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/unsubscribe <event> - Event abbestellen."""
        user_id = str(update.effective_user.id)
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text("❌ Event-Typ erforderlich.")
            return
        
        event_type = context.args[0]
        
        with get_session() as session:
            user = session.exec(
                select(TelegramUser).where(TelegramUser.telegram_id == user_id)
            ).first()
            
            if not user:
                await update.message.reply_text("❌ Benutzer nicht gefunden.")
                return
            
            import json
            subscriptions = json.loads(user.subscribed_events or "{}")
            subscriptions[event_type] = False
            user.subscribed_events = json.dumps(subscriptions)
            session.add(user)
            session.commit()
        
        await update.message.reply_text(f"✅ Du hast *{event_type}* abbestellt", parse_mode="Markdown")
    
    async def handle_notifications(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/notifications - Zeige aktuelle Subscriptions."""
        user_id = str(update.effective_user.id)
        
        with get_session() as session:
            user = session.exec(
                select(TelegramUser).where(TelegramUser.telegram_id == user_id)
            ).first()
            
            if not user:
                await update.message.reply_text("❌ Benutzer nicht gefunden.")
                return
            
            import json
            subscriptions = json.loads(user.subscribed_events or "{}")
            
            lines = ["🔔 *Deine Subscriptions:*\n"]
            for event in ["task_completed", "validation_failed", "retry_exhausted"]:
                status = "✅" if subscriptions.get(event) else "❌"
                lines.append(f"{status} {event}")
        
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    
    async def handle_start_scheduler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/start_scheduler - Scheduler aktivieren (Admin)."""
        user_id = str(update.effective_user.id)
        
        if not await self.check_user_permission(user_id, "admin"):
            await update.message.reply_text("❌ Access denied. Admin-Rolle erforderlich.")
            return
        
        try:
            result = await self.call_api("queue/start", method="POST")
            await update.message.reply_text(f"✅ Scheduler wurde gestartet")
        except Exception as e:
            logger.error(f"Error starting scheduler: {e}")
            await update.message.reply_text("❌ Fehler beim Starten des Scheduler")
    
    async def handle_stop_scheduler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/stop_scheduler - Scheduler deaktivieren (Admin)."""
        user_id = str(update.effective_user.id)
        
        if not await self.check_user_permission(user_id, "admin"):
            await update.message.reply_text("❌ Access denied.")
            return
        
        try:
            result = await self.call_api("queue/stop", method="POST")
            await update.message.reply_text(f"✅ Scheduler wurde gestoppt")
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")
            await update.message.reply_text("❌ Fehler beim Stoppen des Scheduler")
    
    async def handle_admin_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/admin_users - Liste aller Benutzer (Admin)."""
        user_id = str(update.effective_user.id)
        
        if not await self.check_user_permission(user_id, "admin"):
            await update.message.reply_text("❌ Access denied. Admin-Rolle erforderlich.")
            return
        
        try:
            service = TelegramAdminService()
            users = service.list_all_users()
            message = service.format_user_list(users)
            await update.message.reply_text(message, parse_mode="Markdown")
            log_admin_action(user_id, "admin_users", success=True)
        except Exception as e:
            logger.error(f"Error in admin_users: {e}")
            await update.message.reply_text("❌ Fehler beim Laden der Benutzer")
            log_admin_action(user_id, "admin_users", success=False)
    
    async def handle_admin_grant(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/admin_grant <telegram_id> - Admin-Rolle vergeben (Admin)."""
        user_id = str(update.effective_user.id)
        
        if not await self.check_user_permission(user_id, "admin"):
            await update.message.reply_text("❌ Access denied.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text("❌ Telegram-ID erforderlich.\nVerwendung: /admin_grant <telegram_id>")
            return
        
        target_id = context.args[0]
        
        # Schutz: Kann sich nicht selbst Rechte geben (ist schon Admin)
        if target_id == user_id:
            await update.message.reply_text("ℹ️ Du bist bereits Admin.")
            return
        
        try:
            service = TelegramAdminService()
            user = service.grant_admin_role(target_id)
            await update.message.reply_text(
                f"✅ Benutzer {target_id} ist jetzt *{user.role}*",
                parse_mode="Markdown"
            )
            log_admin_action(user_id, "grant_admin", target_id, True)
        except Exception as e:
            logger.error(f"Error in admin_grant: {e}")
            await update.message.reply_text(f"❌ Fehler: {e}")
            log_admin_action(user_id, "grant_admin", target_id, False)
    
    async def handle_admin_revoke(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/admin_revoke <telegram_id> - Admin-Rolle entziehen (Admin)."""
        user_id = str(update.effective_user.id)
        
        if not await self.check_user_permission(user_id, "admin"):
            await update.message.reply_text("❌ Access denied.")
            return
        
        if not context.args or len(context.args) < 1:
            await update.message.reply_text("❌ Telegram-ID erforderlich.")
            return
        
        target_id = context.args[0]
        
        # Schutz: Kann sich nicht selbst entziehen
        if target_id == user_id:
            await update.message.reply_text("❌ Du kannst dir deine eigenen Admin-Rechte nicht entziehen.")
            return
        
        try:
            service = TelegramAdminService()
            
            # Prüfe ob noch andere Admins existieren
            users = service.list_all_users()
            admin_count = sum(1 for u in users if u.role == "admin" and u.telegram_id != target_id)
            
            if admin_count == 0:
                await update.message.reply_text("❌ Es muss mindestens ein Admin vorhanden sein.")
                log_admin_action(user_id, "revoke_admin", target_id, False)
                return
            
            result = service.revoke_admin_role(target_id)
            if result:
                await update.message.reply_text(f"✅ Admin-Rechte von {target_id} wurden entzogen")
                log_admin_action(user_id, "revoke_admin", target_id, True)
            else:
                await update.message.reply_text(f"❌ Benutzer {target_id} war kein Admin")
                log_admin_action(user_id, "revoke_admin", target_id, False)
        except Exception as e:
            logger.error(f"Error in admin_revoke: {e}")
            await update.message.reply_text(f"❌ Fehler: {e}")
            log_admin_action(user_id, "revoke_admin", target_id, False)
    
    async def handle_admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/admin_stats - System-Statistiken (Admin)."""
        user_id = str(update.effective_user.id)
        
        if not await self.check_user_permission(user_id, "admin"):
            await update.message.reply_text("❌ Access denied.")
            return
        
        try:
            service = TelegramAdminService()
            stats = service.get_system_stats()
            message = service.format_stats(stats)
            await update.message.reply_text(message, parse_mode="Markdown")
            log_admin_action(user_id, "admin_stats", success=True)
        except Exception as e:
            logger.error(f"Error in admin_stats: {e}")
            await update.message.reply_text("❌ Fehler beim Laden der Statistiken")
            log_admin_action(user_id, "admin_stats", success=False)


class BotError(Exception):
    """Benutzerdefinierte Exception für Bot-Fehler."""
    pass


async def run_telegram_bot():
    """Hauptfunktion zum Starten des Bots."""
    bot = TelegramBotWorker()
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Bot wurde gestoppt durch Benutzer")
    finally:
        await bot.stop()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    asyncio.run(run_telegram_bot())
