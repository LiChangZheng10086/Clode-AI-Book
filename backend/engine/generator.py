"""A5-A6 Writing agents: Chapter Outliner and Chapter Writer."""

import json
from typing import AsyncIterator

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from core.llm import get_llm, get_planning_llm


class ChapterOutliner:
    """A5: Generates detailed chapter outline from novel-level beats."""

    SYSTEM_PROMPT = """你是一位章节大纲设计师。

基于全书大纲中该章的场景节拍，展开为详细的场景级大纲。

你需要为每个场景定义：
- purpose: 这个场景的叙事目的
- characters: 出场角色及其行为动机
- setting: 场景地点和时间
- emotion_curve: 情绪曲线（起点→终点）
- key_beats: 展开的节拍列表（比全书大纲的 beat 更细）
- information_revealed: 本场景揭示的新信息
- hook_plant: 本场景埋下的新伏笔（如有）
- hook_advanced: 本场景推进的已有伏笔（如有）
- transition: 与上下场景的过渡方式

输出 JSON：
{
  "chapter_outline": {
    "chapter_index": 42,
    "title": "...",
    "target_word_count": 3500,
    "prev_chapter_link": "紧接上一章...",
    "next_chapter_hook": "读者继续翻页的理由...",
    "scenes": [
      {
        "scene": 1,
        "purpose": "...",
        "characters": [{"name": "...", "motivation": "..."}],
        "setting": "...",
        "emotion_curve": "平静 → 紧张 → 释然",
        "key_beats": ["...", "..."],
        "information_revealed": "...",
        "hook_plant": "...",
        "hook_advanced": ["hook_042"],
        "transition": "下一场景由林凡的动作引出"
      }
    ]
  }
}

确保：
1. 场景之间有因果链，不是简单时间顺序
2. 情绪有起伏，不要平铺
3. 每个场景都要推进剧情、揭示信息、或深化角色
4. 钩子的推进和回收要明确标注"""

    def __init__(self, llm: BaseChatModel | None = None):
        self.llm = llm or get_planning_llm()

    async def generate(
        self,
        chapter_index: int,
        novel_outline_beat: dict,
        context_package: dict,
    ) -> dict:
        system = SystemMessage(content=self.SYSTEM_PROMPT)
        human = HumanMessage(content=f"""第{chapter_index}章 全书大纲节拍：
{json.dumps(novel_outline_beat, ensure_ascii=False, indent=2)}

上下文包：
- 当前卷摘要：{context_package.get("volume_summary", "无")}
- 近3章摘要：{json.dumps(context_package.get("recent_summaries", []), ensure_ascii=False)}
- 待处理钩子：{json.dumps(context_package.get("pending_hooks", []), ensure_ascii=False)}
- 本章涉及角色当前状态：{json.dumps(context_package.get("entity_states", {}), ensure_ascii=False)}

请生成第{chapter_index}章的详细大纲。""")
        response = await self.llm.ainvoke([system, human])
        return self._parse_response(response.content)

    async def stream_generate(
        self,
        chapter_index: int,
        novel_outline_beat: dict,
        context_package: dict,
    ) -> AsyncIterator[dict]:
        system = SystemMessage(content=self.SYSTEM_PROMPT)
        human = HumanMessage(content=f"""第{chapter_index}章 全书大纲节拍：
{json.dumps(novel_outline_beat, ensure_ascii=False, indent=2)}

上下文包：
- 当前卷摘要：{context_package.get("volume_summary", "无")}
- 近3章摘要：{json.dumps(context_package.get("recent_summaries", []), ensure_ascii=False)}
- 待处理钩子：{json.dumps(context_package.get("pending_hooks", []), ensure_ascii=False)}
- 本章涉及角色当前状态：{json.dumps(context_package.get("entity_states", {}), ensure_ascii=False)}

请生成第{chapter_index}章的详细大纲，输出完整 JSON。""")
        async for chunk in self.llm.astream([system, human]):
            if chunk.content:
                yield {"type": "stream", "content": chunk.content}

    def _parse_response(self, content: str) -> dict:
        from engine.planner import _extract_json
        result = _extract_json(content)
        if result is not None:
            return result
        return {"chapter_outline": {"raw": content}}


