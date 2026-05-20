from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.base import Hook
from schemas.hook import HookCreate, HookResponse, HookUpdate

router = APIRouter()


@router.get("/novel/{novel_id}", response_model=list[HookResponse])
async def list_hooks(
    novel_id: UUID,
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Hook).where(Hook.novel_id == novel_id)
    if status:
        stmt = stmt.where(Hook.status == status)
    if priority:
        stmt = stmt.where(Hook.priority == priority)
    stmt = stmt.order_by(Hook.planted_chapter_index)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/novel/{novel_id}", response_model=HookResponse, status_code=201)
async def create_hook(novel_id: UUID, data: HookCreate, db: AsyncSession = Depends(get_db)):
    hook = Hook(novel_id=novel_id, **data.model_dump())
    db.add(hook)
    await db.flush()
    await db.refresh(hook)
    return hook


@router.patch("/{hook_id}", response_model=HookResponse)
async def update_hook(hook_id: UUID, data: HookUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Hook).where(Hook.id == hook_id))
    hook = result.scalar_one_or_none()
    if not hook:
        raise HTTPException(status_code=404, detail="Hook not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(hook, key, value)
    await db.flush()
    await db.refresh(hook)
    return hook


@router.delete("/{hook_id}", status_code=204)
async def delete_hook(hook_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Hook).where(Hook.id == hook_id))
    hook = result.scalar_one_or_none()
    if not hook:
        raise HTTPException(status_code=404, detail="Hook not found")
    await db.delete(hook)
