"""system settings and referral welcome flag

Revision ID: 008_referral_discount
Revises: 007_promo_codes
Create Date: 2026-08-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_referral_discount"
down_revision: Union[str, None] = "007_promo_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.execute(
        "INSERT INTO system_settings (key, value) VALUES ('referral_discount_percent', '10')"
    )

    op.add_column(
        "users",
        sa.Column(
            "referral_discount_used",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "referral_discount_used")
    op.drop_table("system_settings")
