"""referral deposit bonuses

Revision ID: 011_referral_deposit_bonus
Revises: 010_config_credentials
Create Date: 2026-08-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_referral_deposit_bonus"
down_revision: Union[str, None] = "010_config_credentials"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_referral_pair", "referral_rewards", type_="unique")
    op.add_column(
        "referral_rewards",
        sa.Column("source_transaction_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_referral_rewards_source_transaction_id",
        "referral_rewards",
        "transactions",
        ["source_transaction_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_referral_rewards_source_transaction_id",
        "referral_rewards",
        ["source_transaction_id"],
        unique=True,
    )
    op.execute(
        """
        UPDATE system_settings
        SET key = 'referral_bonus_percent'
        WHERE key = 'referral_discount_percent'
        """
    )
    op.execute(
        """
        INSERT INTO system_settings (key, value)
        SELECT 'referral_bonus_percent', '10'
        WHERE NOT EXISTS (
            SELECT 1 FROM system_settings WHERE key = 'referral_bonus_percent'
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_referral_rewards_source_transaction_id", table_name="referral_rewards")
    op.drop_constraint(
        "fk_referral_rewards_source_transaction_id",
        "referral_rewards",
        type_="foreignkey",
    )
    op.drop_column("referral_rewards", "source_transaction_id")
    op.create_unique_constraint(
        "uq_referral_pair",
        "referral_rewards",
        ["referrer_id", "referred_id"],
    )
    op.execute(
        """
        UPDATE system_settings
        SET key = 'referral_discount_percent'
        WHERE key = 'referral_bonus_percent'
        """
    )
