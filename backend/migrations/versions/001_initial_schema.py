"""Initial schema — all tables for Clode AI Book.

Revision ID: 001
Revises: None
Create Date: 2026-05-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")

    op.create_table(
        "novels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("genre", sa.String(100), server_default=""),
        sa.Column("target_chapters", sa.Integer(), server_default="100"),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("current_chapter_index", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "volumes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("novel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("novels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), server_default=""),
        sa.Column("summary", sa.Text()),
        sa.Column("status", sa.String(20), server_default="draft"),
    )

    op.create_table(
        "chapters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("volume_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("volumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), server_default=""),
        sa.Column("outline", postgresql.JSONB()),
        sa.Column("content", sa.Text()),
        sa.Column("summary", sa.Text()),
        sa.Column("target_word_count", sa.Integer(), server_default="3000"),
        sa.Column("actual_word_count", sa.Integer(), server_default="0"),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("version", sa.Integer(), server_default="1"),
        sa.Column("review_round", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "chapter_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("summary_type", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "chapter_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
    )

    op.create_table(
        "characters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("novel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("novels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(50), server_default="supporting"),
        sa.Column("profile", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("voice_config", postgresql.JSONB()),
        sa.Column("relationships", postgresql.JSONB()),
        sa.Column("arc", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "entity_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("novel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("novels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_name", sa.String(100), nullable=False),
        sa.Column("state_snapshots", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "hooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("novel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("novels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hook_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("planted_chapter_index", sa.Integer(), nullable=False),
        sa.Column("target_chapter_range", postgresql.JSONB()),
        sa.Column("priority", sa.String(20), server_default="minor"),
        sa.Column("status", sa.String(20), server_default="unresolved"),
        sa.Column("resolved_chapter_index", sa.Integer()),
        sa.Column("resolution_note", sa.Text()),
        sa.Column("related_entities", postgresql.JSONB()),
        sa.Column("related_hooks", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "style_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("novel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("novels.id", ondelete="CASCADE"), unique=True),
        sa.Column("reference_text", sa.Text()),
        sa.Column("extracted_params", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "world_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("novel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("novels.id", ondelete="CASCADE"), unique=True),
        sa.Column("world_type", sa.String(50), server_default=""),
        sa.Column("settings", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes
    op.create_index("idx_chapters_volume", "chapters", ["volume_id", "index"])
    op.create_index("idx_volumes_novel", "volumes", ["novel_id", "index"])
    op.create_index("idx_hooks_novel_status", "hooks", ["novel_id", "status"])
    op.create_index("idx_characters_novel", "characters", ["novel_id"])
    op.create_index("idx_entity_states_lookup", "entity_states", ["novel_id", "entity_name"])


def downgrade() -> None:
    op.drop_table("world_settings")
    op.drop_table("style_profiles")
    op.drop_table("hooks")
    op.drop_table("entity_states")
    op.drop_table("characters")
    op.drop_table("chapter_embeddings")
    op.drop_table("chapter_summaries")
    op.drop_table("chapters")
    op.drop_table("volumes")
    op.drop_table("novels")
