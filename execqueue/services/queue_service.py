from sqlmodel import Session, select
from execqueue.models.requirement import Requirement
from execqueue.models.work_package import WorkPackage
from execqueue.models.task import Task
from execqueue.runtime import apply_test_label


def enqueue_requirement(requirement_id: int, session: Session) -> list[Task]:
    """
    Enqueue all tasks for a requirement.
    
    Creates tasks from work packages or requirement itself.
    """
    requirement = session.get(Requirement, requirement_id)
    if not requirement:
        raise ValueError(f"Requirement {requirement_id} not found")
    
    work_packages = session.exec(
        select(WorkPackage).where(WorkPackage.requirement_id == requirement_id)
    ).all()
    
    tasks = []
    execution_order = 0
    
    if work_packages:
        for wp in sorted(work_packages, key=lambda x: x.execution_order):
            task = Task(
                source_type="work_package",
                source_id=wp.id,
                title=apply_test_label(wp.title),
                prompt=wp.description or f"Implement {wp.title}",
                verification_prompt=requirement.description,
                execution_order=execution_order,
                is_test=True,
            )
            session.add(task)
            tasks.append(task)
            execution_order += 1
    else:
        task = Task(
            source_type="requirement",
            source_id=requirement.id,
            title=apply_test_label(requirement.title),
            prompt=requirement.description or f"Implement {requirement.title}",
            execution_order=execution_order,
            is_test=True,
        )
        session.add(task)
        tasks.append(task)
    
    session.commit()
    return tasks
