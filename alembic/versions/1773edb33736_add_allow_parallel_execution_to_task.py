"""add_allow_parallel_execution_to_task"""

revision = '1773edb33736'
down_revision = '7be75af01ab4'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa



def upgrade() -> None:
    op.add_column(
        "task",
        sa.Column(
            "allow_parallel_execution",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("task", "allow_parallel_execution")
