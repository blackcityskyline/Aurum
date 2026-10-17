"""make chat_attachments.message_id nullable

An attachment is uploaded before the chat message that references it exists,
so the row is created orphaned (message_id NULL) and linked on send. The
column was non-NULL, so every upload hit a ForeignKeyViolation (message_id=0
has no matching chat_messages row).

Revision ID: c9d8e7f6a5b4
Revises: merge_c4e8
Create Date: 2026-10-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d8e7f6a5b4'
down_revision: Union[str, None] = 'merge_c4e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'chat_attachments',
        'message_id',
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'chat_attachments',
        'message_id',
        existing_type=sa.Integer(),
        nullable=False,
    )
