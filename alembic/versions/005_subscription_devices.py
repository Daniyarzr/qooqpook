"""subscription devices

Revision ID: 005_subscription_devices
Revises: 004_traffic_usage
Create Date: 2026-08-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_subscription_devices"
down_revision: Union[str, None] = "004_traffic_usage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscription_devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("client_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("bytes_upload", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bytes_download", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("traffic_baseline_upload", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("traffic_baseline_download", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_uuid"),
    )
    op.create_index("ix_subscription_devices_subscription_id", "subscription_devices", ["subscription_id"])

    op.execute(
        """
        INSERT INTO subscription_devices (subscription_id, client_uuid, name)
        SELECT id, client_uuid, 'Устройство 1'
        FROM subscriptions
        """
    )


def downgrade() -> None:
    op.drop_index("ix_subscription_devices_subscription_id", table_name="subscription_devices")
    op.drop_table("subscription_devices")
