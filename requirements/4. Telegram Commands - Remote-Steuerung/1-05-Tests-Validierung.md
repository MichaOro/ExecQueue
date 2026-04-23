# Arbeitspaket 1-05: Tests und Validierung der Telegram-Integration

## 1. Titel
Tests und Validierung der Telegram-Integration - Unit, Integration und E2E

## 2. Ziel
Umfassende Testabdeckung für alle Telegram-Bot-Komponenten mit Unit-Tests, Integrationstests und End-to-End-Szenarien. Sicherstellung, dass alle Tests bestehen vor dem Merge.

## 3. Fachlicher Kontext / Betroffene Domäne
- **Domäne**: Testautomatisierung und Qualitätssicherung
- **Zielgruppe**: Entwickler, QA, CI/CD
- **Business Value**: Verhindert Regressionen, dokumentiert erwartetes Verhalten, ermöglicht sicheres Refactoring

## 4. Betroffene Bestandteile

**Neu zu erstellen:**
- `tests/unit/test_telegram_bot.py` - Unit-Tests für Bot-Logik
- `tests/unit/test_telegram_notification_service.py` - Unit-Tests für Notification-Service
- `tests/unit/test_telegram_admin_service.py` - Unit-Tests für Admin-Service
- `tests/integration/test_telegram_integration.py` - Integrationstests
- `tests/api/test_telegram_commands.py` - API-Tests für Bot-Commands

**Zu erweitern:**
- `tests/conftest.py` - Fixtures für Telegram-Tests
- `tests/api/conftest.py` - API-Fixtures für Telegram
- `pytest.ini` - Optional: Telegram-spezifische Konfiguration

**Bestehende Strukturen (wiederverwendet):**
- `tests/api/conftest.py` - TestClient, Session-Fixtures
- `tests/unit/__init__.py` - Test-Utils
- `execqueue.db.session` - Test-Database-Session

## 5. Konkrete Umsetzungsschritte

### Schritt 1: Test-Fixtures und Conftest erweitern

**Datei: `tests/conftest.py` (erweitern)**

**Telegram-Bot-Fixture:**
```python
@pytest.fixture
def mock_telegram_bot():
    """Erstellt einen Mock für telegram.Bot."""
    with MagicMock() as mock:
        mock.send_message = AsyncMock(return_value=None)
        yield mock

@pytest.fixture
def telegram_admin_user():
    """Erstellt einen Test-Admin-Benutzer."""
    return TelegramUser(
        telegram_id="123456789",
        username="test_admin",
        role="admin",
        is_test=True
    )

@pytest.fixture
def telegram_operator_user():
    """Erstellt einen Test-Operator-Benutzer."""
    return TelegramUser(
        telegram_id="987654321",
        username="test_operator",
        role="operator",
        is_test=True
    )

@pytest.fixture
def telegram_observer_user():
    """Erstellt einen Test-Observer-Benutzer."""
    return TelegramUser(
        telegram_id="555555555",
        username="test_observer",
        role="observer",
        is_test=True
    )
```

**Anforderungen:**
- Alle Fixtures verwenden `is_test=True` für saubere Test-Daten
- Async-Mocks für Bot-Methoden
- Klare Benennung der Benutzer-Rollen

### Schritt 2: Unit-Tests für Bot-Commands

**Datei: `tests/unit/test_telegram_bot.py`**

