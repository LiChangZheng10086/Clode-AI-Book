from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.base import Character
from schemas.character import CharacterCreate, CharacterResponse, CharacterUpdate

router = APIRouter()


@router.get("/novel/{novel_id}", response_model=list[CharacterResponse])
async def list_characters(novel_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Character).where(Character.novel_id == novel_id).order_by(Character.name)
    )
    return result.scalars().all()


@router.post("/novel/{novel_id}", response_model=CharacterResponse, status_code=201)
async def create_character(novel_id: UUID, data: CharacterCreate, db: AsyncSession = Depends(get_db)):
    character = Character(novel_id=novel_id, **data.model_dump())
    db.add(character)
    await db.flush()
    await db.refresh(character)
    return character


@router.get("/{character_id}", response_model=CharacterResponse)
async def get_character(character_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Character).where(Character.id == character_id))
    character = result.scalar_one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


@router.patch("/{character_id}", response_model=CharacterResponse)
async def update_character(character_id: UUID, data: CharacterUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Character).where(Character.id == character_id))
    character = result.scalar_one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(character, key, value)
    await db.flush()
    await db.refresh(character)
    return character


@router.delete("/{character_id}", status_code=204)
async def delete_character(character_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Character).where(Character.id == character_id))
    character = result.scalar_one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    await db.delete(character)
