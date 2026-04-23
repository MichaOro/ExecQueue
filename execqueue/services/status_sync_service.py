"""
Status-Synchronisation Service für das orchestrierte Task-System.

Synchronisiert Status-Änderungen zwischen Tasks, WorkPackages und Requirements
gemäß dem Kanban-Statusmodell (backlog → in_progress → review → done → trash).
"""

from sqlmodel import Session, select
from typing import Optional, List
from datetime import datetime, timezone
from execqueue.models.task import Task
from execqueue.models.work_package import WorkPackage
from execqueue.models.requirement import Requirement
import logging

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    """Returns current datetime in UTC timezone."""
    return datetime.now(timezone.utc)

# Gültige Status-Übergänge im Kanban-Modell
VALID_STATUS_TRANSITIONS = {
    "backlog": ["in_progress", "trash"],
    "in_progress": ["backlog", "review", "trash"],
    "review": ["in_progress", "backlog", "done", "trash"],
    "done": ["review", "backlog"],
    "trash": ["backlog"],
}


class StatusValidationError(Exception):
    """Exception bei ungültigen Status-Übergängen."""
    pass


def validate_status_transition(old_status: str, new_status: str) -> bool:
    """
    Prüft ob ein Status-Übergang gültig ist.
    
    Args:
        old_status: Aktueller Status
        new_status: Neuer Status
        
    Returns:
        True wenn Übergang gültig
        
    Raises:
        StatusValidationError: Wenn Übergang ungültig ist
    """
    if old_status == new_status:
        return True
        
    allowed = VALID_STATUS_TRANSITIONS.get(old_status, [])
    if new_status not in allowed:
        raise StatusValidationError(
            f"Ungültiger Status-Übergang von '{old_status}' zu '{new_status}'. "
            f"Erlaubt: {allowed}"
        )
    return True


def calculate_requirement_status(requirement: Requirement, session: Session) -> str:
    """
    Berechnet den Status eines Requirements basierend auf seinen WorkPackages.
    
    Status-Logik:
    - done: Alle WorkPackages sind done
    - in_progress: Mindestens ein WorkPackage ist in_progress oder review
    - backlog: Alle WorkPackages sind backlog
    - trash: Mindestens ein WorkPackage ist trash
    
    Args:
        requirement: Das Requirement
        session: Datenbank-Session
        
    Returns:
        Berechneter Status
    """
    work_packages = session.exec(
        select(WorkPackage).where(WorkPackage.requirement_id == requirement.id)
    ).all()
    
    if not work_packages:
        return requirement.queue_status
    
    statuses = [wp.queue_status for wp in work_packages]
    
    if "trash" in statuses:
        return "trash"
    elif all(s == "done" for s in statuses):
        return "done"
    elif any(s in ["in_progress", "review"] for s in statuses):
        return "in_progress"
    else:
        return "backlog"


def calculate_work_package_status(work_package: WorkPackage, session: Session) -> str:
    """
    Berechnet den Status eines WorkPackages basierend auf seinen Tasks.
    
    Args:
        work_package: Das WorkPackage
        session: Datenbank-Session
        
    Returns:
        Berechneter Status
    """
    tasks = session.exec(
        select(Task).where(
            Task.source_type == "work_package",
            Task.source_id == work_package.id
        )
    ).all()
    
    if not tasks:
        return work_package.queue_status
    
    statuses = [t.queue_status for t in tasks]
    
    if "trash" in statuses:
        return "trash"
    elif all(s == "done" for s in statuses):
        return "done"
    elif any(s in ["in_progress", "review"] for s in statuses):
        return "in_progress"
    else:
        return "backlog"