**Test-Struktur:**
```python
class TestTelegramBotCommands:
    """Unit-Tests für Telegram-Bot Commands."""

    @pytest.mark.asyncio
    async def test_handle_start_shows_greeting(self, mock_update, mock_context):
        """Testet dass /start eine Begrüßungsnachricht sendet."""
        bot = TelegramBotWorker()
        await bot.handle_start(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Willkommen" in call_args or "Welcome" in call_args
        assert "/help" in call_args

    @pytest.mark.asyncio
    async def test_handle_help_shows_all_commands(self, mock_update, mock_context):
        """Testet dass /help alle Commands auflistet."""
        bot = TelegramBotWorker()
        await bot.handle_help(mock_update, mock_context)
        
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "/start" in call_args
        assert "/queue" in call_args
        assert "/status" in call_args
        assert "/health" in call_args

    @pytest.mark.asyncio
    async def test_handle_queue_shows_tasks(self, mock_update, mock_context, sample_tasks):
        """Testet dass /queue Tasks anzeigt."""
        bot = TelegramBotWorker()
        with patch("execqueue.workers.telegram_bot.call_api", return_value=sample_tasks):
            await bot.handle_queue(mock_update, mock_context)
        
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Task" in call_args or "queue" in call_args.lower()

    @pytest.mark.asyncio
    async def test_handle_status_requires_task_id(self, mock_update, mock_context):
        """Testet dass /status ohne task_id eine Fehlermeldung zeigt."""
        bot = TelegramBotWorker()
        mock_context.args = []  # Keine Argumente
        
        await bot.handle_status(mock_update, mock_context)
        
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "task_id" in call_args.lower() or "parameter" in call_args.lower()

    @pytest.mark.asyncio
    async def test_handle_status_shows_task_details(self, mock_update, mock_context, sample_task):
        """Testet dass /status <task_id> Details anzeigt."""
        bot = TelegramBotWorker()
        mock_context.args = ["123"]
        
        with patch("execqueue.workers.telegram_bot.call_api", return_value=sample_task):
            await bot.handle_status(mock_update, mock_context)
        
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "123" in call_args or sample_task["status"] in call_args

    @pytest.mark.asyncio
    async def test_handle_health_shows_system_status(self, mock_update, mock_context, mock_health_data):
        """Testet dass /health System-Status anzeigt."""
        bot = TelegramBotWorker()
        
        with patch("execqueue.workers.telegram_bot.call_api", return_value=mock_health_data):
            await bot.handle_health(mock_update, mock_context)
        
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "DB" in call_args or "database" in call_args.lower()

    @pytest.mark.asyncio
    async def test_rate_limiting_blocks_excessive_requests(self):
        """Testet dass Rate-Limiting zu viele Requests blockiert."""
        bot = TelegramBotWorker()
        user_id = "test_user"
        
        # Fülle Rate-Limit
        for _ in range(30):
            bot.check_rate_limit(user_id)
        
        # 31. Request sollte blockiert werden
        assert not bot.check_rate_limit(user_id)

    @pytest.mark.asyncio
    async def test_role_check_observer_cannot_access_admin_commands(
        self, telegram_observer_user, session
    ):
        """Testet dass Observer keine Admin-Commands ausführen können."""
        bot = TelegramBotWorker()
        
        has_permission = await bot.check_admin_permission(
            telegram_observer_user.telegram_id, session
        )
        
        assert has_permission is False

    @pytest.mark.asyncio
    async def test_role_check_admin_can_access_admin_commands(
        self, telegram_admin_user, session
    ):
        """Testet dass Admins Admin-Commands ausführen können."""
        bot = TelegramBotWorker()
        
        has_permission = await bot.check_admin_permission(
            telegram_admin_user.telegram_id, session
        )
        
        assert has_permission is True
```

**Anforderungen:**
- Async/Await für alle Test-Methoden
- Klare Test-Namen (beschreiben das erwartete Verhalten)
- Mocking für externe Abhängigkeiten (API, Bot)
- Isolierte Tests (jeder Test eigene Fixture)

### Schritt 3: Unit-Tests für Notification-Service

**Datei: `tests/unit/test_telegram_notification_service.py`**

