"""
Status-Synchronisation Service für das orchestrierte Task-System.

Synchronisiert Status-Änderungen zwischen Tasks, WorkPackages und Requirements
gemäß dem Kanban-Statusmodell (backlog → in_progress → review → done → trash).
"""

from sqlmodel import Session, select
from typing import Optional, List
from execqueue.models.task import Task
from execqueue.models.work_package import WorkPackage
from execqueue.models.requirement import Requirement
import logging

logger = logging.getLogger(__name__)

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
                    f"Synced WorkPackage {work_package.id} status to '{new_status}' "
                    f"(via task {task.id})"
                )
                
                # Auch Requirement aktualisieren
                requirement = session.get(Requirement, work_package.requirement_id)
                if requirement:
                    new_req_status = calculate_requirement_status(requirement, session)
                    if requirement.queue_status != new_req_status:
                        validate_status_transition(requirement.queue_status, new_req_status)
                        requirement.queue_status = new_req_status
                        requirement.updated_at = task.updated_at
                        session.add(requirement)
                        logger.debug(
                            f"Synced Requirement {requirement.id} status to '{new_req_status}' "
                            f"(via work package {work_package.id})"
                        )
                        
    elif task.source_type == "requirement":
        requirement = session.get(Requirement, task.source_id)
        if requirement and requirement.queue_status != task.queue_status:
            validate_status_transition(requirement.queue_status, task.queue_status)
            requirement.queue_status = task.queue_status
            requirement.updated_at = task.updated_at
            session.add(requirement)
            logger.debug(
                f"Synced Requirement {requirement.id} status to '{task.queue_status}' "
                f"(via task {task.id})"
            )
    
    session.commit()


def sync_requirement_status(requirement: Requirement, session: Session) -> Requirement:
    """
    Synchronisiert den Requirement-Status basierend auf WorkPackages.
    
    Args:
        requirement: Das Requirement
        session: Datenbank-Session
        
    Returns:
        Aktualisiertes Requirement
    """
    new_status = calculate_requirement_status(requirement, session)
    if requirement.queue_status != new_status:
        validate_status_transition(requirement.queue_status, new_status)
        requirement.queue_status = new_status
        requirement.updated_at = requirement.updated_at
        session.add(requirement)
        session.commit()
        logger.info(
            f"Synced Requirement {requirement.id} status to '{new_status}' "
            f"(berechnet aus WorkPackages)"
        )
    return requirement


def sync_work_package_status(work_package: WorkPackage, session: Session) -> WorkPackage:
    """
    Synchronisiert den WorkPackage-Status basierend auf Tasks.
    
    Args:
        work_package: Das WorkPackage
        session: Datenbank-Session
        
    Returns:
        Aktualisiertes WorkPackage
    """
    new_status = calculate_work_package_status(work_package, session)
    if work_package.queue_status != new_status:
        validate_status_transition(work_package.queue_status, new_status)
        work_package.queue_status = new_status
        work_package.updated_at = work_package.updated_at
        session.add(work_package)
        session.commit()
        logger.info(
            f"Synced WorkPackage {work_package.id} status to '{new_status}' "
            f"(berechnet aus Tasks)"
        )
    return work_package


def update_task_queue_status(task: Task, new_status: str, session: Session) -> Task:
    """
    Aktualisiert den queue_status eines Tasks und synchronisiert auf Parents.
    
    Args:
        task: Der Task
        new_status: Neuer Status
        session: Datenbank-Session
        
    Returns:
        Aktualisierter Task
    """
    validate_status_transition(task.queue_status, new_status)
    task.queue_status = new_status
    task.updated_at = task.updated_at
    session.add(task)
    session.commit()
    session.refresh(task)
    
    # Parent synchronisieren
    sync_task_status_to_parent(task, session)
    
    logger.info(
        f"Updated Task {task.id} queue_status to '{new_status}' "
        f"(source_type: {task.source_type})"
    )
    return task


def update_work_package_queue_status(
    work_package: WorkPackage, 
    new_status: str, 
    session: Session
) -> WorkPackage:
    """
    Aktualisiert den queue_status eines WorkPackages und synchronisiert auf Requirement.
    
    Args:
        work_package: Das WorkPackage
        new_status: Neuer Status
        session: Datenbank-Session
        
    Returns:
        Aktualisiertes WorkPackage
    """
    validate_status_transition(work_package.queue_status, new_status)
    work_package.queue_status = new_status
    work_package.updated_at = work_package.updated_at
    session.add(work_package)
    session.commit()
    session.refresh(work_package)
    
    # Requirement synchronisieren
    requirement = session.get(Requirement, work_package.requirement_id)
    if requirement:
        sync_requirement_status(requirement, session)
    
    logger.info(f"Updated WorkPackage {work_package.id} queue_status to '{new_status}'")
    return work_package


def update_requirement_queue_status(
    requirement: Requirement, 
    new_status: str, 
    session: Session
) -> Requirement:
    """
    Aktualisiert den queue_status eines Requirements.
    
    Args:
        requirement: Das Requirement
        new_status: Neuer Status
        session: Datenbank-Session
        
    Returns:
        Aktualisiertes Requirement
    """
    validate_status_transition(requirement.queue_status, new_status)
    requirement.queue_status = new_status
    requirement.updated_at = requirement.updated_at
    session.add(requirement)
    session.commit()
    session.refresh(requirement)
    
    logger.info(f"Updated Requirement {requirement.id} queue_status to '{new_status}'")
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
