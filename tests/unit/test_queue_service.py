import pytest
from sqlmodel import Session, select
from execqueue.services.queue_service import enqueue_requirement
from execqueue.models.requirement import Requirement
from execqueue.models.work_package import WorkPackage
from execqueue.models.task import Task


class TestEnqueueRequirement:
    """Tests for enqueue_requirement function in queue_service."""

    def test_enqueue_requirement_with_work_packages(
        self, db_session: Session, sample_requirement
    ):
        """Test: enqueue_requirement creates tasks for each work package."""
        work_packages = [
            WorkPackage(
                requirement_id=sample_requirement.id,
                title=f"WP {i}",
                description=f"Description {i}",
                execution_order=i,
                implementation_prompt=f"Prompt {i}",
                verification_prompt=f"Verify {i}",
            )
            for i in range(3)
        ]
        db_session.add_all(work_packages)
        db_session.commit()

        tasks = enqueue_requirement(sample_requirement.id, db_session)

        assert len(tasks) == 3
        for i, task in enumerate(tasks):
            assert task.source_type == "work_package"
            assert task.source_id == work_packages[i].id
            assert task.execution_order == i
            assert task.status == "queued"
            assert task.prompt == f"Prompt {i}"
            assert task.verification_prompt == f"Verify {i}"

        refreshed_requirement = db_session.get(Requirement, sample_requirement.id)
        assert refreshed_requirement.status == "planned"

    def test_enqueue_requirement_without_work_packages(
        self, db_session: Session, sample_requirement
    ):
        """Test: enqueue_requirement creates single task from requirement."""
        tasks = enqueue_requirement(sample_requirement.id, db_session)

        assert len(tasks) == 1
        task = tasks[0]
        assert task.source_type == "requirement"
        assert task.source_id == sample_requirement.id
        assert task.prompt == sample_requirement.markdown_content
        assert task.status == "queued"
        assert task.execution_order == 0

        refreshed_requirement = db_session.get(Requirement, sample_requirement.id)
        assert refreshed_requirement.status == "planned"

    def test_enqueue_requirement_nonexistent_requirement(
        self, db_session: Session
    ):
        """Test: enqueue_requirement raises ValueError for non-existent requirement."""
        with pytest.raises(ValueError, match="Requirement not found"):
            enqueue_requirement(9999, db_session)

    def test_enqueue_requirement_workpackage_prompt_priority(
        self, db_session: Session, sample_requirement
    ):
        """Test: WorkPackage implementation_prompt takes priority over description."""
        wp = WorkPackage(
            requirement_id=sample_requirement.id,
            title="WP with both",
            description="This is the description",
            implementation_prompt="This is the implementation prompt",
            execution_order=0,
        )
        db_session.add(wp)
        db_session.commit()

        tasks = enqueue_requirement(sample_requirement.id, db_session)

        assert len(tasks) == 1
        assert tasks[0].prompt == "This is the implementation prompt"

    def test_enqueue_requirement_workpackage_fallback_to_description(
        self, db_session: Session, sample_requirement
    ):
        """Test: Task uses description when implementation_prompt is None."""
        wp = WorkPackage(
            requirement_id=sample_requirement.id,
            title="WP without implementation_prompt",
            description="This is the fallback description",
            implementation_prompt=None,
            execution_order=0,
        )
        db_session.add(wp)
        db_session.commit()

        tasks = enqueue_requirement(sample_requirement.id, db_session)

        assert len(tasks) == 1
        assert tasks[0].prompt == "This is the fallback description"

    def test_enqueue_requirement_verification_prompt_workpackage_priority(
        self, db_session: Session, sample_requirement
    ):
        """Test: WorkPackage verification_prompt takes priority."""
        sample_requirement.verification_prompt = "Requirement verification"
        db_session.add(sample_requirement)
        db_session.commit()

        wp = WorkPackage(
            requirement_id=sample_requirement.id,
            title="WP with verification",
            description="Description",
            verification_prompt="WorkPackage verification",
            execution_order=0,
        )
        db_session.add(wp)
        db_session.commit()

        tasks = enqueue_requirement(sample_requirement.id, db_session)

        assert len(tasks) == 1
        assert tasks[0].verification_prompt == "WorkPackage verification"

    def test_enqueue_requirement_verification_prompt_requirement_fallback(
        self, db_session: Session, sample_requirement
    ):
        """Test: Task uses requirement verification_prompt when WP has none."""
        sample_requirement.verification_prompt = "Requirement verification"
        db_session.add(sample_requirement)
        db_session.commit()

        wp = WorkPackage(
            requirement_id=sample_requirement.id,
            title="WP without verification",
            description="Description",
            verification_prompt=None,
            execution_order=0,
        )
        db_session.add(wp)
        db_session.commit()

        tasks = enqueue_requirement(sample_requirement.id, db_session)

        assert len(tasks) == 1
        assert tasks[0].verification_prompt == "Requirement verification"

    def test_enqueue_requirement_execution_order_preserved(
        self, db_session: Session, sample_requirement
    ):
        """Test: Tasks maintain WorkPackage execution_order."""
        work_packages = [
            WorkPackage(
                requirement_id=sample_requirement.id,
                title=f"WP {i}",
                description=f"Description {i}",
                execution_order=order,
            )
            for i, order in enumerate([5, 2, 8, 1])
        ]
        db_session.add_all(work_packages)
        db_session.commit()

        tasks = enqueue_requirement(sample_requirement.id, db_session)

        assert len(tasks) == 4
        assert tasks[0].execution_order == 1
        assert tasks[1].execution_order == 2
        assert tasks[2].execution_order == 5
        assert tasks[3].execution_order == 8
