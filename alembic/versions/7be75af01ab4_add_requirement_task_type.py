"""add_requirement_task_type

Revision ID: 7be75af01ab4
Revises: 99d5a553d696
Create Date: 2026-04-28

REQ-011: Add 'requirement' as a valid task type
"""

from alembic import op
import sqlalchemy as sa


revision = '7be75af01ab4'
down_revision = '99d5a553d696'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop existing check constraint first
    op.execute("ALTER TABLE task DROP CONSTRAINT IF EXISTS ck_task_type_allowed")
    
    # Create new constraint with requirement type
    op.execute(
        "ALTER TABLE task ADD CONSTRAINT ck_task_type_allowed "
        "CHECK (type IN ('planning', 'execution', 'analysis', 'requirement'))"
    )


def downgrade() -> None:
    # Drop existing check constraint
    op.execute("ALTER TABLE task DROP CONSTRAINT IF EXISTS ck_task_type_allowed")
    
    # Restore original constraint without requirement
    op.execute(
        "ALTER TABLE task ADD CONSTRAINT ck_task_type_allowed "
        "CHECK (type IN ('planning', 'execution', 'analysis'))"
    )
