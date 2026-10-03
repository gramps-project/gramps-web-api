"""Allow several labelled access tokens per user and scope

Sync tokens are used one per device, and each device needs its own token so
that it can be revoked on its own. The unique constraint on (user_id, scope)
is replaced by one on (user_id, scope, label); scopes with a single token per
user keep using an empty label. Also record when a token was last used.

Revision ID: 7b2e9f4c1a63
Revises: d4e9a1c7b3f2
Create Date: 2026-10-03 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision = "7b2e9f4c1a63"
down_revision = "d4e9a1c7b3f2"
branch_labels = None
depends_on = None

TABLE = "access_tokens"
OLD_CONSTRAINT = "uq_access_tokens_user_scope"
OLD_COLUMNS = ["user_id", "scope"]
NEW_CONSTRAINT = "uq_access_tokens_user_scope_label"
NEW_COLUMNS = ["user_id", "scope", "label"]
# lets batch mode refer to a constraint if SQLite reflects it without a name
NAMING_CONVENTION = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def _unique_constraint_name(
    inspector: Inspector, columns: list[str], default: str
) -> str | None:
    """Return the name of the unique constraint on columns, or None if absent."""
    for constraint in inspector.get_unique_constraints(TABLE):
        if list(constraint["column_names"]) == columns:
            return constraint["name"] or default
    return None


def upgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    columns = {column["name"] for column in inspector.get_columns(TABLE)}
    old_name = _unique_constraint_name(inspector, OLD_COLUMNS, OLD_CONSTRAINT)
    has_new = _unique_constraint_name(inspector, NEW_COLUMNS, NEW_CONSTRAINT)
    with op.batch_alter_table(TABLE, naming_convention=NAMING_CONVENTION) as batch_op:
        if "label" not in columns:
            batch_op.add_column(
                sa.Column(
                    "label", sa.String(length=100), nullable=False, server_default=""
                )
            )
        if "last_used_at" not in columns:
            batch_op.add_column(sa.Column("last_used_at", sa.DateTime(), nullable=True))
        if old_name:
            batch_op.drop_constraint(old_name, type_="unique")
        if not has_new:
            batch_op.create_unique_constraint(NEW_CONSTRAINT, NEW_COLUMNS)


def downgrade():
    bind = op.get_bind()
    # the old schema allows a single token per user and scope, so labelled
    # tokens (one per device) can't be kept
    bind.execute(sa.text(f"DELETE FROM {TABLE} WHERE label != ''"))
    inspector = Inspector.from_engine(bind)
    new_name = _unique_constraint_name(inspector, NEW_COLUMNS, NEW_CONSTRAINT)
    with op.batch_alter_table(TABLE, naming_convention=NAMING_CONVENTION) as batch_op:
        if new_name:
            batch_op.drop_constraint(new_name, type_="unique")
        batch_op.create_unique_constraint(OLD_CONSTRAINT, OLD_COLUMNS)
        batch_op.drop_column("last_used_at")
        batch_op.drop_column("label")