**Test-Struktur:**
```python
class TestTelegramNotificationService:
    """Unit-Tests für Notification-Service."""

    @pytest.mark.asyncio
    async def test_send_notification_sends_to_subscribed_users(
        self, mock_bot, telegram_observer_user, session
    ):
        """Testet dass Notifications nur an abonnierte Benutzer gesendet werden."""
        # Benutzer abonniert task_completed
        telegram_observer_user.subscribed_events = '{"task_completed": true}'
        session.add(telegram_observer_user)
        session.commit()
        
        service = TelegramNotificationService(mock_bot)
        await service.notify_task_completed(MockTask(id=123, status="done"))
        
        mock_bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_notification_skips_unsubscribed_users(
        self, mock_bot, telegram_observer_user, session
    ):
        """Testet dass Notifications nicht an nicht-abonnierte Benutzer gesendet werden."""
        # Benutzer hat nichts abonniert
        telegram_observer_user.subscribed_events = '{}'
        session.add(telegram_observer_user)
        session.commit()
        
        service = TelegramNotificationService(mock_bot)
        await service.notify_task_completed(MockTask(id=123, status="done"))
        
        mock_bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_task_completed_formats_message_correctly(
        self, mock_bot, session
    ):
        """Testet dass Task-Abschluss korrekt formatiert wird."""
        service = TelegramNotificationService(mock_bot)
        
        task = MockTask(
            id=123,
            status="done",
            validation_summary="Tests bestanden",
            validation_evidence="All tests passed"
        )
        
        await service.notify_task_completed(task)
        
        call_args = mock_bot.send_message.call_args[1]["text"]
        assert "123" in call_args
        assert "abgeschlossen" in call_args or "completed" in call_args

    @pytest.mark.asyncio
    async def test_notify_validation_failed_sends_error_message(
        self, mock_bot, session
    ):
        """Testet dass Validierungsfehler-Nachricht gesendet wird."""
        service = TelegramNotificationService(mock_bot)
        
        task = MockTask(id=456, status="failed")
        await service.notify_validation_failed(task)
        
        mock_bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_retry_exhausted_sends_critical_alert(
        self, mock_bot, session
    ):
        """Testet dass erschöpftes Retry-Limit kritisch alarmiert."""
        service = TelegramNotificationService(mock_bot)
        
        task = MockTask(id=789, retry_count=3, max_retries=3)
        await service.notify_retry_exhausted(task)
        
        call_args = mock_bot.send_message.call_args[1]["text"]
        assert "Retry" in call_args or "retry" in call_args

    @pytest.mark.asyncio
    async def test_save_notification_stores_in_database(
        self, mock_bot, session, telegram_observer_user
    ):
        """Testet dass Notifications in DB gespeichert werden."""
        service = TelegramNotificationService(mock_bot)
        
        await service._save_notification(
            user_telegram_id=telegram_observer_user.telegram_id,
            event_type="task_completed",
            message="Test notification",
            task_id=123
        )
        
        notification = session.exec(
            select(TelegramNotification)
            .where(TelegramNotification.user_telegram_id == telegram_observer_user.telegram_id)
        ).first()
        
        assert notification is not None
        assert notification.event_type == "task_completed"
        assert notification.message == "Test notification"
        assert notification.sent_at is None  # Noch nicht gesendet
```

**Anforderungen:**
- MockTask-Klasse für Test-Daten
- Isolierte Tests für jede Notification-Art
- Datenbank-Tests mit echter Session

### Schritt 4: Unit-Tests für Admin-Service

**Datei: `tests/unit/test_telegram_admin_service.py`**

**Test-Struktur:**
```python
class TestTelegramAdminService:
    """Unit-Tests für Admin-Service."""

    def test_list_all_users_returns_all_users(self, session, telegram_admin_user, telegram_operator_user):
        """Testet dass alle Benutzer gelistet werden."""
        session.add(telegram_admin_user)
        session.add(telegram_operator_user)
        session.commit()
        
        service = TelegramAdminService(session)
        users = service.list_all_users()
        
        assert len(users) == 2

    def test_grant_admin_role_creates_user_if_not_exists(self, session):
        """Testet dass grant_admin_role Benutzer erstellt wenn nicht existent."""
        service = TelegramAdminService(session)
        
        user = service.grant_admin_role("999999999")
        
        assert user.telegram_id == "999999999"
        assert user.role == "admin"

    def test_grant_admin_role_updates_existing_user(self, session, telegram_operator_user):
        """Testet dass grant_admin_role Rolle aktualisiert."""
        service = TelegramAdminService(session)
        session.add(telegram_operator_user)
        session.commit()
        
        user = service.grant_admin_role(telegram_operator_user.telegram_id)
        
        assert user.role == "admin"

    def test_revoke_admin_role_downgrades_to_operator(self, session, telegram_admin_user):
        """Testet dass revoke_admin_role auf Operator herabstuft."""
        service = TelegramAdminService(session)
        session.add(telegram_admin_user)
        session.commit()
        
        result = service.revoke_admin_role(telegram_admin_user.telegram_id)
        
        assert result is True
        refreshed = session.get(TelegramUser, telegram_admin_user.id)
        assert refreshed.role == "operator"

    def test_revoke_admin_role_returns_false_for_non_admin(self, session, telegram_operator_user):
        """Testet dass revoke_admin_role False zurückgibt wenn kein Admin."""
        service = TelegramAdminService(session)
        session.add(telegram_operator_user)
        session.commit()
        
        result = service.revoke_admin_role(telegram_operator_user.telegram_id)
        
        assert result is False

    def test_revoke_admin_role_returns_false_for_nonexistent_user(self, session):
        """Testet dass revoke_admin_role False zurückgibt wenn Benutzer nicht existiert."""
        service = TelegramAdminService(session)
        
        result = service.revoke_admin_role("999999999")
        
        assert result is False

    def test_get_system_stats_returns_correct_counts(
        self, session, sample_tasks, telegram_admin_user, telegram_operator_user
    ):
        """Testet dass System-Stats korrekt gezählt werden."""
        session.add(telegram_admin_user)
        session.add(telegram_operator_user)
        session.commit()
        
        service = TelegramAdminService(session)
        stats = service.get_system_stats()
        
        assert "tasks" in stats
        assert "requirements" in stats
        assert "telegram_users" in stats
        assert "admin_users" in stats
        assert stats["admin_users"] == 1
```

