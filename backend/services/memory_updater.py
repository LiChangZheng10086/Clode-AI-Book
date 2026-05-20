"""Post-chapter memory updates: summaries, hooks, entity states."""

import json
import logging
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import async_session
from core.llm import get_planning_llm
from models.base import Chapter, ChapterSummary, EntityState, Hook, Novel, Volume

logger = logging.getLogger(__name__)

_CHAPTER_SUMMARY_PROMPT = """你是一位小说编辑。请为以下章节撰写一段简短摘要（100–200 字）。

章节标题：{title}
章节正文（截取）：
---
{content}
---

只输出摘要文本，不要任何标记或格式。"""

_BOOK_SUMMARY_PROMPT = """你是一位小说编辑。请根据已完成的章节，更新全书的摘要。

已有全书摘要（如首次生成则为空）：
{existing_summary}

新完成的章节摘要：
{new_chapter_summary}

请撰写一段更新的全书摘要（200–400 字），概括：
1. 故事的整体走向
2. 主要剧情进展
3. 关键转折点

只输出摘要文本，不要任何标记或格式。"""

_VOLUME_SUMMARY_PROMPT = """你是一位小说编辑。请为当前卷撰写一段摘要（150–300 字）。

当前卷标题：{volume_title}
本卷已完成章节的摘要列表：
{chapter_summaries}

新完成的章节摘要：
{new_chapter_summary}

请撰写一段卷摘要，概括本卷到目前为止的主要剧情进展。
只输出摘要文本，不要任何标记或格式。"""

_HOOK_EXTRACTION_PROMPT = """你是一位伏笔分析师。从以下章节正文和章节大纲中，识别所有伏笔（hook）。

章节大纲中的 hooks 字段（如有）：
{hooks_from_outline}

章节正文（截取前 6000 字）：
---
{content}
---

对于每个伏笔，输出 JSON 数组：
[
  {{
    "hook_type": "mystery|chekhovs_gun|prophecy|secret|conflict",
    "description": "伏笔简述（50字以内）",
    "priority": "major|minor",
    "status": "unresolved|resolved",
    "resolution_note": "如已回收，简述回收方式（否则填null）",
    "related_entities": ["相关角色或势力名"]
  }}
]

规则：
1. 已在大纲中标注 hook_plant 的优先识别
2. 正文中隐晦的伏笔也要识别
3. 已回收的伏笔也需要记录（status=resolved）
4. 如果没有发现任何伏笔，返回空数组 []

直接输出 JSON 数组，不要包裹在对象中。"""

_ENTITY_STATE_PROMPT = """你是一位角色/实体状态追踪员。从以下章节正文中，提取每个提及角色/实体的最新状态。

已知实体列表（如首次则为空）：
{known_entities}

章节正文（截取前 6000 字）：
---
{content}
---

输出 JSON 对象，key 为实体名称，value 为状态描述：
{{
  "角色名": {{
    "entity_type": "character",
    "state": "当前状态简述（位置、状态、关系变化等，50字以内）"
  }}
}}

规则：
1. 已有状态的实体：更新其状态
2. 新出现的实体：记录其初始状态
3. 本章未出现的实体：不包含在输出中
4. 包括重要物品（法宝、秘籍等）和势力

直接输出 JSON 对象，不要包裹在数组中。"""


