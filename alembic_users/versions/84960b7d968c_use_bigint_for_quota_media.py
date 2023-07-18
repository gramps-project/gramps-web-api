"""Use BigInt for quota_media

Revision ID: 84960b7d968c
Revises: b0582f54029c
Create Date: 2023-07-18 12:10:56.978022

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "84960b7d968c"
down_revision = "b0582f54029c"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column(
            "trees", "quota_media", type_=sa.BigInteger(), existing_type=sa.Integer()
        )


def downgrade():
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column(
            "trees", "quota_media", type_=sa.Integer(), existing_type=sa.BigInteger()
        )
