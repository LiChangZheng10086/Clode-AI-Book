"""A5-A6 Writing agents: Chapter Outliner and Chapter Writer."""

import json
import logging
from typing import AsyncIterator

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from core.json_utils import parse_llm_json, parse_llm_json_array
from core.llm import get_llm, get_planning_llm

logger = logging.getLogger(__name__)


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
        return parse_llm_json(content, fallback_key="chapter_outline")


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

    PATCH_PROMPT = """你是一位精准修改师。你的任务是根据审核报告，对原文进行**最小粒度的精确修改**。

审核报告指出了以下需要修改的问题：
{review_issues}

请你针对每个问题输出一个 JSON Patch。**严禁重写整个段落**，只修改有问题的部分。

==== 修改规则 ====
1. 每个 patch 的 target 必须**与原文逐字匹配**（标点符号、空格都不能错）
2. target 长度不超过 200 个字（整句或相邻几句话）
3. replacement 只替换 target 中**有问题的部分**，不要改动周围上下文
4. 不需要修改的部分**绝不**出现在 patches 里
5. 多个 patch 按在文中出现的先后顺序排列

==== 操作流程 ====
修改工作在原始文本上依次执行。从原始文本开头开始，找到最早的 target，
替换为 replacement。每应用一个 patch 之后，从替换后的文本开头重新扫描，
找下一个 target。**所以 patches 必须按文中先后顺序排列，且不要重叠。**

==== 输出格式 ====
```json
[
  {{
    "target": "原文中必须替换的段落（与原文完全一致）",
    "replacement": "替换后的新段落",
    "reason": "修复的问题编号"
  }}
]
```

如果没有需要修改的内容（审核误判），返回空数组 []。

==== 示例 ====
原句：「林凡微微一笑，然后说道：『师傅，古戒上出现了新的铭文，我不太明白这是什么意思。』只因师傅曾教导他要虚心求教。」
审核意见：林凡话太多（设定话少），且「然后」是 AI 高频词。

预期输出：
```json
[
  {{
    "target": "林凡微微一笑，然后说道：『师傅，古戒上出现了新的铭文，我不太明白这是什么意思。』只因师傅曾教导他要虚心求教。",
    "replacement": "林凡低头看了看古戒，没说话，只是把戒面转向青云真人。——只因师傅曾教导他要虚心求教。"
  }}
]
```"""

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

        past_chunks = context_package.get("past_chapter_chunks", [])
        if past_chunks:
            parts.append(f"【向量检索】相关历史片段（用于保持细节连贯）：\n{json.dumps(past_chunks, ensure_ascii=False)}")

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

    # ── Revision via structured patches ───────────────────────

    async def revise(self, original_content: str, review_report: dict) -> str:
        patches = await self._generate_patches(original_content, review_report)
        if patches:
            return self._apply_patches(original_content, patches)
        return original_content

    async def stream_revise(
        self, original_content: str, review_report: dict
    ) -> AsyncIterator[str]:
        patches = await self._generate_patches(original_content, review_report)
        if patches:
            revised = self._apply_patches(original_content, patches)
        else:
            revised = original_content
        yield revised

    async def _generate_patches(
        self, original_content: str, review_report: dict
    ) -> list[dict]:
        """Ask LLM for structured patches, parse and validate."""
        issues = review_report.get("issues", [])
        issues_text = ""
        for i, issue in enumerate(issues, 1):
            issues_text += f"""
问题 {i} (严重程度: {issue.get('severity')}) — {issue.get('dimension')}
位置: {issue.get('location', '全文')}
问题描述: {issue.get('problem', '')}
修改建议: {issue.get('suggestion', '')}
"""

        prompt = self.PATCH_PROMPT.format(
            review_issues=issues_text,
            original_content=original_content,
        )
        try:
            response = await self.llm.ainvoke([SystemMessage(content=prompt)])
            return self._parse_patches((response.content or ""))
        except Exception:
            logger.exception("A6 _generate_patches failed")
            return []

    def _parse_patches(self, content: str) -> list[dict]:
        patches = parse_llm_json_array(content)
        if not patches:
            return []
        valid = []
        for p in patches:
            if isinstance(p, dict) and p.get("target") and isinstance(p["target"], str):
                p["replacement"] = p.get("replacement", "")
                valid.append(p)
        if not valid and patches:
            logger.warning("No valid patches found in A6 patch array (got %d items)", len(patches))
        return valid

    def _apply_patches(self, original: str, patches: list[dict]) -> str:
        """Apply patches sequentially. Each patch replaces an exact match.

        Patches MUST be in document order (earliest first) and MUST NOT overlap.
        After each replacement, the next patch is searched in the modified text.
        """
        result = original
        applied = 0
        skipped = 0

        for i, patch in enumerate(patches):
            target = patch["target"]
            replacement = patch["replacement"]
            pos = result.find(target)

            if pos != -1:
                result = result[:pos] + replacement + result[pos + len(target):]
                applied += 1
            else:
                # Retry with stripped whitespace (fuzzy fallback)
                target_stripped = target.strip()
                pos2 = result.find(target_stripped)
                if pos2 != -1:
                    result = result[:pos2] + replacement + result[pos2 + len(target_stripped):]
                    applied += 1
                else:
                    skipped += 1

        logger.info(
            "A6 revise: applied %d patches, skipped %d (out of %d)",
            applied, skipped, len(patches),
        )
        return result