async def run_memory_updates(
    novel_id: str,
    chapter_index: int,
    chapter_content: str,
    chapter_outline: dict | None = None,
) -> dict:
    """Run all post-chapter memory updates after a chapter passes review.

    Returns a dict summarizing what was updated for frontend display.
    """
    if not chapter_content or len(chapter_content.strip()) < 200:
        logger.warning("Chapter content too short for memory updates: novel=%s ch=%s",
                       novel_id, chapter_index)
        return {}

    novel_uuid = UUID(novel_id)
    result: dict = {}

    async with async_session() as db:
        # Look up the chapter
        chapter = await _find_chapter(db, novel_uuid, chapter_index)
        if not chapter:
            logger.warning("Chapter not found for memory updates: novel=%s index=%s",
                           novel_id, chapter_index)
            return {}

        # Find volume
        volume = None
        vol_result = await db.execute(
            select(Volume).where(Volume.id == chapter.volume_id)
        )
        volume = vol_result.scalar_one_or_none()

        # 1. Generate chapter summary
        chapter_summary_text = await _generate_chapter_summary(
            chapter.title or f"第{chapter_index}章", chapter_content
        )
        if chapter_summary_text:
            # Delete old chapter-level summary if exists
            await db.execute(
                delete(ChapterSummary).where(
                    ChapterSummary.chapter_id == chapter.id,
                    ChapterSummary.summary_type == "chapter",
                )
            )
            db.add(ChapterSummary(
                chapter_id=chapter.id,
                summary_type="chapter",
                content=chapter_summary_text,
            ))
            chapter.summary = chapter_summary_text
            result["chapter_summary"] = chapter_summary_text
            logger.info("Generated chapter summary for ch %s", chapter_index)

        # 2. Update book-level summary
        existing_book_summary = await _get_latest_summary(db, novel_uuid, "book")
        all_chapter_summaries = await _get_all_chapter_summaries(db, novel_uuid)
        book_summary = await _generate_book_summary(
            existing_book_summary, chapter_summary_text or "", all_chapter_summaries
        )
        if book_summary:
            await db.execute(
                delete(ChapterSummary).where(
                    ChapterSummary.chapter_id == chapter.id,
                    ChapterSummary.summary_type == "book",
                )
            )
            db.add(ChapterSummary(
                chapter_id=chapter.id,
                summary_type="book",
                content=book_summary,
            ))
            result["book_summary"] = book_summary
            logger.info("Updated book summary for novel %s after ch %s", novel_id, chapter_index)

        # 3. Update volume-level summary
        if volume:
            vol_chapter_summaries = await _get_volume_chapter_summaries(
                db, volume.id, chapter_index
            )
            existing_vol_summary = await _get_latest_summary(db, novel_uuid, "volume")
            vol_summary = await _generate_volume_summary(
                volume.title or f"第{volume.index}卷",
                existing_vol_summary or volume.summary or "",
                vol_chapter_summaries,
                chapter_summary_text or "",
            )
            if vol_summary:
                await db.execute(
                    delete(ChapterSummary).where(
                        ChapterSummary.chapter_id == chapter.id,
                        ChapterSummary.summary_type == "volume",
                    )
                )
                db.add(ChapterSummary(
                    chapter_id=chapter.id,
                    summary_type="volume",
                    content=vol_summary,
                ))
                volume.summary = vol_summary
                result["volume_summary"] = vol_summary
                logger.info("Updated volume summary for vol %s", volume.index)

        # 4. Extract and save hooks
        hooks_from_outline = _extract_hooks_from_outline(chapter_outline)
        hooks = await _extract_hooks(chapter_content, hooks_from_outline, novel_uuid, chapter_index)
        if hooks:
            for h_data in hooks:
                hook = Hook(
                    novel_id=novel_uuid,
                    hook_type=h_data.get("hook_type", "mystery"),
                    description=h_data.get("description", ""),
                    planted_chapter_index=chapter_index,
                    priority=h_data.get("priority", "minor"),
                    status=h_data.get("status", "unresolved"),
                    resolution_note=h_data.get("resolution_note"),
                    resolved_chapter_index=chapter_index if h_data.get("status") == "resolved" else None,
                    related_entities=h_data.get("related_entities"),
                )
                db.add(hook)
            result["new_hooks"] = len(hooks)
            logger.info("Extracted %d hooks from ch %s", len(hooks), chapter_index)

        # Mark hooks as resolved if this chapter's outline says so
        resolved_hook_ids = _find_resolved_hooks(chapter_outline)
        if resolved_hook_ids:
            # These are hook identifiers from the outline — try to match existing hooks
            for hook_name in resolved_hook_ids:
                stmt = select(Hook).where(
                    Hook.novel_id == novel_uuid,
                    Hook.status == "unresolved",
                )
                hook_result = await db.execute(stmt)
                for h in hook_result.scalars().all():
                    if hook_name.lower() in (h.description or "").lower():
                        h.status = "resolved"
                        h.resolved_chapter_index = chapter_index
                        h.resolution_note = f"第{chapter_index}章回收"
                        logger.info("Resolved hook %s in ch %s", h.id, chapter_index)

        # 5. Update entity states
        known_entities = await _get_known_entities(db, novel_uuid)
        entity_states = await _extract_entity_states(
            chapter_content, known_entities, novel_uuid
        )
        if entity_states:
            for name, state_data in entity_states.items():
                existing = await db.execute(
                    select(EntityState).where(
                        EntityState.novel_id == novel_uuid,
                        EntityState.entity_name == name,
                    )
                )
                entity = existing.scalar_one_or_none()
                if entity:
                    snapshots = entity.state_snapshots or []
                    snapshots.append({
                        "chapter_index": chapter_index,
                        "state": state_data.get("state", ""),
                    })
                    entity.state_snapshots = snapshots
                else:
                    db.add(EntityState(
                        novel_id=novel_uuid,
                        entity_type=state_data.get("entity_type", "character"),
                        entity_name=name,
                        state_snapshots=[{
                            "chapter_index": chapter_index,
                            "state": state_data.get("state", ""),
                        }],
                    ))
            result["entity_states_updated"] = len(entity_states)
            logger.info("Updated %d entity states for ch %s", len(entity_states), chapter_index)

        await db.commit()

    return result


