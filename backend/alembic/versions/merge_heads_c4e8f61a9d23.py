"""merge heads

Revision ID: merge_c4e8
Revises: b8e3f7a2c1d4, d1a6f4c8b729
"""
from alembic import op
import sqlalchemy as sa

revision = "merge_c4e8"
down_revision = ("b8e3f7a2c1d4", "d1a6f4c8b729")
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass
