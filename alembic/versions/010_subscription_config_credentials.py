"""subscription config credentials — unique UUID per device and VPN config

Revision ID: 010_config_credentials
Revises: 009_vpn_config_json
Create Date: 2026-08-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010_config_credentials"
down_revision: Union[str, None] = "009_vpn_config_json"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscription_config_credentials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("vpn_config_id", sa.Integer(), nullable=False),
        sa.Column("client_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["device_id"], ["subscription_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vpn_config_id"], ["vpn_configs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subscription_id",
            "device_id",
            "vpn_config_id",
            name="uq_subscription_config_credential",
        ),
        sa.UniqueConstraint("client_uuid"),
    )
    op.create_index(
        "ix_subscription_config_credentials_subscription_id",
        "subscription_config_credentials",
        ["subscription_id"],
    )
    op.create_index(
        "ix_subscription_config_credentials_client_uuid",
        "subscription_config_credentials",
        ["client_uuid"],
    )

    op.execute(
        """
        INSERT INTO subscription_config_credentials
            (subscription_id, device_id, vpn_config_id, client_uuid, created_at)
        SELECT
            d.subscription_id,
            d.id,
            c.id,
            gen_random_uuid(),
            NOW()
        FROM subscription_devices d
        JOIN subscriptions s ON s.id = d.subscription_id
        JOIN vpn_configs c ON c.is_active = true
        JOIN vpn_servers srv ON srv.id = c.server_id
        WHERE srv.id = COALESCE(
            (SELECT vc.server_id FROM vpn_configs vc WHERE vc.id = s.config_id),
            (SELECT id FROM vpn_servers WHERE is_active = true ORDER BY sort_order, id LIMIT 1)
        )
        AND c.server_id = COALESCE(
            (SELECT vc.server_id FROM vpn_configs vc WHERE vc.id = s.config_id),
            (SELECT id FROM vpn_servers WHERE is_active = true ORDER BY sort_order, id LIMIT 1)
        )
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_subscription_config_credentials_client_uuid",
        table_name="subscription_config_credentials",
    )
    op.drop_index(
        "ix_subscription_config_credentials_subscription_id",
        table_name="subscription_config_credentials",
    )
    op.drop_table("subscription_config_credentials")
