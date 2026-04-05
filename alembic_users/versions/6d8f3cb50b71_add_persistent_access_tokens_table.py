"""add persistent access tokens table

Revision ID: 6d8f3cb50b71
Revises: 2082445b0769
Create Date: 2026-03-31 00:25:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

from gramps_webapi.auth.sql_guid import GUID


# revision identifiers, used by Alembic.
revision = "6d8f3cb50b71"
down_revision = "2082445b0769"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()
    if "access_tokens" in tables:
        # If table already exists, do nothing
        return None

    op.create_table(
        "access_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("token", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "scope", name="uq_access_tokens_user_scope"),
    )
    op.create_index("ix_access_tokens_user_id", "access_tokens", ["user_id"], unique=False)
    op.create_index("ix_access_tokens_scope", "access_tokens", ["scope"], unique=False)
    op.create_index("ix_access_tokens_token", "access_tokens", ["token"], unique=True)


def downgrade():
    op.drop_index("ix_access_tokens_token", table_name="access_tokens")
    op.drop_index("ix_access_tokens_scope", table_name="access_tokens")
    op.drop_index("ix_access_tokens_user_id", table_name="access_tokens")
    op.drop_table("access_tokens")
