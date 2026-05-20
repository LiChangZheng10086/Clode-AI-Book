from uuid import UUID

from pydantic import BaseModel


class VolumeResponse(BaseModel):
    id: UUID
    novel_id: UUID
    index: int
    title: str
    summary: str | None
    status: str

    model_config = {"from_attributes": True}


class ChapterResponse(BaseModel):
    id: UUID
    volume_id: UUID
    index: int
    title: str
    outline: dict | None
    content: str | None
    summary: str | None
    target_word_count: int
    actual_word_count: int
    status: str
    version: int

    model_config = {"from_attributes": True}


class ChapterOutlineUpdate(BaseModel):
    outline: dict


class ChapterContentUpdate(BaseModel):
    content: str


class ChapterSaveRequest(BaseModel):
    content: str | None = None
    outline: dict | None = None