**Anforderungen:**
- Synchronized Tests (nicht async, da keine I/O)
- Datenbank-Operations in Session
- Klare Assertions für jede Operation

### Schritt 5: Integrationstests

**Datei: `tests/integration/test_telegram_integration.py`**

**Test-Struktur:**
```python
class TestTelegramIntegration:
    """Integrationstests für Telegram-Bot mit echter Datenbank."""

    @pytest.mark.asyncio
    async def test_full_command_flow_from_start_to_queue(
        self, mock_telegram_bot, session
    ):
        """Testet kompletten Command-Flow von /start bis /queue."""
        # 1. Benutzer erstellt (automatisch bei erstem Command)
        # 2. /start Command
        # 3. /help Command
        # 4. /queue Command
        # 5. Verifiziere dass alle Nachrichten gesendet wurden
        
        pass  # Implementierung folgt

    @pytest.mark.asyncio
    async def test_subscription_flow_subscribe_and_receive_notification(
        self, mock_telegram_bot, session, telegram_observer_user
    ):
        """Testet kompletten Subscription-Flow."""
        # 1. Benutzer subscribt zu task_completed
        # 2. Task abgeschlossen
        # 3. Verifiziere dass Notification gesendet wurde
        
        pass  # Implementierung folgt

    @pytest.mark.asyncio
    async def test_admin_grant_revoke_cycle(self, mock_telegram_bot, session, telegram_operator_user):
        """Testet Admin-Grant und Revoke Zyklus."""
        # 1. Operator ist kein Admin
        # 2. Admin grantet Rechte
        # 3. Verifiziere Admin-Rolle
        # 4. Admin revokes Rechte
        # 5. Verifiziere Operator-Rolle
        
        pass  # Implementierung folgt

    @pytest.mark.asyncio
    async def test_rate_limiting_prevents_abuse(self, mock_telegram_bot, session):
        """Testet dass Rate-Limiting Missbrauch verhindert."""
        # 1. Sende 30 Commands in kurzer Zeit
        # 2. 31. Command sollte blockiert werden
        
        pass  # Implementierung folgt
```

**Anforderungen:**
- Echte Datenbank-Session
- Mock-Bot für Telegram-API
- Komplette Szenarien (nicht nur einzelne Methoden)

### Schritt 6: E2E-Tests (Optional)

**Datei: `tests/e2e/test_telegram_e2e.py`**

**Test-Struktur:**
```python
@pytest.mark.e2e
class TestTelegramE2E:
    """End-to-End-Tests mit echtem Bot-Start (nur manuell)."""

    @pytest.mark.skip(reason="Requires running bot and Telegram account")
    async def test_bot_starts_and_responds_to_start_command(self):
        """E2E: Bot startet und antwortet auf /start."""
        # Nur manuell ausführbar
        # Benötigt:
        # - Laufenden Bot mit echtem Token
        # - Telegram-Account für Tests
        
        pass
```

**Anforderungen:**
- Mit @pytest.mark.e2e markiert
- Standardmäßig übersprungen (skip)
- Nur manuell ausführbar mit echter Telegram-Integration

### Schritt 7: Test-Abdeckung validieren

**Datei: `pytest.ini` (erweitern)**

**Konfiguration:**
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Coverage-Konfiguration
addopts = 
    --cov=execqueue
    --cov-report=term-missing
    --cov-report=html
    --cov-fail-under=80

# Markers
markers =
    e2e: End-to-End tests (requires external services)
    telegram: Telegram-Bot tests
    slow: Slow running tests
