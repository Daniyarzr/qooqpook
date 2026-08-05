"""payment orders and yookassa method

Revision ID: 002_payment_orders
Revises: 001_initial
Create Date: 2026-08-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_payment_orders"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'yookassa'")

    op.create_table(
        "payment_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "succeeded", "canceled", name="paymentstatus"),
            nullable=False,
        ),
        sa.Column("payment_url", sa.String(length=1024), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id"),
    )
    op.create_index("ix_payment_orders_user_id", "payment_orders", ["user_id"])
    op.create_index("ix_payment_orders_external_id", "payment_orders", ["external_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_orders_external_id", table_name="payment_orders")
    op.drop_index("ix_payment_orders_user_id", table_name="payment_orders")
    op.drop_table("payment_orders")
    op.execute("DROP TYPE IF EXISTS paymentstatus")
