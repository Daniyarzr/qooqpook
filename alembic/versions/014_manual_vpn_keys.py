"""manual vpn keys for admin panel

Revision ID: 014_manual_vpn_keys
Revises: 013_telegram_admins
Create Date: 2026-08-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "014_manual_vpn_keys"
down_revision: Union[str, None] = "013_telegram_admins"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "manual_vpn_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("server_id", sa.Integer(), nullable=False),
        sa.Column("client_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["server_id"], ["vpn_servers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_uuid"),
    )
    op.create_index("ix_manual_vpn_keys_server_id", "manual_vpn_keys", ["server_id"])


def downgrade() -> None:
    op.drop_index("ix_manual_vpn_keys_server_id", table_name="manual_vpn_keys")
    op.drop_table("manual_vpn_keys")
