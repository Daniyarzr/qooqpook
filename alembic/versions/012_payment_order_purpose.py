"""payment order purpose and subscription purchase fields

Revision ID: 012_payment_order_purpose
Revises: 011_referral_deposit_bonus
Create Date: 2026-08-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_payment_order_purpose"
down_revision: Union[str, None] = "011_referral_deposit_bonus"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE paymentorderpurpose AS ENUM ('deposit', 'subscription')")

    op.add_column(
        "payment_orders",
        sa.Column(
            "purpose",
            sa.Enum("deposit", "subscription", name="paymentorderpurpose"),
            nullable=False,
            server_default="deposit",
        ),
    )
    op.add_column("payment_orders", sa.Column("plan_id", sa.Integer(), nullable=True))
    op.add_column("payment_orders", sa.Column("promo_code_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_payment_orders_plan_id",
        "payment_orders",
        "subscription_plans",
        ["plan_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_payment_orders_promo_code_id",
        "payment_orders",
        "promo_codes",
        ["promo_code_id"],
        ["id"],
    )
    op.create_index("ix_payment_orders_plan_id", "payment_orders", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_orders_plan_id", table_name="payment_orders")
    op.drop_constraint("fk_payment_orders_promo_code_id", "payment_orders", type_="foreignkey")
    op.drop_constraint("fk_payment_orders_plan_id", "payment_orders", type_="foreignkey")
    op.drop_column("payment_orders", "promo_code_id")
    op.drop_column("payment_orders", "plan_id")
    op.drop_column("payment_orders", "purpose")
    op.execute("DROP TYPE IF EXISTS paymentorderpurpose")