# ── Internal helpers ────────────────────────────────────

async def _find_chapter(db: AsyncSession, novel_uuid: UUID, chapter_index: int) -> Chapter | None:
    vol_result = await db.execute(
        select(Volume).where(Volume.novel_id == novel_uuid).order_by(Volume.index)
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
    return None


async def _generate_chapter_summary(title: str, content: str) -> str:
    try:
        llm = get_planning_llm()
        prompt = _CHAPTER_SUMMARY_PROMPT.format(
            title=title, content=content[:4000]
        )
        response = await llm.ainvoke(prompt)
        return (response.content or "").strip()
    except Exception:
        logger.exception("Failed to generate chapter summary")
        return ""


async def _get_latest_summary(db: AsyncSession, novel_uuid: UUID, summary_type: str) -> str:
    """Get the most recent summary of given type across all chapters of the novel."""
    vol_result = await db.execute(
        select(Volume).where(Volume.novel_id == novel_uuid)
    )
    latest = ""
    for v in vol_result.scalars().all():
        ch_result = await db.execute(
            select(Chapter).where(Chapter.volume_id == v.id).order_by(Chapter.index.desc())
        )
        for ch in ch_result.scalars().all():
            s_result = await db.execute(
                select(ChapterSummary).where(
                    ChapterSummary.chapter_id == ch.id,
                    ChapterSummary.summary_type == summary_type,
                )
            )
            s = s_result.scalar_one_or_none()
            if s and s.content:
                latest = s.content
                break
        if latest:
            break
    return latest


async def _get_all_chapter_summaries(db: AsyncSession, novel_uuid: UUID) -> list[str]:
    summaries: list[str] = []
    vol_result = await db.execute(
        select(Volume).where(Volume.novel_id == novel_uuid).order_by(Volume.index)
    )
    for v in vol_result.scalars().all():
        ch_result = await db.execute(
            select(Chapter).where(Chapter.volume_id == v.id).order_by(Chapter.index)
        )
        for ch in ch_result.scalars().all():
            s_result = await db.execute(
                select(ChapterSummary).where(
                    ChapterSummary.chapter_id == ch.id,
                    ChapterSummary.summary_type == "chapter",
                )
            )
            s = s_result.scalar_one_or_none()
            if s and s.content:
                summaries.append(s.content)
    return summaries


async def _get_volume_chapter_summaries(
    db: AsyncSession, volume_id: UUID, up_to_chapter_index: int
) -> list[str]:
    summaries: list[str] = []
    ch_result = await db.execute(
        select(Chapter).where(Chapter.volume_id == volume_id).order_by(Chapter.index)
    )
    for ch in ch_result.scalars().all():
        if ch.index <= up_to_chapter_index:
            s_result = await db.execute(
                select(ChapterSummary).where(
                    ChapterSummary.chapter_id == ch.id,
                    ChapterSummary.summary_type == "chapter",
                )
            )
            s = s_result.scalar_one_or_none()
            if s and s.content:
                summaries.append(f"第{ch.index}章: {s.content}")
    return summaries


async def _generate_book_summary(
    existing: str, new_chapter_summary: str, all_summaries: list[str]
) -> str:
    try:
        llm = get_planning_llm()
        prompt = _BOOK_SUMMARY_PROMPT.format(
            existing_summary=existing or "（尚无全书摘要）",
            new_chapter_summary=new_chapter_summary or "（新章节）",
        )
        response = await llm.ainvoke(prompt)
        return (response.content or "").strip()
    except Exception:
        logger.exception("Failed to generate book summary")
        return ""


async def _generate_volume_summary(
    volume_title: str,
    existing_summary: str,
    chapter_summaries: list[str],
    new_chapter_summary: str,
) -> str:
    try:
        llm = get_planning_llm()
        prompt = _VOLUME_SUMMARY_PROMPT.format(
            volume_title=volume_title,
            chapter_summaries="\n".join(chapter_summaries[-5:]) if chapter_summaries else "（无）",
            new_chapter_summary=new_chapter_summary or "（新章节）",
        )
        response = await llm.ainvoke(prompt)
        return (response.content or "").strip()
    except Exception:
        logger.exception("Failed to generate volume summary")
        return ""


def _extract_hooks_from_outline(outline: dict | None) -> list[dict]:
    """Extract hook descriptions from chapter outline scenes."""
    if not outline:
        return []
    hooks = []
    scenes = outline.get("scenes", [])
    if not isinstance(scenes, list):
        return []
    for s in scenes:
        if not isinstance(s, dict):
            continue
        for field in ("hook_plant", "hook_planted"):
            hp = s.get(field)
            if isinstance(hp, str) and hp.strip():
                hooks.append({"description": hp.strip(), "source": "outline_plant"})
        for field in ("hook_advanced",):
            ha = s.get(field)
            if isinstance(ha, list):
                for h in ha:
                    if isinstance(h, str) and h.strip():
                        hooks.append({"description": h.strip(), "source": "outline_advanced"})
    return hooks


async def _extract_hooks(
    content: str,
    outline_hooks: list[dict],
    novel_uuid: UUID,
    chapter_index: int,
) -> list[dict]:
    """Use LLM to extract hooks from chapter content, informed by outline hooks."""
    try:
        hooks_text = json.dumps(outline_hooks, ensure_ascii=False) if outline_hooks else "（无）"
        llm = get_planning_llm()
        prompt = _HOOK_EXTRACTION_PROMPT.format(
            hooks_from_outline=hooks_text,
            content=content[:6000],
        )
        response = await llm.ainvoke(prompt)
        text = (response.content or "").strip()
        from engine.planner import _extract_json
        result = _extract_json(text)
        if isinstance(result, list):
            return [h for h in result if isinstance(h, dict) and h.get("description")]
        return []
    except Exception:
        logger.exception("Hook extraction failed")
        # Fallback: save outline hooks as basic hook entries
        basic = []
        for oh in outline_hooks:
            basic.append({
                "hook_type": "mystery",
                "description": oh.get("description", ""),
                "priority": "minor",
                "status": "unresolved",
                "resolution_note": None,
                "related_entities": [],
            })
        return basic


def _find_resolved_hooks(outline: dict | None) -> list[str]:
    """Find hook identifiers that were resolved in this chapter's outline."""
    if not outline:
        return []
    resolved = []
    scenes = outline.get("scenes", [])
    if not isinstance(scenes, list):
        return []
    for s in scenes:
        if not isinstance(s, dict):
            continue
        hr = s.get("hook_resolved")
        if isinstance(hr, str) and hr.strip():
            resolved.append(hr.strip())
        elif isinstance(hr, list):
            for h in hr:
                if isinstance(h, str) and h.strip():
                    resolved.append(h.strip())
    return resolved


async def _get_known_entities(db: AsyncSession, novel_uuid: UUID) -> list[str]:
    result = await db.execute(
        select(EntityState.entity_name).where(EntityState.novel_id == novel_uuid)
    )
    return [row[0] for row in result.all()]


async def _extract_entity_states(
    content: str,
    known_entities: list[str],
    novel_uuid: UUID,
) -> dict:
    """Use LLM to extract entity states from chapter content."""
    try:
        known_str = ", ".join(known_entities) if known_entities else "（首次追踪）"
        llm = get_planning_llm()
        prompt = _ENTITY_STATE_PROMPT.format(
            known_entities=known_str,
            content=content[:6000],
        )
        response = await llm.ainvoke(prompt)
        text = (response.content or "").strip()
        from engine.planner import _extract_json
        result = _extract_json(text)
        if isinstance(result, dict):
            return {k: v for k, v in result.items() if isinstance(v, dict) and v.get("state")}
        return {}
    except Exception:
        logger.exception("Entity state extraction failed")
        return {}
