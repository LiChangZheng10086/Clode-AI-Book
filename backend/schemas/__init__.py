from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NovelCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    genre: str = Field(default="")
    target_chapters: int = Field(default=100, ge=1, le=5000)


class NovelUpdate(BaseModel):
    title: str | None = None
    genre: str | None = None
    target_chapters: int | None = Field(default=None, ge=1, le=5000)
    status: str | None = None


class NovelResponse(BaseModel):
    id: UUID
    title: str
    genre: str
    target_chapters: int
    status: str
    created_at: datetime
    updated_at: datetime
    current_chapter_index: int | None = None

    model_config = {"from_attributes": True}
