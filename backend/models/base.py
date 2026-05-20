import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class Novel(Base):
    __tablename__ = "novels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    genre: Mapped[str] = mapped_column(String(100), default="")
    target_chapters: Mapped[int] = mapped_column(Integer, default=100)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | preprocess | writing | completed | archived
    current_chapter_index: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    volumes: Mapped[list["Volume"]] = relationship(back_populates="novel", cascade="all, delete-orphan")
    characters: Mapped[list["Character"]] = relationship(back_populates="novel", cascade="all, delete-orphan")
    hooks: Mapped[list["Hook"]] = relationship(back_populates="novel", cascade="all, delete-orphan")
    style_profile: Mapped["StyleProfile | None"] = relationship(back_populates="novel", uselist=False, cascade="all, delete-orphan")
    world_setting: Mapped["WorldSetting | None"] = relationship(back_populates="novel", uselist=False, cascade="all, delete-orphan")


class Volume(Base):
    __tablename__ = "volumes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("novels.id", ondelete="CASCADE"))
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="")
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft")

    novel: Mapped["Novel"] = relationship(back_populates="volumes")
    chapters: Mapped[list["Chapter"]] = relationship(back_populates="volume", cascade="all, delete-orphan", order_by="Chapter.index")


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    volume_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("volumes.id", ondelete="CASCADE"))
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="")
    outline: Mapped[dict | None] = mapped_column(JSONB)    # Chapter-level scene beats
    content: Mapped[str | None] = mapped_column(Text)      # Full text
    summary: Mapped[str | None] = mapped_column(Text)      # Auto-generated after writing
    target_word_count: Mapped[int] = mapped_column(Integer, default=3000)
    actual_word_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | outlining | writing | reviewing | done
    version: Mapped[int] = mapped_column(Integer, default=1)
    review_round: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    volume: Mapped["Volume"] = relationship(back_populates="chapters")
    chapter_summaries: Mapped[list["ChapterSummary"]] = relationship(back_populates="chapter", cascade="all, delete-orphan")
    embeddings: Mapped[list["ChapterEmbedding"]] = relationship(back_populates="chapter", cascade="all, delete-orphan")


class ChapterSummary(Base):
    __tablename__ = "chapter_summaries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chapter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="CASCADE"))
    summary_type: Mapped[str] = mapped_column(String(20), nullable=False)  # chapter | volume | book
    content: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    chapter: Mapped["Chapter"] = relationship(back_populates="chapter_summaries")


class ChapterEmbedding(Base):
    __tablename__ = "chapter_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chapter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024))

    chapter: Mapped["Chapter"] = relationship(back_populates="embeddings")


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("novels.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="supporting")  # protagonist | supporting | antagonist | npc
    profile: Mapped[dict] = mapped_column(JSONB, default=dict)           # appearance, personality, background, motivation, flaws
    voice_config: Mapped[dict | None] = mapped_column(JSONB)             # speaking style, catchphrases, taboo words
    relationships: Mapped[list | None] = mapped_column(JSONB)            # [{target, relation, detail}]
    arc: Mapped[list | None] = mapped_column(JSONB)                      # [{stage, chapter_range, description}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    novel: Mapped["Novel"] = relationship(back_populates="characters")


class EntityState(Base):
    __tablename__ = "entity_states"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("novels.id", ondelete="CASCADE"))
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # character | item | faction | location
    entity_name: Mapped[str] = mapped_column(String(100), nullable=False)
    state_snapshots: Mapped[list] = mapped_column(JSONB, default=list)    # [{chapter, state}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Hook(Base):
    __tablename__ = "hooks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("novels.id", ondelete="CASCADE"))
    hook_type: Mapped[str] = mapped_column(String(50), nullable=False)  # mystery | chekhovs_gun | prophecy | secret | conflict
    description: Mapped[str] = mapped_column(Text, nullable=False)
    planted_chapter_index: Mapped[int] = mapped_column(Integer, nullable=False)
    target_chapter_range: Mapped[dict | None] = mapped_column(JSONB)     # [min, max]
    priority: Mapped[str] = mapped_column(String(20), default="minor")   # major | minor
    status: Mapped[str] = mapped_column(String(20), default="unresolved")  # unresolved | in_progress | resolved | abandoned
    resolved_chapter_index: Mapped[int | None] = mapped_column(Integer)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    related_entities: Mapped[list | None] = mapped_column(JSONB)
    related_hooks: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    novel: Mapped["Novel"] = relationship(back_populates="hooks")


class StyleProfile(Base):
    __tablename__ = "style_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("novels.id", ondelete="CASCADE"), unique=True)
    reference_text: Mapped[str | None] = mapped_column(Text)
    extracted_params: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    novel: Mapped["Novel"] = relationship(back_populates="style_profile")


class WorldSetting(Base):
    __tablename__ = "world_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    novel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("novels.id", ondelete="CASCADE"), unique=True)
    world_type: Mapped[str] = mapped_column(String(200), default="")
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)  # geography, power_system, factions, items, rules, history
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    novel: Mapped["Novel"] = relationship(back_populates="world_setting")
