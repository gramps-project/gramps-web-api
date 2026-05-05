"""Add trees.config JSON column

Revision ID: b2c3d4e5f6a7
Revises: f3a1c8e92b47
Create Date: 2026-05-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision = "b2c3d4e5f6a7"
down_revision = "f3a1c8e92b47"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col["name"] for col in inspector.get_columns("trees")]
    if "config" in columns:
        return None
    op.add_column("trees", sa.Column("config", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("trees", "config")
