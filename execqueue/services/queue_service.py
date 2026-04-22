from sqlmodel import Session, select

from execqueue.models.requirement import Requirement
from execqueue.models.work_package import WorkPackage
from execqueue.models.task import Task


def enqueue_requirement(requirement_id: int, session: Session) -> list[Task]:
    requirement = session.get(Requirement, requirement_id)
    if not requirement:
        raise ValueError("Requirement not found")

    work_packages = session.exec(
        select(WorkPackage)
        .where(WorkPackage.requirement_id == requirement_id)
        .order_by(WorkPackage.execution_order, WorkPackage.id)
    ).all()

    created_tasks: list[Task] = []

    if work_packages:
        for wp in work_packages:
            prompt = wp.implementation_prompt or wp.description
            verification_prompt = wp.verification_prompt or requirement.verification_prompt

            task = Task(
                source_type="work_package",
                source_id=wp.id,
                title=wp.title,
                prompt=prompt,
                verification_prompt=verification_prompt,
                execution_order=wp.execution_order,
                status="queued",
            )
            session.add(task)
            created_tasks.append(task)
    else:
        prompt = requirement.markdown_content
        verification_prompt = requirement.verification_prompt

        task = Task(
            source_type="requirement",
            source_id=requirement.id,
            title=requirement.title,
            prompt=prompt,
            verification_prompt=verification_prompt,
            execution_order=0,
            status="queued",
        )
        session.add(task)
        created_tasks.append(task)

    requirement.status = "planned"
    session.add(requirement)

    session.commit()

    for task in created_tasks:
        session.refresh(task)

    return created_tasks