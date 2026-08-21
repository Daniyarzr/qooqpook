"""subscription expiry reminder tracking

Revision ID: 015_expiry_reminder_sent
Revises: 014_manual_vpn_keys
Create Date: 2026-08-17

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015_expiry_reminder_sent"
down_revision: Union[str, None] = "014_manual_vpn_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("expiry_reminder_sent", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "expiry_reminder_sent")
