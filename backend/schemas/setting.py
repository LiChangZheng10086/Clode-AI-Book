from pydantic import BaseModel


class WorldSettingUpdate(BaseModel):
    world_type: str | None = None
    settings: dict | None = None


class StyleProfileUpdate(BaseModel):
    reference_text: str | None = None
    extracted_params: dict | None = None
