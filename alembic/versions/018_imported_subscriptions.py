"""external subscription import

Revision ID: 018_imported_subscriptions
Revises: 017_purchase_nudge_sent
Create Date: 2026-10-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018_imported_subscriptions"
down_revision: Union[str, None] = "017_purchase_nudge_sent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "imported_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "imported_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("remark", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("is_alive", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_ping_ms", sa.Integer(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["imported_subscriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "fingerprint", name="uq_imported_config_fp"),
    )
    op.create_index("ix_imported_configs_source_id", "imported_configs", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_imported_configs_source_id", table_name="imported_configs")
    op.drop_table("imported_configs")
    op.drop_table("imported_subscriptions")
