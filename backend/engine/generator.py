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

    SYSTEM_PROMPT = """你是一位小说家。你必须严格按照下方【写作结构】的流程来撰写章节正文，
不可跳过任何步骤。

==== 写作结构（必须严格遵循）====

【第一步：角色声线预演】
阅读上下文包中的角色语调卡。对于本章出场的每个角色，在心里复述：
- 此人说话的字数风格（话多/话少/沉默）
- 此人的情绪反应模式（外露/内敛/矛盾）
- 此人的习惯用语或禁忌词
在写对话时，每句台词写完后自问："这句台词换成另一个角色说，能区分吗？"
如果不能区分 → 重写，直到声音独特为止。

【第二步：逐场景写作 — 节拍清单制】
上下文包中提供了一个【节拍清单】，里面列出了本章每个场景必须完成的元素：
- purpose（叙事目的）→ 必须达成
- key_beats（关键节拍）→ 必须全部覆盖
- emotion_curve（情绪曲线）→ 必须体现起点和终点
- hook_plant / hook_advanced（伏笔操作）→ 必须明确写入
- information_revealed（信息揭示）→ 必须自然呈现

每个场景写完后，对照节拍清单逐项打勾。严禁遗漏任何 beat。
如果某个 beat 在写作过程中发现难以融入，不要跳过 —
调整场景事件或对话，使 beat 能够自然嵌入。

【第三步：世界观融入规则 — 禁止说明书】
世界观信息必须通过以下方式自然露出，严禁使用"说明书式"的旁白介绍：
❌ 禁止：「这个世界分为五大境界：练气、筑基、金丹、元婴、化神。」
✅ 正确：角色在行动中体现 —「他咬牙将灵力压缩到丹田深处——还不够，离筑基只差一线。」
❌ 禁止：「青云宗是大陆三大宗门之一，底蕴深厚。」
✅ 正确：通过角色的眼睛 —「山门前十二根通天石柱让林凡倒吸了一口凉气，他从未见过如此气派的宗门。」
❌ 禁止：角色内心大段解释设定（"他知道这是因为灵根属性的原因..."）
✅ 正确：让读者通过角色的遭遇和感受自行推断

规则：
- 设定信息每次透露不超过一句话
- 通过角色的感知（视觉/听觉/触觉/反应）传递，而非旁白直述
- 如果一段设定解释超过 20 字 → 删掉，改为角色体验
- 禁止"众所周知""在这个世界""根据修炼体系"等教科书式过渡词

【第四步：场景过渡与连贯性】
- 上一章的结尾文本已提供，第一章的第一个字必须从那里自然延续
- 场景之间的过渡要有因果链（因为 A 发生了，所以 B 发生）
- 同一场景内的时间跳跃用空行分隔

【第五步：草稿自审】
全文写完后，再次对照节拍清单逐项检查，如有遗漏，在对应位置补写。

==== 输出格式 ====
直接输出章节正文。不需要任何前言、标记或 JSON 包装。
正文完成后润色器会自动处理表达层面的优化。"""

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

        # ── 0. Chapter outline (full JSON for reference) ──
        parts.append(f"章节大纲（完整）：\n{json.dumps(chapter_outline, ensure_ascii=False, indent=2)}")

        # ── 1. Beat checklist — extracted from scene outlines ──
        beat_checklist = self._build_beat_checklist(chapter_outline)
        parts.append(beat_checklist)

        # ── 2. Voice rehearsal — extracted from character voice cards ──
        voices = context_package.get("character_voices", [])
        if voices:
            voice_section = self._build_voice_rehearsal(voices)
            parts.append(voice_section)

        # ── 3. Previous chapter ending (continuity anchor) ──
        prev_content = context_package.get("prev_chapter_content", "")
        if prev_content:
            parts.append(f"上一章结尾（必须从此处自然衔接）：\n---\n{prev_content}\n---")

        # ── 4. Context summaries ──
        recent = context_package.get("recent_summaries", [])
        if recent:
            parts.append(f"前几章摘要：\n{json.dumps(recent, ensure_ascii=False, indent=2)}")

        vol_summary = context_package.get("volume_summary", "无")
        parts.append(f"当前卷概要：{vol_summary}")

        # ── 5. Hook tracking ──
        pending_hooks = context_package.get("pending_hooks", [])
        if pending_hooks:
            parts.append(f"待推进/回收的伏笔（必须在写作中推进或回收）：\n{json.dumps(pending_hooks, ensure_ascii=False, indent=2)}")

        # ── 6. Entity state ──
        entity_states = context_package.get("entity_states", {})
        if entity_states:
            parts.append(f"角色/实体当前状态：\n{json.dumps(entity_states, ensure_ascii=False, indent=2)}")

        # ── 7. Style constraints ──
        style = context_package.get("style_profile", {})
        if style:
            parts.append(f"写作风格要求：\n{json.dumps(style, ensure_ascii=False, indent=2)}")

        # ── 8. Worldbuilding (use sparingly, via character experience) ──
        world = context_package.get("world_setting_chunks", [])
        if world:
            parts.append(f"世界观设定（仅通过角色体验自然露出，禁止说明书式介绍）：\n{json.dumps(world, ensure_ascii=False)}")

        # ── 9. Vector-retrieved historical fragments ──
        past_chunks = context_package.get("past_chapter_chunks", [])
        if past_chunks:
            parts.append(f"【向量检索】相关历史片段（用于保持细节连贯）：\n{json.dumps(past_chunks, ensure_ascii=False)}")

        return "\n\n".join(parts) + "\n\n请严格按照【写作结构】中的五步流程撰写本章正文。"

    # ── Structured section builders ──────────────────────────

    @staticmethod
    def _build_beat_checklist(chapter_outline: dict) -> str:
        """Build a human-readable beat checklist from chapter outline scenes.

        Each scene's must-include elements are extracted and formatted so
        the LLM can check them off as it writes.
        """
        lines: list[str] = []
        lines.append("=" * 50)
        lines.append("【节拍清单】— 写作时必须逐项覆盖，写完后逐项打勾自审")
        lines.append("=" * 50)

        outline = chapter_outline.get("chapter_outline", chapter_outline)
        scenes = outline.get("scenes", [])
        if not scenes:
            lines.append("（无场景大纲，请根据完整大纲自由写作）")
            return "\n".join(lines)

        for scene in scenes:
            idx = scene.get("scene", "?")
            lines.append(f"\n{'─' * 40}")
            lines.append(f"场景 {idx}")

            purpose = scene.get("purpose", "")
            if purpose:
                lines.append(f"  □ 叙事目的：{purpose}")

            chars = scene.get("characters", [])
            if chars:
                char_list = "、".join(
                    f"{c['name']}（{c.get('motivation', '动机不明')}）"
                    if isinstance(c, dict) else str(c)
                    for c in chars
                )
                lines.append(f"  □ 出场角色：{char_list}")

            setting = scene.get("setting", "")
            if setting:
                lines.append(f"  □ 场景地点：{setting}")

            emotion = scene.get("emotion_curve", "")
            if emotion:
                lines.append(f"  □ 情绪曲线：{emotion}")

            beats = scene.get("key_beats", [])
            if beats:
                lines.append(f"  □ 关键节拍（{len(beats)}项）：")
                for b in beats:
                    lines.append(f"      ☐ {b}")

            info = scene.get("information_revealed", "")
            if info:
                lines.append(f"  □ 信息揭示：{info}")

            hook_plant = scene.get("hook_plant", "")
            if hook_plant:
                lines.append(f"  □ 埋设伏笔：{hook_plant}")

            hook_adv = scene.get("hook_advanced", [])
            if hook_adv:
                hooks_str = "、".join(hook_adv)
                lines.append(f"  □ 推进伏笔：{hooks_str}")

            transition = scene.get("transition", "")
            if transition:
                lines.append(f"  □ 过渡方式：{transition}")

        lines.append(f"\n{'=' * 50}")
        lines.append("写作完成后，请对照以上清单逐项打勾。遗漏任何 beat 视为不合格。")
        lines.append("=" * 50)
        return "\n".join(lines)

    @staticmethod
    def _build_voice_rehearsal(voices: list[dict]) -> str:
        """Build a voice rehearsal section from character voice cards.

        Extracts the key distinguishing traits for each character so the
        LLM can mentally rehearse before writing dialogue.
        """
        lines: list[str] = []
        lines.append("=" * 50)
        lines.append("【角色声线预演】— 写每句台词前必须回忆该角色的声音特征")
        lines.append("=" * 50)

        for v in voices:
            name = v.get("name", v.get("character_name", "未知角色"))
            lines.append(f"\n◆ {name}")

            # Speech volume/style
            speech_style = v.get("speech_style") or v.get("dialogue_style", "")
            if speech_style:
                lines.append(f"  说话风格：{speech_style}")

            word_count = v.get("word_count") or v.get("verbosity", "")
            if word_count:
                lines.append(f"  话量：{word_count}")

            # Emotional pattern
            emotion = v.get("emotion_pattern") or v.get("emotional_response", "")
            if emotion:
                lines.append(f"  情绪模式：{emotion}")

            # Signature phrases / taboo words
            signature = v.get("signature_phrases") or v.get("catchphrases", [])
            if signature:
                phrases = "、".join(signature if isinstance(signature, list) else [signature])
                lines.append(f"  习惯用语：{phrases}")

            taboo = v.get("taboo_words") or v.get("forbidden_words", [])
            if taboo:
                words = "、".join(taboo if isinstance(taboo, list) else [taboo])
                lines.append(f"  禁忌词：{words}")

            # Inner monologue style
            inner = v.get("inner_monologue_style", "")
            if inner:
                lines.append(f"  内心独白风格：{inner}")

            # Distinguishing trait — quick mental check
            trait = v.get("distinguishing_trait") or v.get("voice_note", "")
            if trait:
                lines.append(f"  辨识要点：{trait}")

        lines.append(f"\n{'=' * 50}")
        lines.append("每句台词写完后自问：「这句换成另一个角色说，能区分吗？」")
        lines.append("不能区分 → 重写，直到声音独特为止。")
        lines.append("=" * 50)
        return "\n".join(lines)

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
