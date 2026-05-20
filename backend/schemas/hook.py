from uuid import UUID

from pydantic import BaseModel, Field


class HookCreate(BaseModel):
    hook_type: str
    description: str
    planted_chapter_index: int
    target_chapter_range: dict | None = None
    priority: str = "minor"
    related_entities: list | None = None


class HookUpdate(BaseModel):
    status: str | None = None
    resolved_chapter_index: int | None = None
    resolution_note: str | None = None
    target_chapter_range: dict | None = None


class HookResponse(BaseModel):
    id: UUID
    novel_id: UUID
    hook_type: str
    description: str
    planted_chapter_index: int
    target_chapter_range: dict | None
    priority: str
    status: str
    resolved_chapter_index: int | None
    resolution_note: str | None

    model_config = {"from_attributes": True}
