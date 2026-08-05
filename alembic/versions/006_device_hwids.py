"""device hwid tracking and suspension reason

Revision ID: 006_device_hwids
Revises: 005_subscription_devices
Create Date: 2026-08-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_device_hwids"
down_revision: Union[str, None] = "005_subscription_devices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("suspension_reason", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("device_limit_notified_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "subscription_hwids",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("hwid", sa.String(length=128), nullable=False),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_id", "hwid", name="uq_subscription_hwid"),
    )
    op.create_index("ix_subscription_hwids_subscription_id", "subscription_hwids", ["subscription_id"])


def downgrade() -> None:
    op.drop_index("ix_subscription_hwids_subscription_id", table_name="subscription_hwids")
    op.drop_table("subscription_hwids")
    op.drop_column("subscriptions", "device_limit_notified_at")
    op.drop_column("subscriptions", "suspension_reason")
