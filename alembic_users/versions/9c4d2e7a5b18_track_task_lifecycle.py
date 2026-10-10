"""Track the task lifecycle in task_tree

The user database becomes the source of truth for task state, progress and
result, and enforces one active task per tree and lock key (see
gramps_webapi/util/task_state.py). Rows recorded before this migration get the
status "unknown"; their state is still read from the Celery result backend.

Revision ID: 9c4d2e7a5b18
Revises: 7b2e9f4c1a63
Create Date: 2026-10-09 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision = "9c4d2e7a5b18"
down_revision = "7b2e9f4c1a63"
branch_labels = None
depends_on = None

TABLE = "task_tree"
CONSTRAINT = "uq_task_tree_tree_lock_key"


def _columns() -> list[sa.Column]:
    """Return the added columns (a column can only be attached to one table)."""
    return [
        sa.Column("status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("lock_key", sa.String(64), nullable=True),
        sa.Column("rerun", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
    ]


def upgrade():
    inspector = Inspector.from_engine(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns(TABLE)}
    has_constraint = any(
        constraint["name"] == CONSTRAINT
        for constraint in inspector.get_unique_constraints(TABLE)
    )
    with op.batch_alter_table(TABLE) as batch_op:
        for column in _columns():
            if column.name not in existing:
                batch_op.add_column(column)
        if not has_constraint:
            batch_op.create_unique_constraint(CONSTRAINT, ["tree", "lock_key"])


def downgrade():
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.drop_constraint(CONSTRAINT, type_="unique")
        for column in reversed(_columns()):
            batch_op.drop_column(column.name)
