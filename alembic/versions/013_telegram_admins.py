"""Telegram admins for payment notifications

Revision ID: 013_telegram_admins
Revises: 012_payment_order_purpose
Create Date: 2026-08-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013_telegram_admins"
down_revision: Union[str, None] = "012_payment_order_purpose"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telegram_admins",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_index("ix_telegram_admins_telegram_id", "telegram_admins", ["telegram_id"])


def downgrade() -> None:
    op.drop_index("ix_telegram_admins_telegram_id", table_name="telegram_admins")
    op.drop_table("telegram_admins")
