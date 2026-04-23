# Anforderungsartefakt: Orchestriertes Task- und Requirement-System

## 1. Titel

Orchestriertes Task-System mit Requirement-Hierarchie, Queue-Steuerung
und Statusmodell

## 2. Zielbild / Systemvision

Ein robustes, deterministisches Verarbeitungssystem zur automatisierten
und manuellen Abarbeitung von Anforderungen und daraus abgeleiteten
Tasks.

Kerncharakteristika: - Hierarchisches Modell: Requirement → WorkPackages
→ Tasks\
- Deterministische Queue-Verarbeitung mit Blockierungs- und
Parallelisierungslogik\
- Persistente Execution Engine (OpenCode) mit Ergebnis-Speicherung\
- Kanban-basiertes Statusmodell für alle Ebenen\
- Scheduler + API-gesteuerte Ausführung

## 3. Systemkontext

Das System dient der strukturierten Verarbeitung von: -
Anforderungsartefakten - Transkripten - Code-bezogenen Aufgaben

Verarbeitung erfolgt über eine Execution Engine (OpenCode), die: - Input
(Content + Prompt) verarbeitet - Ergebnisse persistiert - optional Code
verändert - immer eine Zusammenfassung erzeugt

## 4. Domänenmodell

### Requirement

-   Content
-   Prompt
-   Type (transcript \| artifact)
-   Queue Status (Kanban)
-   Scheduler Flags
-   WorkPackage-Existenz
-   Order-Steuerung
-   System-ID (falls nicht vorhanden auto-generiert)

### WorkPackage

-   Content / Prompt
-   Status (Kanban)
-   OrderNumber
-   Dependency
-   Parallelisierungsfähigkeit
-   Beziehung zu Requirement (1:n)

### Task

-   block_queue
-   parallelization_allowed
-   schedulable
-   source_type (Requirement / WorkPackage)
-   Execution Status

## 5. Prozessmodell

Requirement → WorkPackages → Tasks → Queue → Execution → Persistiertes
Ergebnis

## 6. Statusmodell (Kanban)

Backlog → In Progress → Review → Done\
↓\
Trash

## 7. Queue- und Scheduling-Modell

-   Zentrale Queue für Tasks
-   Scheduler läuft kontinuierlich
-   Manuelle Steuerung via API

### Steuerung

-   block_queue → blockiert Queue
-   parallelization_allowed → erlaubt Parallelität
-   schedulable → erlaubt Scheduler-Ausführung

## 8. Execution Engine

-   Verarbeitung von Tasks
-   Optional Codeänderungen
-   Persistenz
-   Zusammenfassung je Task

## 9. Datenmodell-Anforderungen

### Requirement

-   queue_status
-   type
-   has_work_packages
-   order_number
-   scheduler_enabled
-   parallelization_delay

### WorkPackage

-   queue_status
-   order_number
-   dependency_id
-   parallelization_enabled

### Task

-   block_queue
-   parallelization_allowed
-   schedulable
-   queue_status

## 10. Fachliche Regeln

-   Status synchron zwischen Task und Parent
-   Dependencies müssen erfüllt sein
-   Reihenfolge über order_number

## 11. Schnittstellen

-   Task starten
-   Status ändern
-   Queue steuern
-   Kanban abrufen

## 12. Nicht-Funktionale Anforderungen

-   Skalierbarkeit über Parallelisierung
-   Konsistenz durch Locking
-   Persistenz aller Ergebnisse

## 13. Constraints

-   Single-Instance Scheduler
-   PostgreSQL + SQLModel
-   Keine verteilte Queue

## 14. Risiken

-   Queue-Blockade
-   Deadlocks
-   Race Conditions
-   Starvation

## 15. Offene Punkte

-   Parallelisierungslimit
-   Blockierungs-Granularität
-   Retry-Strategie
-   Dependency-Zyklen
-   Scheduler-Intervall

## 16. Datenbank-Migration und Schema-Management

### 16.1 Aktuelle Situation
- **Bestehende Daten**: Production-Datenbank enthält bereits Daten in `tasks`, `requirement`, `work_packages` Tabellen
- **Schema-Änderungen**: Neue Felder müssen hinzugefügt werden ohne existierende Daten zu verlieren
- **Problem**: `create_db_and_tables()` führt `drop_all()` aus und löscht ALLE Daten

### 16.2 Migrations-Anforderungen

#### Muss-Anforderungen
- **Kein Datenverlust**: Bestehende Daten müssen erhalten bleiben
- **Schemaversionierung**: Schema-Änderungen müssen versioniert und nachvollziehbar sein
- **Rückwärtskompatibilität**: Alte Code-Versionen müssen mit neuem Schema arbeiten können (während Übergangsphase)
- **Testbarkeit**: Migration muss in Test-Umgebung validiert werden können

