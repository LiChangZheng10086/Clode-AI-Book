from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.base import Novel
from schemas import NovelCreate, NovelResponse, NovelUpdate

router = APIRouter()


@router.get("/", response_model=list[NovelResponse])
async def list_novels(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Novel).order_by(Novel.updated_at.desc()))
    return result.scalars().all()


@router.post("/", response_model=NovelResponse, status_code=201)
async def create_novel(data: NovelCreate, db: AsyncSession = Depends(get_db)):
    novel = Novel(**data.model_dump())
    db.add(novel)
    await db.flush()
    await db.refresh(novel)
    return novel


@router.get("/{novel_id}", response_model=NovelResponse)
async def get_novel(novel_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Novel).where(Novel.id == novel_id))
    novel = result.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    return novel


@router.patch("/{novel_id}", response_model=NovelResponse)
async def update_novel(novel_id: UUID, data: NovelUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Novel).where(Novel.id == novel_id))
    novel = result.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(novel, key, value)
    await db.flush()
    await db.refresh(novel)
    return novel


@router.delete("/{novel_id}", status_code=204)
async def delete_novel(novel_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Novel).where(Novel.id == novel_id))
    novel = result.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    await db.delete(novel)
