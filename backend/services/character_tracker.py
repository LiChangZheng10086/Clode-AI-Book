"""Extract and track new characters from generated chapter content."""

import json
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import async_session
from core.json_utils import parse_llm_json_array
from core.llm import get_planning_llm
from models.base import Character

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = """你是一位角色登记员。从以下小说章节内容中，找出**新登场**的角色（即不在已知角色列表中的角色）。

已知角色列表（只登记不在此列表中的新角色）：
{known_names}

章节内容：
---
{content}
---

对于每个新角色，提取以下信息并输出 JSON 数组：
[
  {{
    "name": "角色名",
    "role": "protagonist|supporting|antagonist|npc",
    "profile": {{
      "appearance": "外貌描述（如未描述则填'未知'）",
      "personality": "性格特征（如未体现则填'未知'）",
      "background": "背景（如未提及则填'未知'）"
    }},
    "relationships": [
      {{"target": "主角名或角色名", "relation_type": "师徒/朋友/敌人/同门/...", "description": "关系简述"}}
    ],
    "faction": "所属势力（如未提及则填'未知'）",
    "is_alive": true
  }}
]

规则：
1. 只登记**不在已知角色列表**中的新角色
2. 配角/龙套也要登记（如"店小二"、"路人甲"）
3. 已死亡的角色也要登记，is_alive 设为 false
4. 如果在内容中没有找到任何新角色，返回空数组 []
5. relationship 中的 target 优先使用已知角色列表中的名字

直接输出 JSON 数组，不要包裹在对象中。"""


async def extract_and_save_new_characters(
    novel_id: str,
    chapter_content: str,
    known_character_names: list[str],
) -> list[dict]:
    """Find new characters in chapter content and save them to the database.

    Returns list of newly created character dicts.
    """
    if not chapter_content or len(chapter_content.strip()) < 100:
        return []

    novel_uuid = UUID(novel_id)
    known_str = ", ".join(known_character_names) if known_character_names else "（无已知角色）"

    # Truncate content to avoid token overflow — first 8K chars should catch most intros
    content_snippet = chapter_content[:8000]

    prompt = _EXTRACT_PROMPT.format(known_names=known_str, content=content_snippet)
    llm = get_planning_llm()

    try:
        response = await llm.ainvoke(prompt)
        text = (response.content or "").strip()
        result = parse_llm_json_array(text)
    except Exception as exc:
        logger.warning("Character extraction LLM call failed: %s", exc)
        return []

    if not result:
        return []

    new_chars = []
    async with async_session() as db:
        for c in result:
            if not isinstance(c, dict) or not c.get("name"):
                continue
            name = str(c["name"]).strip()
            if not name or name in known_character_names:
                continue

            char = Character(
                novel_id=novel_uuid,
                name=name,
                role=str(c.get("role", "npc")),
                profile=c.get("profile", {}),
                relationships=c.get("relationships"),
            )
            db.add(char)
            new_chars.append({
                "name": name,
                "role": c.get("role", "npc"),
                "profile": c.get("profile", {}),
                "relationships": c.get("relationships"),
                "faction": c.get("faction", "未知"),
                "is_alive": c.get("is_alive", True),
            })

        if new_chars:
            await db.commit()
            logger.info("Saved %d new characters for novel %s: %s",
                        len(new_chars), novel_id, [c["name"] for c in new_chars])

    return new_chars