#### Soll-Anforderungen
- **In-place Migration**: Felder werden mit `ALTER TABLE` hinzugefügt
- **Default-Werte**: Neue Felder haben sinnvolle Defaults für existierende Daten
- **Rollback-Fähigkeit**: Migration kann bei Problemen rückgängig gemacht werden
- **Dokumentation**: Jeder Migrationsschritt ist dokumentiert

### 16.3 Migrations-Strategie

#### Option A: Manuelle SQL-Migration (Empfohlen für dieses Projekt)
```sql
-- Requirement Tabelle erweitern
ALTER TABLE requirement 
    ADD COLUMN IF NOT EXISTS queue_status VARCHAR(50) DEFAULT 'backlog',
    ADD COLUMN IF NOT EXISTS type VARCHAR(50) DEFAULT 'artifact',
    ADD COLUMN IF NOT EXISTS has_work_packages BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS order_number INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS scheduler_enabled BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS parallelization_delay INTEGER DEFAULT 0;

-- WorkPackage Tabelle erweitern
ALTER TABLE work_packages
    ADD COLUMN IF NOT EXISTS queue_status VARCHAR(50) DEFAULT 'backlog',
    ADD COLUMN IF NOT EXISTS order_number INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS dependency_id INTEGER,
    ADD COLUMN IF NOT EXISTS parallelization_enabled BOOLEAN DEFAULT FALSE;

-- Task Tabelle erweitern
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS block_queue BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS parallelization_allowed BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS schedulable BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS queue_status VARCHAR(50) DEFAULT 'backlog';

-- Fremdschlüssel für dependency_id hinzufügen
ALTER TABLE work_packages
    ADD CONSTRAINT fk_work_packages_dependency
    FOREIGN KEY (dependency_id) REFERENCES work_packages(id);

-- Indizes erstellen
CREATE INDEX IF NOT EXISTS idx_requirement_queue_status ON requirement(queue_status);
CREATE INDEX IF NOT EXISTS idx_work_packages_queue_status ON work_packages(queue_status);
CREATE INDEX IF NOT EXISTS idx_tasks_queue_status ON tasks(queue_status);
CREATE INDEX IF NOT EXISTS idx_tasks_block_queue_status ON tasks(block_queue, status);
```

#### Option B: Alembic Migrations (falls gewünscht)
- Alembic installieren und initialisieren
- Autogenerate Migration für Schema-Änderungen
- Migration manuell reviewen und anpassen
- Migration auf Production anwenden

### 16.4 Migrations-Checkliste

#### Vor der Migration
- [ ] Backup der Production-Datenbank erstellen
- [ ] Migration in Test-Umgebung validieren
- [ ] Schema-Änderungen dokumentieren
- [ ] Rollback-Plan erstellen
- [ ] Downtime-Fenster planen (falls nötig)

#### Während der Migration
- [ ] Application stoppen (falls nötig)
- [ ] Backup verifizieren
- [ ] Migration ausführen
- [ ] Schema-Änderungen verifizieren
- [ ] Datenintegrität prüfen

#### Nach der Migration
- [ ] Application starten
- [ ] Funktionale Tests ausführen
- [ ] Performance prüfen
- [ ] Monitoring aktivieren
- [ ] Backup nach Migration erstellen

### 16.5 Risiko-Minderung

#### Datenverlust-Risiko
- **Minderung**: Vollständiges Backup vor Migration
- **Minderung**: Migration in Test-Umgebung zuerst testen
- **Minderung**: Rollback-Plan bereithalten

#### Downtime-Risiko
- **Minderung**: Migration während Wartungsfenster
- **Minderung**: Online-Migration mit minimaler Downtime
- **Minderung**: Blue-Green Deployment falls möglich

#### Kompatibilitäts-Risiko
- **Minderung**: Neue Felder mit NULL oder Defaults
- **Minderung**: Graduelle Migration (Feature Flags)
- **Minderung**: Backward-compatible Code-Änderungen

### 16.6 Empfohlener Ablauf

1. **Test-Datenbank**: Migration auf Test-Datenbank ausführen
2. **Validierung**: Funktionale Tests nach Migration
3. **Production-Backup**: Vollständiges Backup erstellen
4. **Downtime-Fenster**: Wartungsfenster planen
5. **Production-Migration**: Migration ausführen
6. **Verifikation**: Schema und Daten prüfen
7. **Application-Deploy**: Neue Code-Version deployen
8. **Monitoring**: System überwachen
9. **Rollback-Plan**: Bis zur Stabilität bereithalten
