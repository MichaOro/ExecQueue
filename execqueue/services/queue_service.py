from sqlmodel import Session, select, or_, and_
from typing import Optional
from execqueue.models.requirement import Requirement
from execqueue.models.work_package import WorkPackage
from execqueue.models.task import Task
from execqueue.runtime import apply_test_label
from execqueue.services.status_sync_service import (
    sync_work_package_status,
    sync_requirement_status,
)
import logging

logger = logging.getLogger(__name__)


def check_queue_blocked(session: Session, is_test: bool) -> bool:
    """Prüft ob die Queue durch einen block_queue Task blockiert ist."""
    blocking_task = session.exec(
        select(Task)
        .where(
            Task.block_queue == True,
            Task.status.in_(["queued", "in_progress"]),
            Task.is_test == is_test,
        )
        .limit(1)
    ).first()
    return blocking_task is not None


def get_parallel_task_count(session: Session, is_test: bool) -> int:
    """Zählt die Anzahl aktuell paralleler Tasks."""
    return session.exec(
        select(Task)
        .where(
            Task.parallelization_allowed == True,
            Task.status.in_(["queued", "in_progress"]),
            Task.is_test == is_test,
        )
    ).count()


def validate_dependencies(work_package: WorkPackage, session: Session) -> bool:
    """
    Prüft ob alle Dependencies eines WorkPackages erfüllt sind.
    
    Args:
        work_package: Das WorkPackage
        session: Datenbank-Session
        
    Returns:
        True wenn alle Dependencies erfüllt (done) sind
    """
    if not work_package.dependency_id:
        return True
    
    dependency = session.get(WorkPackage, work_package.dependency_id)
    if not dependency:
        logger.warning(
            f"Dependency {work_package.dependency_id} für WorkPackage "
            f"{work_package.id} nicht gefunden"
        )
        return False
    
    return dependency.queue_status == "done"


def enqueue_requirement(requirement_id: int, session: Session) -> list[Task]:
    """
    Enqueue all tasks for a requirement.
    
    Creates tasks from work packages or requirement itself.
    Respects queue blocking, dependencies, and parallelization settings.
    """
    requirement = session.get(Requirement, requirement_id)
    if not requirement:
        raise ValueError(f"Requirement {requirement_id} not found")
    
    # Requirement queue_status aktualisieren
    requirement.queue_status = "in_progress"
    requirement.has_work_packages = True
    session.add(requirement)
    
    work_packages = session.exec(
        select(WorkPackage).where(WorkPackage.requirement_id == requirement_id)
    ).all()
    
    tasks = []
    execution_order = 0
    
    if work_packages:
        for wp in sorted(work_packages, key=lambda x: x.execution_order):
            # Dependencies prüfen
            if not validate_dependencies(wp, session):
                logger.info(
                    f"Skipping WorkPackage {wp.id} - dependencies not met"
                )
                continue
            
            task = Task(
                source_type="work_package",
                source_id=wp.id,
                title=apply_test_label(wp.title),
                prompt=wp.implementation_prompt or wp.description or f"Implement {wp.title}",
                verification_prompt=requirement.description,
                execution_order=execution_order,
                is_test=True,
                block_queue=wp.parallelization_enabled == False,  # Blockiert wenn keine Parallelisierung
                parallelization_allowed=wp.parallelization_enabled,
                schedulable=True,
                queue_status="backlog",
            )
            session.add(task)
            tasks.append(task)
            execution_order += 1
            
            # WorkPackage queue_status aktualisieren
            wp.queue_status = "in_progress"
            wp.order_number = execution_order
            session.add(wp)
    else:
        task = Task(
            source_type="requirement",
            source_id=requirement.id,
            title=apply_test_label(requirement.title),
            prompt=requirement.markdown_content or requirement.description or f"Implement {requirement.title}",
            execution_order=execution_order,
            is_test=True,
            block_queue=False,
            parallelization_allowed=True,
            schedulable=True,
            queue_status="backlog",
        )
        session.add(task)
        tasks.append(task)
        requirement.order_number = execution_order
    
    session.commit()
    
    # Requirement status synchronisieren
    sync_requirement_status(requirement, session)
    
    logger.info(
        f"Enqueued {len(tasks)} tasks for requirement {requirement_id}"
    )
    return tasks


def enqueue_work_package(work_package_id: int, session: Session) -> Optional[Task]:
    """
    Enqueue a single task for a work package.
    
    Args:
        work_package_id: ID des WorkPackages
        session: Datenbank-Session
        
    Returns:
        Erstellter Task oder None
    """
    work_package = session.get(WorkPackage, work_package_id)
    if not work_package:
        raise ValueError(f"WorkPackage {work_package_id} not found")
    
    # Dependencies prüfen
    if not validate_dependencies(work_package, session):
        raise ValueError(f"Dependencies not met for WorkPackage {work_package_id}")
    
    requirement = session.get(Requirement, work_package.requirement_id)
    if not requirement:
        raise ValueError(f"Requirement {work_package.requirement_id} not found")
    
    task = Task(
        source_type="work_package",
        source_id=work_package.id,
        title=apply_test_label(work_package.title),
        prompt=work_package.implementation_prompt or work_package.description or f"Implement {work_package.title}",
        verification_prompt=requirement.description,
        execution_order=0,
        is_test=True,
        block_queue=work_package.parallelization_enabled == False,
        parallelization_allowed=work_package.parallelization_enabled,
        schedulable=True,
        queue_status="backlog",
    )
    session.add(task)
    
    work_package.queue_status = "in_progress"
    session.add(work_package)
    
    session.commit()
    session.refresh(task)
    
    logger.info(f"Enqueued task {task.id} for work package {work_package_id}")
    return task
