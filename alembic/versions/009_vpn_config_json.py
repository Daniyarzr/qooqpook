"""vpn config type and default flag

Revision ID: 009_vpn_config_json
Revises: 008_referral_discount
Create Date: 2026-08-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "009_vpn_config_json"
down_revision: Union[str, None] = "008_referral_discount"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

vpn_config_type = postgresql.ENUM(
    "vless_link",
    "xray_json",
    name="vpnconfigtype",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE vpnconfigtype AS ENUM ('vless_link', 'xray_json');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )
    op.add_column(
        "vpn_configs",
        sa.Column(
            "config_type",
            vpn_config_type,
            server_default="xray_json",
            nullable=False,
        ),
    )
    op.add_column(
        "vpn_configs",
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
    )
    op.execute("UPDATE vpn_configs SET config_type = 'vless_link' WHERE config_template LIKE 'vless://%'")

    from src.services.vpn_config_store import export_default_json_template

    template = export_default_json_template()
    conn = op.get_bind()
    servers = conn.execute(sa.text("SELECT id FROM vpn_servers ORDER BY id")).fetchall()
    has_default = conn.execute(
        sa.text("SELECT id FROM vpn_configs WHERE config_type = 'xray_json' AND is_default = true LIMIT 1")
    ).fetchone()
    for (server_id,) in servers:
        existing = conn.execute(
            sa.text(
                "SELECT id FROM vpn_configs "
                "WHERE server_id = :sid AND config_type = 'xray_json' LIMIT 1"
            ),
            {"sid": server_id},
        ).fetchone()
        if existing:
            continue
        make_default = not has_default
        conn.execute(
            sa.text(
                """
                INSERT INTO vpn_configs
                    (server_id, name, config_type, config_template, is_default, is_active, created_at, updated_at)
                VALUES
                    (:sid, 'Xray JSON Profile', 'xray_json', :tpl, :is_default, true, NOW(), NOW())
                """
            ),
            {"sid": server_id, "tpl": template, "is_default": make_default},
        )
        if make_default:
            has_default = True


def downgrade() -> None:
    op.drop_column("vpn_configs", "is_default")
    op.drop_column("vpn_configs", "config_type")
    op.execute("DROP TYPE IF EXISTS vpnconfigtype")
