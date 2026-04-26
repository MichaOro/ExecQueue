"""Create telegram users table."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260426_02"
down_revision = "20260426_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("telegram_id", sa.BIGINT(), nullable=False),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=32), server_default="user", nullable=False),
        sa.Column("subscribed_events", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_active", sa.DateTime(timezone=True), nullable=True),
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
            "role IN ('user', 'operator', 'admin')",
            name=op.f("ck_telegram_users_telegram_users_role_allowed"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telegram_users")),
        sa.UniqueConstraint("telegram_id", name=op.f("uq_telegram_users_telegram_id")),
    )


def downgrade() -> None:
    op.drop_table("telegram_users")
