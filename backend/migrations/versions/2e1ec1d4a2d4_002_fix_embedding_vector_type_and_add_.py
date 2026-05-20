"""002_fix_embedding_vector_type_and_add_current_chapter_index

Revision ID: 2e1ec1d4a2d4
Revises: 001
Create Date: 2026-05-17 13:54:28.194015

Fix:
  1. Change chapter_embeddings.embedding from float[] to vector(1024) for pgvector support
  2. Add current_chapter_index to novels table
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision: str = '2e1ec1d4a2d4'
down_revision: Union[str, Sequence[str], None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Fix embedding column type: float[] -> vector(1024)
    #    Drop and recreate since PostgreSQL can't directly cast float[] to vector
    op.execute("ALTER TABLE chapter_embeddings ALTER COLUMN embedding TYPE vector(1024) USING embedding::text::vector")

    # 2. Add current_chapter_index to novels
    op.add_column("novels", sa.Column("current_chapter_index", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("novels", "current_chapter_index")
    op.execute("ALTER TABLE chapter_embeddings ALTER COLUMN embedding TYPE float[] USING embedding::text::float[]")
