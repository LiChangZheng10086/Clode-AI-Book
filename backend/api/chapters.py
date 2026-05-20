from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.base import Chapter, Volume
from schemas.chapter import ChapterContentUpdate, ChapterOutlineUpdate, ChapterResponse, ChapterSaveRequest, VolumeResponse

router = APIRouter()


@router.get("/novel/{novel_id}/volumes", response_model=list[VolumeResponse])
async def list_volumes(novel_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Volume).where(Volume.novel_id == novel_id).order_by(Volume.index)
    )
    return result.scalars().all()


@router.get("/volume/{volume_id}/chapters", response_model=list[ChapterResponse])
async def list_chapters(volume_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Chapter).where(Chapter.volume_id == volume_id).order_by(Chapter.index)
    )
    return result.scalars().all()


@router.get("/novel/{novel_id}/chapter/{chapter_index}", response_model=ChapterResponse)
async def get_chapter_by_index(novel_id: UUID, chapter_index: int, db: AsyncSession = Depends(get_db)):
    """Get chapter by novel ID and chapter index within the novel."""
    vol_result = await db.execute(
        select(Volume).where(Volume.novel_id == novel_id).order_by(Volume.index)
    )
    for v in vol_result.scalars().all():
        ch_result = await db.execute(
            select(Chapter).where(
                Chapter.volume_id == v.id,
                Chapter.index == chapter_index,
            )
        )
        ch = ch_result.scalar_one_or_none()
        if ch:
            return ch
    raise HTTPException(status_code=404, detail="Chapter not found")


@router.get("/{chapter_id}", response_model=ChapterResponse)
async def get_chapter(chapter_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter


@router.patch("/{chapter_id}/outline", response_model=ChapterResponse)
async def update_chapter_outline(chapter_id: UUID, data: ChapterOutlineUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    chapter.outline = data.outline
    chapter.status = "outlining"
    await db.flush()
    await db.refresh(chapter)
    return chapter


@router.patch("/novel/{novel_id}/chapter/{chapter_index}/save")
async def save_chapter_content(
    novel_id: UUID,
    chapter_index: int,
    data: ChapterSaveRequest,
    db: AsyncSession = Depends(get_db),
):
    """Save chapter content (and optional outline) by novel ID + chapter index."""
    vol_result = await db.execute(
        select(Volume).where(Volume.novel_id == novel_id).order_by(Volume.index)
    )
    target = None
    for v in vol_result.scalars().all():
        ch_result = await db.execute(
            select(Chapter).where(
                Chapter.volume_id == v.id,
                Chapter.index == chapter_index,
            )
        )
        target = ch_result.scalar_one_or_none()
        if target:
            break

    if not target:
        raise HTTPException(status_code=404, detail="Chapter not found")

    if data.content is not None:
        target.content = data.content
        target.actual_word_count = len(data.content)
        target.status = "completed"
    if data.outline is not None:
        target.outline = data.outline
    await db.commit()
    await db.refresh(target)
    return target


@router.get("/novel/{novel_id}/write-context")
async def get_write_context(novel_id: UUID, chapter_index: int, db: AsyncSession = Depends(get_db)):
    """Fetch context data for the Write page sidebar."""
    from models.base import ChapterSummary, EntityState, Hook

    ctx = {
        "book_summary": "",
        "volume_summary": "",
        "prev_chapter_recap": "",
        "pending_hooks": [],
        "characters_involved": [],
        "entity_states": [],
    }

    # Find the volume that contains this chapter
    vol_result = await db.execute(
        select(Volume).where(Volume.novel_id == novel_id).order_by(Volume.index)
    )
    volumes = vol_result.scalars().all()
    current_volume = None
    all_chapters = []
    for v in volumes:
        ch_result = await db.execute(
            select(Chapter).where(Chapter.volume_id == v.id).order_by(Chapter.index)
        )
        v_chapters = list(ch_result.scalars().all())
        all_chapters.extend(v_chapters)
        for ch in v_chapters:
            if ch.index == chapter_index:
                current_volume = v
                break
        if current_volume:
            break

    # Book summary — find latest book-level summary
    for v in volumes:
        ch_result = await db.execute(
            select(Chapter).where(Chapter.volume_id == v.id).order_by(Chapter.index.desc())
        )
        for ch in ch_result.scalars().all():
            s_result = await db.execute(
                select(ChapterSummary).where(
                    ChapterSummary.chapter_id == ch.id,
                    ChapterSummary.summary_type == "book",
                )
            )
            s = s_result.scalar_one_or_none()
            if s and s.content:
                ctx["book_summary"] = s.content
                break
        if ctx["book_summary"]:
            break

    # Volume summary
    if current_volume:
        ctx["volume_summary"] = current_volume.summary or ""

    # Previous chapter recap (last chapter's summary)
    all_chapters_sorted = sorted(all_chapters, key=lambda c: (c.volume_id, c.index))
    prev_chapters = [c for c in all_chapters_sorted if c.index < chapter_index]
    if prev_chapters:
        prev_ch = prev_chapters[-1]
        s_result = await db.execute(
            select(ChapterSummary).where(
                ChapterSummary.chapter_id == prev_ch.id,
                ChapterSummary.summary_type == "chapter",
            )
        )
        prev_summary = s_result.scalar_one_or_none()
        if prev_summary and prev_summary.content:
            ctx["prev_chapter_recap"] = prev_summary.content
        elif prev_ch.summary:
            ctx["prev_chapter_recap"] = prev_ch.summary

    # Pending hooks (unresolved + in_progress)
    hook_result = await db.execute(
        select(Hook).where(
            Hook.novel_id == novel_id,
            Hook.status.in_(["unresolved", "in_progress"]),
        ).order_by(Hook.priority.desc(), Hook.planted_chapter_index)
    )
    ctx["pending_hooks"] = [
        {
            "id": str(h.id),
            "hook_type": h.hook_type,
            "description": h.description,
            "priority": h.priority,
            "planted_chapter_index": h.planted_chapter_index,
            "status": h.status,
        }
        for h in hook_result.scalars().all()
    ]

    # Characters involved — from chapter outline
    for v in volumes:
        ch_result = await db.execute(
            select(Chapter).where(
                Chapter.volume_id == v.id,
                Chapter.index == chapter_index,
            )
        )
        target_ch = ch_result.scalar_one_or_none()
        if target_ch:
            outline = target_ch.outline or {}
            scenes = outline.get("scenes", [])
            if isinstance(scenes, list):
                seen_names = set()
                for s in scenes:
                    if not isinstance(s, dict):
                        continue
                    for field in ("characters_involved", "characters"):
                        chars = s.get(field, [])
                        if isinstance(chars, list):
                            for c in chars:
                                name = c.get("name", c) if isinstance(c, dict) else str(c)
                                if name and name not in seen_names:
                                    seen_names.add(name)
                                    ctx["characters_involved"].append(name)
            break

    # Entity states
    entity_result = await db.execute(
        select(EntityState).where(EntityState.novel_id == novel_id)
    )
    for e in entity_result.scalars().all():
        latest = e.state_snapshots[-1] if e.state_snapshots else None
        ctx["entity_states"].append({
            "name": e.entity_name,
            "type": e.entity_type,
            "latest_state": latest.get("state", "") if latest else "",
        })

    return ctx


@router.patch("/{chapter_id}/content", response_model=ChapterResponse)
async def update_chapter_content(chapter_id: UUID, data: ChapterContentUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    chapter.content = data.content
    await db.flush()
    await db.refresh(chapter)
    return chapter
