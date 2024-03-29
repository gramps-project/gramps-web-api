"""Add tree column to User

Revision ID: e176543c72a8
Revises: e5e738d09fa7
Create Date: 2023-03-13 13:37:40.620127

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision = "e176543c72a8"
down_revision = "e5e738d09fa7"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col["name"] for col in inspector.get_columns("users")]
    if "tree" in columns:
        # If tree already exists, do nothing
        return None

    op.add_column("users", sa.Column("tree", sa.String(), nullable=True))
    op.create_index(op.f("ix_users_tree"), "users", ["tree"], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_users_tree"), table_name="users")
    op.drop_column("users", "tree")
    # ### end Alembic commands ###
