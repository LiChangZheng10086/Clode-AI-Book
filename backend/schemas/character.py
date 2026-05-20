from uuid import UUID

from pydantic import BaseModel, Field


class CharacterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    role: str = Field(default="supporting")
    profile: dict = Field(default_factory=dict)


class CharacterUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    profile: dict | None = None
    voice_config: dict | None = None
    relationships: list | None = None
    arc: list | None = None


class CharacterResponse(BaseModel):
    id: UUID
    novel_id: UUID
    name: str
    role: str
    profile: dict
    voice_config: dict | None = None
    relationships: list | None = None
    arc: list | None = None

    model_config = {"from_attributes": True}
