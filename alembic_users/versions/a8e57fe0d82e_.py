"""empty message

Revision ID: a8e57fe0d82e
Revises: 84960b7d968c
Create Date: 2024-09-03 18:48:00.917543

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8e57fe0d82e'
down_revision = '84960b7d968c'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('trees', sa.Column('quota_ai', sa.Integer(), nullable=True))
    op.add_column('trees', sa.Column('usage_ai', sa.Integer(), nullable=True))
    op.alter_column('trees', 'quota_media',
               existing_type=sa.INTEGER(),
               type_=sa.BigInteger(),
               existing_nullable=True)
    op.alter_column('trees', 'usage_media',
               existing_type=sa.INTEGER(),
               type_=sa.BigInteger(),
               existing_nullable=True)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('trees', 'usage_media',
               existing_type=sa.BigInteger(),
               type_=sa.INTEGER(),
               existing_nullable=True)
    op.alter_column('trees', 'quota_media',
               existing_type=sa.BigInteger(),
               type_=sa.INTEGER(),
               existing_nullable=True)
    op.drop_column('trees', 'usage_ai')
    op.drop_column('trees', 'quota_ai')
    # ### end Alembic commands ###