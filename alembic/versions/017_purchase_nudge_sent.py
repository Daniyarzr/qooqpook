"""track last purchase reminder sent to a user

Revision ID: 017_purchase_nudge_sent
Revises: 016_partner_links
Create Date: 2026-10-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017_purchase_nudge_sent"
down_revision: Union[str, None] = "016_partner_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("purchase_nudge_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "purchase_nudge_sent_at")
