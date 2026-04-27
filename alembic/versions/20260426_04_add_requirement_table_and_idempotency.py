"""Add requirement table and task idempotency columns.

Revision ID: 20260426_04
Revises: 20260426_03
Create Date: 2026-04-27

This migration implements AP 2 - Persistenzmodell, Constraints und Idempotenz absichern:
- Creates the requirement table for intake artifacts
- Adds requirement_id foreign key to task table
- Adds idempotency_key column for duplicate prevention
- Adds indices for efficient querying
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260426_04"
down_revision = "20260426_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create requirement table
    op.create_table(
        "requirement",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'approved', 'rejected', 'archived')",
            name=op.f("ck_requirement_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_requirement_project_id_project"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requirement")),
    )

    # Add requirement_id and idempotency_key columns to task table
    # Using nullable=True initially to allow migration of existing data
    op.add_column("task", sa.Column("requirement_id", sa.Uuid(), nullable=True))
    op.add_column(
        "task",
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
    )

    # Create constraints using batch mode for SQLite compatibility
    # This allows the migration to work on both SQLite and PostgreSQL
    with op.batch_alter_table("task") as batch_op:
        batch_op.create_foreign_key(
            op.f("fk_task_requirement_id_requirement"),
            "requirement",
            ["requirement_id"],
            ["id"],
        )
        batch_op.create_unique_constraint(
            op.f("uq_task_idempotency_key"),
            ["idempotency_key"],
        )

    # Create indices for efficient querying
    op.create_index(op.f("ix_task_type"), "task", ["type"], unique=False)
    op.create_index(
        op.f("ix_task_requirement_id"),
        "task",
        ["requirement_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_requirement_project_id"),
        "requirement",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_requirement_status"),
        "requirement",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    # Drop indices
    op.drop_index(op.f("ix_requirement_status"), table_name="requirement")
    op.drop_index(op.f("ix_requirement_project_id"), table_name="requirement")
    op.drop_index(op.f("ix_task_requirement_id"), table_name="task")
    op.drop_index(op.f("ix_task_type"), table_name="task")

    # Drop constraints using batch mode for SQLite compatibility
    with op.batch_alter_table("task") as batch_op:
        batch_op.drop_constraint(op.f("uq_task_idempotency_key"), type_="unique")
        batch_op.drop_constraint(
            op.f("fk_task_requirement_id_requirement"),
            type_="foreignkey",
        )

    # Drop columns
    op.drop_column("task", "idempotency_key")
    op.drop_column("task", "requirement_id")

    # Drop requirement table
    op.drop_table("requirement")
