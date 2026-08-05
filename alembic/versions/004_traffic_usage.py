"""traffic usage fields

Revision ID: 004_traffic_usage
Revises: 003_subscription_client_uuid
Create Date: 2026-08-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_traffic_usage"
down_revision: Union[str, None] = "003_subscription_client_uuid"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscription_plans",
        sa.Column("traffic_limit_gb", sa.Integer(), nullable=True),
    )

    op.add_column(
        "subscriptions",
        sa.Column("bytes_upload", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "subscriptions",
        sa.Column("bytes_download", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "subscriptions",
        sa.Column("traffic_baseline_upload", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "subscriptions",
        sa.Column("traffic_baseline_download", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "subscriptions",
        sa.Column("last_traffic_sync_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "last_traffic_sync_at")
    op.drop_column("subscriptions", "traffic_baseline_download")
    op.drop_column("subscriptions", "traffic_baseline_upload")
    op.drop_column("subscriptions", "bytes_download")
    op.drop_column("subscriptions", "bytes_upload")
    op.drop_column("subscription_plans", "traffic_limit_gb")
