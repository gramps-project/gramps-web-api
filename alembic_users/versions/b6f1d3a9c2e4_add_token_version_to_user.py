"""Add token_version column to User

Revision ID: b6f1d3a9c2e4
Revises: 9c4d2e7a5b18
Create Date: 2026-10-28 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision = "b6f1d3a9c2e4"
down_revision = "9c4d2e7a5b18"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col["name"] for col in inspector.get_columns("users")]
    if "token_version" in columns:
        return None

    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("users", "token_version")