class ChapterWriter:
    """A6: Generates chapter content and handles revision."""

    SYSTEM_PROMPT = """你是一位小说家。根据章节大纲和完整的上下文包，撰写章节正文。

要求：
1. 严格遵循大纲中的场景和节拍
2. 确保角色行为和对白符合其语调卡
3. 推进待回收的伏笔（明确标注的 hook_advanced）
4. 自然融入世界观（不要"说明书式"介绍，让设定从角色行为和环境中自然露出）
5. 保持风格一致性（句长、节奏、描写比例）
6. 用描写代替直述（show, don't tell）
7. 场景过渡自然流畅
8. 最重要：开篇必须与上一章结尾自然衔接，维持故事的连续性

输出：直接输出章节正文，不需要标记或注释。

写作完成后你会被润色器自动处理，所以原文可以稍微直接一些，
但请确保内容完整、情节连贯、角色一致。"""

    REVISION_PROMPT = """你需要根据审核报告修改以下章节内容。

审核报告指出了以下需要修改的问题：
{review_issues}

请逐条修改。修改规则：
- 只修改问题涉及的部分
- 保持未提及的部分不变
- 确保修改后和新内容风格统一
- 输出修改后的完整章节正文

原文：
{original_content}

请输出修改后的完整正文："""

    def __init__(self, llm: BaseChatModel | None = None):
        self.llm = llm or get_llm()

    def _build_write_prompt(self, chapter_outline: dict, context_package: dict) -> str:
        parts: list[str] = []
        parts.append(f"章节大纲：\n{json.dumps(chapter_outline, ensure_ascii=False, indent=2)}")

        prev_content = context_package.get("prev_chapter_content", "")
        if prev_content:
            parts.append(f"上一章结尾（必须从此处自然衔接）：\n---\n{prev_content}\n---")

        recent = context_package.get("recent_summaries", [])
        if recent:
            parts.append(f"前几章摘要：\n{json.dumps(recent, ensure_ascii=False, indent=2)}")

        vol_summary = context_package.get("volume_summary", "无")
        parts.append(f"当前卷概要：{vol_summary}")

        pending_hooks = context_package.get("pending_hooks", [])
        if pending_hooks:
            parts.append(f"待推进/回收的伏笔（必须在写作中推进或回收）：\n{json.dumps(pending_hooks, ensure_ascii=False, indent=2)}")

        entity_states = context_package.get("entity_states", {})
        if entity_states:
            parts.append(f"角色/实体当前状态：\n{json.dumps(entity_states, ensure_ascii=False, indent=2)}")

        style = context_package.get("style_profile", {})
        if style:
            parts.append(f"写作风格要求：\n{json.dumps(style, ensure_ascii=False, indent=2)}")

        world = context_package.get("world_setting_chunks", [])
        if world:
            parts.append(f"世界观设定：\n{json.dumps(world, ensure_ascii=False)}")

        voices = context_package.get("character_voices", [])
        if voices:
            parts.append(f"角色语调卡：\n{json.dumps(voices, ensure_ascii=False, indent=2)}")

        return "\n\n".join(parts) + "\n\n请撰写本章正文。"

    async def write(self, chapter_outline: dict, context_package: dict) -> str:
        system = SystemMessage(content=self.SYSTEM_PROMPT)
        human = HumanMessage(content=self._build_write_prompt(chapter_outline, context_package))
        response = await self.llm.ainvoke([system, human])
        return response.content

    async def stream_write(
        self, chapter_outline: dict, context_package: dict
    ) -> AsyncIterator[str]:
        system = SystemMessage(content=self.SYSTEM_PROMPT)
        human = HumanMessage(content=self._build_write_prompt(chapter_outline, context_package))
        async for chunk in self.llm.astream([system, human]):
            if chunk.content:
                yield chunk.content

    async def revise(self, original_content: str, review_report: dict) -> str:
        issues = review_report.get("issues", [])
        issues_text = ""
        for i, issue in enumerate(issues, 1):
            issues_text += f"""
问题 {i} (严重程度: {issue.get('severity')}) — {issue.get('dimension')}
位置: {issue.get('location', '全文')}
问题描述: {issue.get('problem', '')}
修改建议: {issue.get('suggestion', '')}
"""
        prompt = self.REVISION_PROMPT.format(
            review_issues=issues_text,
            original_content=original_content,
        )
        response = await self.llm.ainvoke([SystemMessage(content=self.SYSTEM_PROMPT), HumanMessage(content=prompt)])
        return response.content

    async def stream_revise(
        self, original_content: str, review_report: dict
    ) -> AsyncIterator[str]:
        issues = review_report.get("issues", [])
        issues_text = ""
        for i, issue in enumerate(issues, 1):
            issues_text += f"""
问题 {i} (严重程度: {issue.get('severity')}) — {issue.get('dimension')}
位置: {issue.get('location', '全文')}
问题描述: {issue.get('problem', '')}
修改建议: {issue.get('suggestion', '')}
"""
        prompt = self.REVISION_PROMPT.format(
            review_issues=issues_text,
            original_content=original_content,
        )
        async for chunk in self.llm.astream([SystemMessage(content=self.SYSTEM_PROMPT), HumanMessage(content=prompt)]):
            if chunk.content:
                yield chunk.content
