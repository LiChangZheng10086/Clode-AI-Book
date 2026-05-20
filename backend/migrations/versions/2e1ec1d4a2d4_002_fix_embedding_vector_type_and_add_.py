"""Fix chapter_embeddings.embedding type to vector(1024).

Revision ID: 2e1ec1d4a2d4
Revises: 001
Create Date: 2026-05-17 13:54:28.194015

Note: current_chapter_index was already created in migration 001,
so this migration only handles the embedding vector type fix.
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
    # Fix embedding column type: float[] -> vector(1024)
    op.execute("ALTER TABLE chapter_embeddings ALTER COLUMN embedding TYPE vector(1024) USING embedding::text::vector")


def downgrade() -> None:
    op.execute("ALTER TABLE chapter_embeddings ALTER COLUMN embedding TYPE float[] USING embedding::text::float[]")
