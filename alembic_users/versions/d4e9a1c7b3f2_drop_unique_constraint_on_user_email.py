"""Drop the unique constraint on users.email

Nothing identifies a user by e-mail address: login, password reset and e-mail
confirmation all key off the username. The constraint only made legitimate
setups impossible - a person with an account in two trees, or a household
sharing one mailbox - so it is replaced by a plain index.

Revision ID: d4e9a1c7b3f2
Revises: 6d8f3cb50b71
Create Date: 2026-08-28 00:00:00.000000

"""

from typing import Optional, Tuple

from alembic import op
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision = "d4e9a1c7b3f2"
down_revision = "6d8f3cb50b71"
branch_labels = None
depends_on = None

# SQLite reflects the constraint without a name, so batch mode needs a
# convention to be able to refer to it. On other dialects batch mode is a
# pass-through and the reflected name is used as is.
NAMING_CONVENTION = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
CONSTRAINT_NAME = "uq_users_email"
INDEX_NAME = "ix_users_email"


def _email_unique_constraint(inspector: Inspector) -> Tuple[bool, Optional[str]]:
    """Return whether users.email has a unique constraint, and its name."""
    for constraint in inspector.get_unique_constraints("users"):
        if list(constraint["column_names"]) == ["email"]:
            return True, constraint["name"]
    return False, None


def _has_index(inspector: Inspector, name: str) -> bool:
    """Return whether the users table has an index of that name."""
    return any(index["name"] == name for index in inspector.get_indexes("users"))


def upgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    exists, name = _email_unique_constraint(inspector)
    if exists:
        with op.batch_alter_table(
            "users", naming_convention=NAMING_CONVENTION
        ) as batch_op:
            batch_op.drop_constraint(name or CONSTRAINT_NAME, type_="unique")
    # dropping the constraint drops the index that backed it
    if not _has_index(Inspector.from_engine(bind), INDEX_NAME):
        op.create_index(op.f(INDEX_NAME), "users", ["email"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    if _has_index(inspector, INDEX_NAME):
        op.drop_index(op.f(INDEX_NAME), table_name="users")
    exists, _ = _email_unique_constraint(inspector)
    if not exists:
        # fails if duplicate addresses have been stored in the meantime
        with op.batch_alter_table(
            "users", naming_convention=NAMING_CONVENTION
        ) as batch_op:
            batch_op.create_unique_constraint(CONSTRAINT_NAME, ["email"])
