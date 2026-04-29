"""Add task_tree table

Revision ID: f3a1c8e92b47
Revises: 2082445b0769
Create Date: 2026-04-27 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision = "f3a1c8e92b47"
down_revision = "2082445b0769"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    if "task_tree" in inspector.get_table_names():
        return None

    op.create_table(
        "task_tree",
        sa.Column("task_id", sa.String(155), nullable=False),
        sa.Column("tree", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.create_index("ix_task_tree_tree", "task_tree", ["tree"])
    op.create_index("ix_task_tree_user_id", "task_tree", ["user_id"])
    # Composite index for the primary list query (filter by tree, order by created_at)
    # and for the periodic purge (filter by created_at).
    op.create_index(
        "ix_task_tree_tree_created_at", "task_tree", ["tree", "created_at"]
    )


def downgrade():
    op.drop_index("ix_task_tree_tree_created_at", table_name="task_tree")
    op.drop_index("ix_task_tree_user_id", table_name="task_tree")
    op.drop_index("ix_task_tree_tree", table_name="task_tree")
    op.drop_table("task_tree")
