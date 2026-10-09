"""merge heads

Revision ID: merge_c4e8
Revises: a1b2c3d4e5f6, d1a6f4c8b729
"""
from alembic import op
import sqlalchemy as sa

revision = "merge_c4e8"
down_revision = ("a1b2c3d4e5f6", "d1a6f4c8b729")
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass
