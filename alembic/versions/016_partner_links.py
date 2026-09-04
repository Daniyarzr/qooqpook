"""partner acquisition links

Revision ID: 016_partner_links
Revises: 015_expiry_reminder_sent
Create Date: 2026-09-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016_partner_links"
down_revision: Union[str, None] = "015_expiry_reminder_sent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "partner_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("telegram_username", sa.String(length=255), nullable=True),
        sa.Column("note", sa.String(length=512), nullable=True),
        sa.Column("click_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_partner_links_code", "partner_links", ["code"])

    op.add_column(
        "users",
        sa.Column("partner_link_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_users_partner_link_id", "users", ["partner_link_id"])
    op.create_foreign_key(
        "fk_users_partner_link_id",
        "users",
        "partner_links",
        ["partner_link_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_partner_link_id", "users", type_="foreignkey")
    op.drop_index("ix_users_partner_link_id", table_name="users")
    op.drop_column("users", "partner_link_id")
    op.drop_index("ix_partner_links_code", table_name="partner_links")
    op.drop_table("partner_links")
