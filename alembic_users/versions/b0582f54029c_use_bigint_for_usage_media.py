"""Use BigInt for usage_media

Revision ID: b0582f54029c
Revises: 22c8d1fba959
Create Date: 2023-07-18 11:28:14.327541

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b0582f54029c"
down_revision = "22c8d1fba959"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column(
            "trees", "usage_media", type_=sa.BigInteger(), existing_type=sa.Integer()
        )


def downgrade():
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column(
            "trees", "usage_media", type_=sa.Integer(), existing_type=sa.BigInteger()
        )