def sync_task_status_to_parent(task: Task, session: Session) -> None:
    """
    Synchronisiert den Task-Status auf das Parent-Objekt (WorkPackage oder Requirement).
    
    HINWEIS: Diese Funktion führt KEIN session.commit() aus. Der Caller kontrolliert
    die Transaction-Granularität für atomare Updates über alle Entity-Grenzen hinweg.
    
    Args:
        task: Der Task
        session: Datenbank-Session
    """
    if task.source_type == "work_package":
        work_package = session.get(WorkPackage, task.source_id)
        if work_package:
            new_status = calculate_work_package_status(work_package, session)
            if work_package.queue_status != new_status:
                validate_status_transition(work_package.queue_status, new_status)
                work_package.queue_status = new_status
                work_package.updated_at = task.updated_at
                session.add(work_package)
                logger.debug(
                    "Synced WorkPackage %d status to '%s' (via task %d)",
                    work_package.id, new_status, task.id
                )
                
                # Auch Requirement aktualisieren (ohne commit - Caller macht das)
                requirement = session.get(Requirement, work_package.requirement_id)
                if requirement:
                    new_req_status = calculate_requirement_status(requirement, session)
                    if requirement.queue_status != new_req_status:
                        validate_status_transition(requirement.queue_status, new_req_status)
                        requirement.queue_status = new_req_status
                        requirement.updated_at = task.updated_at
                        session.add(requirement)
                        logger.debug(
                            "Synced Requirement %d status to '%s' (via work package %d)",
                            requirement.id, new_req_status, work_package.id
                        )
                        
    elif task.source_type == "requirement":
        requirement = session.get(Requirement, task.source_id)
        if requirement and requirement.queue_status != task.queue_status:
            validate_status_transition(requirement.queue_status, task.queue_status)
            requirement.queue_status = task.queue_status
            requirement.updated_at = task.updated_at
            session.add(requirement)
            logger.debug(
                "Synced Requirement %d status to '%s' (via task %d)",
                requirement.id, task.queue_status, task.id
            )
    
    # KEIN session.commit() hier - Caller kontrolliert Transaction


def sync_requirement_status(requirement: Requirement, session: Session, commit: bool = False) -> Requirement:
    """
    Synchronisiert den Requirement-Status basierend auf WorkPackages.
    
    Args:
        requirement: Das Requirement
        session: Datenbank-Session
        commit: Optional, ob ein Commit durchgeführt werden soll (Default: False)
        
    Returns:
        Aktualisiertes Requirement
    """
    new_status = calculate_requirement_status(requirement, session)
    if requirement.queue_status != new_status:
        validate_status_transition(requirement.queue_status, new_status)
        requirement.queue_status = new_status
        requirement.updated_at = utcnow()
        session.add(requirement)
        
        if commit:
            session.commit()
            logger.info(
                "Synced Requirement %d status to '%s' (berechnet aus WorkPackages)",
                requirement.id, new_status
            )
        else:
            logger.debug(
                "Prepared Requirement %d status update to '%s' (commit pending)",
                requirement.id, new_status
            )
    return requirement


def sync_work_package_status(work_package: WorkPackage, session: Session, commit: bool = False) -> WorkPackage:
    """
    Synchronisiert den WorkPackage-Status basierend auf Tasks.
    
    Args:
        work_package: Das WorkPackage
        session: Datenbank-Session
        commit: Optional, ob ein Commit durchgeführt werden soll (Default: False)
        
    Returns:
        Aktualisiertes WorkPackage
    """
    new_status = calculate_work_package_status(work_package, session)
    if work_package.queue_status != new_status:
        validate_status_transition(work_package.queue_status, new_status)
        work_package.queue_status = new_status
        work_package.updated_at = utcnow()
        session.add(work_package)
        
        if commit:
            session.commit()
            logger.info(
                "Synced WorkPackage %d status to '%s' (berechnet aus Tasks)",
                work_package.id, new_status
            )
        else:
            logger.debug(
                "Prepared WorkPackage %d status update to '%s' (commit pending)",
                work_package.id, new_status
            )
    return work_package


