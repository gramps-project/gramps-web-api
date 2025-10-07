"""add oidc_accounts table for secure provider_id and subject_id mapping

Revision ID: 2082445b0769
Revises: a8e57fe0d82e
Create Date: 2025-09-28 17:21:49.676157

"""
from alembic import op
import sqlalchemy as sa
from gramps_webapi.auth.sql_guid import GUID


# revision identifiers, used by Alembic.
revision = '2082445b0769'
down_revision = 'a8e57fe0d82e'
branch_labels = None
depends_on = None


def upgrade():
    # Create oidc_accounts table for secure provider_id and subject_id mapping
    op.create_table(
        'oidc_accounts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', GUID(), nullable=False),
        sa.Column('provider_id', sa.String(64), nullable=False),
        sa.Column('subject_id', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('provider_id', 'subject_id', name='uq_oidc_provider_subject'),
        sa.Index('ix_oidc_accounts_user_id', 'user_id'),
        sa.Index('ix_oidc_accounts_email', 'email'),
    )


def downgrade():
    # Drop oidc_accounts table
    op.drop_table('oidc_accounts')