```

**Anforderungen:**
- Minimum 80% Coverage für Telegram-Code
- Coverage-Report in HTML für Detail-Analyse
- Marker für E2E-Tests (umgehen bei CI)

## 6. Architektur- und Codequalitätsvorgaben

**Clean Code:**
- Test-Namen beschreiben das erwartete Verhalten
- AAA-Struktur (Arrange-Act-Assert) in allen Tests
- Keine redundanten Tests

**Test-Isolation:**
- Jeder Test verwendet eigene Datenbank-Session
- Test-Daten mit `is_test=True`
- Cleanup nach jedem Test (Fixture teardown)

**Async Testing:**
- `@pytest.mark.asyncio` für alle async Tests
- `AsyncMock` für async Dependencies
- `pytest-asyncio` mit `asyncio_mode = auto`

## 7. Abgrenzung: Was NICHT Teil des Pakets ist

- **Keine Performance-Tests** (z.B. Load-Tests mit 100 Benutzern)
- **Keine Security-Tests** (z.B. SQL-Injection, XSS)
- **Keine UI-Tests** (kein Selenium für Telegram Web)
- **Keine Contract-Tests** mit Telegram-API

## 8. Abhängigkeiten

**Vorausgesetzt:**
- Alle vorherigen Arbeitspakete (1-01 bis 1-04) sind implementiert
- `pytest-asyncio` ist installiert
- `pytest-cov` ist installiert

**Wird benötigt für:**
- CI/CD Pipeline (Tests müssen bestehen vor Merge)

## 9. Akzeptanzkriterien

- [ ] Unit-Tests für alle Bot-Commands (`/start`, `/help`, `/queue`, `/status`, `/health`, etc.)
- [ ] Unit-Tests für Notification-Service (alle Event-Typen)
- [ ] Unit-Tests für Admin-Service (grant, revoke, list, stats)
- [ ] Integrationstests für komplette Szenarien
- [ ] E2E-Tests markiert und übersprungen (manuell ausführbar)
- [ ] Test-Abdeckung >= 80% für Telegram-Code
- [ ] Alle Tests bestehen (`pytest`)
- [ ] Tests sind isoliert (keine Abhängigkeiten zwischen Tests)
- [ ] Test-Daten mit `is_test=True` gekennzeichnet
- [ ] Async Tests verwenden `@pytest.mark.asyncio`

## 10. Risiken / Prüfpunkte

| Risiko | Auswirkung | Minderung |
|--------|------------|-----------|
| Flaky Tests durch Timing | Tests failen intermittierend | Explizite Await-Punkte, keine `sleep()` |
| Test-Daten-Kollision | Tests beeinflussen sich gegenseitig | Eigene Session pro Test, Cleanup |
| Mocks zu stark | Tests decken nicht wirkliches Verhalten ab | Integrationstests für kritische Pfade |
| E2E-Tests in CI | CI-Tests failen durch externe Abhängigkeiten | @pytest.mark.e2e mit skip in CI |

**Prüfpunkte vor Merge:**
- [ ] `pytest -v` läuft erfolgreich
- [ ] Coverage-Bericht zeigt >= 80% für Telegram-Code
- [ ] Keine flaky Tests (3x `pytest` erfolgreich)
- [ ] E2E-Tests sind in CI übersprungen

## 11. Begründung für Struktur

**Warum separate Test-Dateien für jeden Service?**
- **Organisation**: Klare Trennung nach Domänen (Bot, Notification, Admin)
- **Wartbarkeit**: Tests für einen Service können unabhängig geändert werden
- **CI/CD**: Paralleles Ausführen möglich

**Warum Integrationstests getrennt von Unit-Tests?**
- **Geschwindigkeit**: Unit-Tests sind schneller (keine DB)
- **Zweck**: Integrationstests testen echte Interaktionen
- **CI/CD**: Unit-Tests in jedem PR, Integrationstests in Nightly-Builds

**Bewusste Entscheidung: Keine E2E-Tests in CI**
- E2E-Tests benötigen echte Telegram-Integration
- Zu instabil für automatisierte CI
- Manuell ausführbar bei Bedarf

## 12. Empfohlene Dateinamen

- `tests/unit/test_telegram_bot.py`
- `tests/unit/test_telegram_notification_service.py`
- `tests/unit/test_telegram_admin_service.py`
- `tests/integration/test_telegram_integration.py`
- `tests/e2e/test_telegram_e2e.py` (optional)

## 13. Zielpfade

- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/tests/unit/test_telegram_bot.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/tests/unit/test_telegram_notification_service.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/tests/unit/test_telegram_admin_service.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/tests/integration/test_telegram_integration.py`
- `/home/ubuntu/workspace/IdeaProjects/ExecQueue/tests/e2e/test_telegram_e2e.py`

---

**Ende Arbeitspaket 1-05**