def update_task_queue_status(task: Task, new_status: str, session: Session, commit: bool = True) -> Task:
    """
    Aktualisiert den queue_status eines Tasks und synchronisiert auf Parents.
    
    Args:
        task: Der Task
        new_status: Neuer Status
        session: Datenbank-Session
        commit: Optional, ob ein Commit durchgeführt werden soll (Default: True)
        
    Returns:
        Aktualisierter Task
    """
    validate_status_transition(task.queue_status, new_status)
    task.queue_status = new_status
    task.updated_at = utcnow()
    session.add(task)
    
    # Parent synchronisieren (ohne Commit)
    sync_task_status_to_parent(task, session)
    
    if commit:
        session.commit()
        session.refresh(task)
        logger.info(
            "Updated Task %d queue_status to '%s' (source_type: %s)",
            task.id, new_status, task.source_type
        )
    else:
        logger.debug(
            "Prepared Task %d queue_status update to '%s' (commit pending)",
            task.id, new_status
        )
    
    return task


def update_work_package_queue_status(
    work_package: WorkPackage, 
    new_status: str, 
    session: Session,
    commit: bool = True
) -> WorkPackage:
    """
    Aktualisiert den queue_status eines WorkPackages und synchronisiert auf Requirement.
    
    Args:
        work_package: Das WorkPackage
        new_status: Neuer Status
        session: Datenbank-Session
        commit: Optional, ob ein Commit durchgeführt werden soll (Default: True)
        
    Returns:
        Aktualisiertes WorkPackage
    """
    validate_status_transition(work_package.queue_status, new_status)
    work_package.queue_status = new_status
    work_package.updated_at = utcnow()
    session.add(work_package)
    
    # Requirement synchronisieren (ohne Commit)
    requirement = session.get(Requirement, work_package.requirement_id)
    if requirement:
        sync_requirement_status(requirement, session, commit=False)
    
    if commit:
        session.commit()
        session.refresh(work_package)
        logger.info("Updated WorkPackage %d queue_status to '%s'", work_package.id, new_status)
    else:
        logger.debug(
            "Prepared WorkPackage %d queue_status update to '%s' (commit pending)",
            work_package.id, new_status
        )
    
    return work_package


def update_requirement_queue_status(
    requirement: Requirement, 
    new_status: str, 
    session: Session,
    commit: bool = True
) -> Requirement:
    """
    Aktualisiert den queue_status eines Requirements.
    
    Args:
        requirement: Das Requirement
        new_status: Neuer Status
        session: Datenbank-Session
        commit: Optional, ob ein Commit durchgeführt werden soll (Default: True)
        
    Returns:
        Aktualisiertes Requirement
    """
    validate_status_transition(requirement.queue_status, new_status)
    requirement.queue_status = new_status
    requirement.updated_at = utcnow()
    session.add(requirement)
    
    if commit:
        session.commit()
        session.refresh(requirement)
        logger.info("Updated Requirement %d queue_status to '%s'", requirement.id, new_status)
    else:
        logger.debug(
            "Prepared Requirement %d queue_status update to '%s' (commit pending)",
            requirement.id, new_status
        )
    
    return requirement


def get_kanban_summary(session: Session, is_test: bool = False) -> dict:
    """
    Erstellt eine Kanban-Übersicht aller Entities.
    
    Args:
        session: Datenbank-Session
        is_test: Nur Test-Daten
        
    Returns:
        Dict mit Status-Counts pro Entity-Typ
    """
    from sqlmodel import func
    
    where_clause = Task.is_test == is_test
    tasks_by_status = session.exec(
        select(Task.queue_status, func.count(Task.id))
        .where(where_clause)
        .group_by(Task.queue_status)
    ).all()
    
    where_clause_wp = WorkPackage.is_test == is_test
    wps_by_status = session.exec(
        select(WorkPackage.queue_status, func.count(WorkPackage.id))
        .where(where_clause_wp)
        .group_by(WorkPackage.queue_status)
    ).all()
    
    where_clause_req = Requirement.is_test == is_test
    reqs_by_status = session.exec(
        select(Requirement.queue_status, func.count(Requirement.id))
        .where(where_clause_req)
        .group_by(Requirement.queue_status)
    ).all()
    
    return {
        "tasks": dict(tasks_by_status),
        "work_packages": dict(wps_by_status),
        "requirements": dict(reqs_by_status),
    }
