from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.base import Novel, StyleProfile, WorldSetting
from schemas.setting import StyleProfileUpdate, WorldSettingUpdate

router = APIRouter()


@router.get("/novel/{novel_id}/world")
async def get_world_setting(novel_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WorldSetting).where(WorldSetting.novel_id == novel_id))
    ws = result.scalar_one_or_none()
    if not ws:
        return None
    return {"id": str(ws.id), "world_type": ws.world_type, "settings": ws.settings}


@router.put("/novel/{novel_id}/world")
async def update_world_setting(novel_id: UUID, data: WorldSettingUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WorldSetting).where(WorldSetting.novel_id == novel_id))
    ws = result.scalar_one_or_none()
    if not ws:
        ws = WorldSetting(novel_id=novel_id)
        db.add(ws)
    if data.world_type is not None:
        ws.world_type = data.world_type
    if data.settings is not None:
        ws.settings = data.settings
    await db.flush()
    await db.refresh(ws)
    return {"id": str(ws.id), "world_type": ws.world_type, "settings": ws.settings}


@router.get("/novel/{novel_id}/style")
async def get_style_profile(novel_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(StyleProfile).where(StyleProfile.novel_id == novel_id))
    sp = result.scalar_one_or_none()
    if not sp:
        return None
    return {"id": str(sp.id), "reference_text": sp.reference_text, "extracted_params": sp.extracted_params}


@router.put("/novel/{novel_id}/style")
async def update_style_profile(novel_id: UUID, data: StyleProfileUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(StyleProfile).where(StyleProfile.novel_id == novel_id))
    sp = result.scalar_one_or_none()
    if not sp:
        sp = StyleProfile(novel_id=novel_id)
        db.add(sp)
    if data.reference_text is not None:
        sp.reference_text = data.reference_text
    if data.extracted_params is not None:
        sp.extracted_params = data.extracted_params
    await db.flush()
    await db.refresh(sp)
    return {"id": str(sp.id), "reference_text": sp.reference_text, "extracted_params": sp.extracted_params}
