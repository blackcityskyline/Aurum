"""add llm_settings, llm_providers and chat_messages.reasoning

Revision ID: d4a7f1c3b9e2
Revises: a1b2c3d4e5f6
Create Date: 2026-09-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a7f1c3b9e2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'llm_providers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('base_url', sa.String(length=300), nullable=False),
        sa.Column('api_key', sa.String(length=500), nullable=True),
        sa.Column('model', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'llm_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mode', sa.String(length=20), nullable=False),
        sa.Column('harness_url', sa.String(length=300), nullable=False),
        sa.Column('active_provider_id', sa.Integer(), nullable=True),
        sa.Column('max_tokens', sa.Integer(), nullable=False),
        sa.Column('temperature', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ['active_provider_id'], ['llm_providers.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.add_column('chat_messages', sa.Column('reasoning', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('chat_messages', 'reasoning')
    op.drop_table('llm_settings')
    op.drop_table('llm_providers')
