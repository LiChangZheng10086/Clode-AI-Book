"""A7 Review agent: Chapter quality review across 8 dimensions."""

import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from core.llm import get_reviewer_llm


class ChapterReviewer:
    """A7: Reviews chapter content across 8 dimensions.

    Produces structured report. If issues found, sends report back
    to A6 Writer for revision (max 3 rounds).
    """

    SYSTEM_PROMPT = """你是一位资深文学编辑，负责审核小说章节的质量。

你需要从以下 8 个维度逐项审核，每个维度给出 0-10 分：

1. 大纲符合度 — 场景是否完整？节拍是否都覆盖？有没有遗漏或多余的内容？
2. 世界观一致性 — 有没有违反设定规则？物品/能力/规则的描述是否前后一致？
3. 角色一致性 — 性格是否前后一致？对白是否符合语调卡？行为是否符合动机和角色档案？
4. 情节逻辑 — 和前章的衔接是否连贯？有没有逻辑漏洞？事件之间的因果链是否成立？
5. 钩子管理 — 该推进的钩子推进了吗？该回收的回收了吗？有没有遗漏？
6. 风格符合度 — 句长/节奏/描写比例是否符合风格画像？
7. AI 味道 — 有没有 AI 高频句式（然而/因此/突然/就在这时）？有没有重复句式？有没有过度说理？
   角色对白是否千人一面？
8. 细节质量 — 场景描写够不够？五感描写是否充分？情绪是否到位？

对于每个发现的问题，你必须：
- severity: major（严重影响阅读体验/逻辑漏洞）| minor（风格瑕疵/细节不足）
- location: 定位到具体段落或场景（如"场景2，林凡与青云真人的对话段落"）
- problem: 具体说明问题
- suggestion: 给出具体修改范例（不要只说"改一下"，要给出改法）

输出 JSON：
{
  "overall": "pass" | "revision_needed",
  "scores": {
    "outline_compliance": 8,
    "worldbuilding_consistency": 9,
    "character_consistency": 5,
    "plot_logic": 8,
    "hook_management": 7,
    "style_adherence": 8,
    "ai_flavor": 6,
    "detail_quality": 7
  },
  "issues": [
    {
      "severity": "major",
      "dimension": "character_consistency",
      "location": "场景2，林凡与青云真人的对话",
      "problem": "林凡说了12句台词，语气热情主动，但语调卡标注'话少、冷淡、不超过4句'",
      "suggestion": "将林凡台词删减至3-4句，多余信息通过神态和动作传达。例如：原文'师傅，古戒上出现了新的铭文，我不太明白这是什么意思' → 改为：林凡低头看了看古戒，没说话，只是把戒面转向青云真人。"
    }
  ],
  "overall_comment": "整体评价..."
}

overall 判定规则：
- 任何维度低于 6 分 → revision_needed
- 存在 major 级别问题 → revision_needed
- 3 个及以上 minor 问题 → revision_needed
- 否则 → pass"""

    def __init__(self, llm: BaseChatModel | None = None):
        self.llm = llm or get_reviewer_llm()

    async def review(
        self,
        chapter_content: str,
        chapter_outline: dict,
        world_setting: dict,
        characters: list,
        style_profile: dict,
        hooks: list,
        prev_chapter_summaries: list[str],
    ) -> dict:
        system = SystemMessage(content=self.SYSTEM_PROMPT)
        human = HumanMessage(content=f"""请审核以下章节内容。

==== 章节大纲 ====
{json.dumps(chapter_outline, ensure_ascii=False, indent=2)}

==== 章节正文 ====
{chapter_content}

==== 世界观设定 ====
{json.dumps(world_setting, ensure_ascii=False, indent=2)}

==== 角色档案（含语调卡） ====
{json.dumps(characters, ensure_ascii=False, indent=2)}

==== 风格画像 ====
{json.dumps(style_profile, ensure_ascii=False, indent=2)}

==== 钩子注册表（本章相关） ====
{json.dumps(hooks, ensure_ascii=False, indent=2)}

==== 前章摘要（连续性检查参考） ====
{json.dumps(prev_chapter_summaries, ensure_ascii=False)}

请逐项审核，输出结构化 JSON 审核报告。""")
        response = await self.llm.ainvoke([system, human])
        return self._parse_response(response.content)

    def _parse_response(self, content: str) -> dict:
        try:
            start = content.index("{")
            end = content.rindex("}") + 1
            return json.loads(content[start:end])
        except (ValueError, json.JSONDecodeError):
            return {
                "overall": "revision_needed",
                "scores": {},
                "issues": [{"severity": "major", "dimension": "parse_error", "problem": "Failed to parse review JSON", "suggestion": content[:500]}],
            }
