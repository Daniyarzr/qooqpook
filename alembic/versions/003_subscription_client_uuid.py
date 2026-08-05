"""subscription client_uuid

Revision ID: 003_subscription_client_uuid
Revises: 002_payment_orders
Create Date: 2026-08-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_subscription_client_uuid"
down_revision: Union[str, None] = "002_payment_orders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("client_uuid", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Unique UUID per subscription row
    op.execute("UPDATE subscriptions SET client_uuid = gen_random_uuid() WHERE client_uuid IS NULL")

    # Keep current VPN access: active/trial subs inherit the user's existing UUID
    op.execute(
        """
        UPDATE subscriptions AS s
        SET client_uuid = u.client_uuid
        FROM users AS u
        WHERE s.user_id = u.id
          AND s.id IN (
              SELECT DISTINCT ON (user_id) id
              FROM subscriptions
              WHERE status IN ('active', 'trial')
              ORDER BY user_id, expires_at DESC
          )
        """
    )

    op.alter_column("subscriptions", "client_uuid", nullable=False)
    op.create_unique_constraint("uq_subscriptions_client_uuid", "subscriptions", ["client_uuid"])
    op.create_index("ix_subscriptions_client_uuid", "subscriptions", ["client_uuid"])


def downgrade() -> None:
    op.drop_index("ix_subscriptions_client_uuid", table_name="subscriptions")
    op.drop_constraint("uq_subscriptions_client_uuid", "subscriptions", type_="unique")
    op.drop_column("subscriptions", "client_uuid")
