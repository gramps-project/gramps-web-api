"""empty message

Revision ID: c89728e71264
Revises:
Create Date: 2022-01-11 22:15:39.286700

"""
from alembic import op
import sqlalchemy as sa
import gramps_webapi
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = "c89728e71264"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###

    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()
    if "users" in tables:
        # Don't do anything if user table already exists!
        return None

    op.create_table(
        "users",
        sa.Column("id", gramps_webapi.auth.sql_guid.GUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("fullname", sa.String(), nullable=True),
        sa.Column("pwhash", sa.String(), nullable=False),
        sa.Column("role", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("name"),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("users")
    # ### end Alembic commands ###
