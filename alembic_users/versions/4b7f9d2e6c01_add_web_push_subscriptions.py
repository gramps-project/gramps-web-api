"""add Web Push subscriptions table

Revision ID: 4b7f9d2e6c01
Revises: d4e9a1c7b3f2
Create Date: 2026-09-22 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

from gramps_webapi.auth.sql_guid import GUID

# revision identifiers, used by Alembic.
revision = "4b7f9d2e6c01"
down_revision = "d4e9a1c7b3f2"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "push_subscriptions" in Inspector.from_engine(bind).get_table_names():
        return None
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("endpoint_hash", sa.String(length=64), nullable=False),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column("expiration_time", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_push_subscriptions_user_id",
        "push_subscriptions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_push_subscriptions_endpoint_hash",
        "push_subscriptions",
        ["endpoint_hash"],
        unique=True,
    )


def downgrade():
    op.drop_index(
        "ix_push_subscriptions_endpoint_hash", table_name="push_subscriptions"
    )
    op.drop_index("ix_push_subscriptions_user_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
