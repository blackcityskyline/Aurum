"""add llm_settings.harness_type and llm_settings.harness_model

Revision ID: e5f6a7b8c9d0
Revises: d4a7f1c3b9e2
Create Date: 2026-09-23 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4a7f1c3b9e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Which harness driver serves chat — defaults to the existing one so
    # current deployments keep working untouched.
    op.add_column(
        'llm_settings',
        sa.Column('harness_type', sa.String(length=30), nullable=False, server_default='opencode'),
    )
    op.add_column(
        'llm_settings',
        sa.Column('harness_model', sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('llm_settings', 'harness_model')
    op.drop_column('llm_settings', 'harness_type')
