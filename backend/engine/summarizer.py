"""Auto-summarization and entity extraction after chapter completion."""

import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from core.llm import get_llm


class Summarizer:
    """Generates summaries and extracts structural info after each chapter."""

    CHAPTER_SUMMARY_PROMPT = """你是一位小说分析员。请总结以下章节内容。

输出 JSON：
{
  "summary": "200字以内的章节摘要，包含关键事件",
  "key_events": ["事件1", "事件2", ...],
  "entity_state_changes": [
    {"entity_type": "character|item|faction|location", "entity_name": "...", "before": "上一章的状态", "after": "本章结束时的状态", "note": "变化说明"}
  ],
  "new_hooks": [
    {"type": "mystery|chekhovs_gun|prophecy|secret|conflict", "description": "...", "related_entities": ["..."], "priority": "major|minor", "target_chapter_range": [min, max]}
  ],
  "resolved_hooks": [
    {"hook_id": "..."}
  ]
}"""

    VOLUME_SUMMARY_PROMPT = """请基于以下章节摘要列表，为当前卷生成一个 300-500 字的卷摘要。
涵盖本卷的主要剧情线、角色发展、和留下的悬念。

章节摘要：
{chapter_summaries}

输出：直接输出卷摘要文本。"""

    BOOK_SUMMARY_PROMPT = """请基于以下卷摘要列表，为全书生成一个 500-800 字的全书摘要。
涵盖主线剧情、核心冲突、主要角色弧线。

卷摘要：
{volume_summaries}

输出：直接输出全书摘要文本。"""

    def __init__(self, llm: BaseChatModel | None = None):
        self.llm = llm or get_llm()

    async def summarize_chapter(self, chapter_content: str, chapter_outline: dict) -> dict:
        system = SystemMessage(content=self.CHAPTER_SUMMARY_PROMPT)
        human = HumanMessage(content=f"章节大纲：\n{json.dumps(chapter_outline, ensure_ascii=False, indent=2)}\n\n章节正文：\n{chapter_content[:8000]}")
        response = await self.llm.ainvoke([system, human])
        return self._parse_json(response.content)

    async def summarize_volume(self, chapter_summaries: list[str]) -> str:
        summaries_text = "\n\n---\n\n".join(
            f"第{i+1}章摘要：{s}" for i, s in enumerate(chapter_summaries)
        )
        prompt = self.VOLUME_SUMMARY_PROMPT.format(chapter_summaries=summaries_text)
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        return response.content.strip()

    async def update_book_summary(self, volume_summaries: list[str]) -> str:
        summaries_text = "\n\n---\n\n".join(
            f"卷{i+1}摘要：{s}" for i, s in enumerate(volume_summaries)
        )
        prompt = self.BOOK_SUMMARY_PROMPT.format(volume_summaries=summaries_text)
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        return response.content.strip()

    def _parse_json(self, content: str) -> dict:
        from core.json_utils import extract_json_block
        result = extract_json_block(content)
        if result is not None:
            return result
        return {"summary": content[:200], "key_events": [], "entity_state_changes": [], "new_hooks": [], "resolved_hooks": []}
