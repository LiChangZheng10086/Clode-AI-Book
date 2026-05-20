"""Global consistency checker — scans all chapter summaries for contradictions."""

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from core.llm import get_planning_llm

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是一位小说世界逻辑审查员。请审查所有已生成章节，找出逻辑矛盾和不一致之处。

检查维度：
1. **世界观矛盾** — 是否违反了已设定的世界规则/力量体系？
2. **角色不一致** — 角色性格、能力、动机是否前后矛盾？
3. **情节漏洞** — 时间线冲突、因果链断裂、事件顺序混乱？
4. **伏笔管理** — 已埋下的伏笔是否被遗忘（超过10章未推进即算遗忘）？
5. **设定漂移** — 早期设定在后期是否被悄然改变或违背？

对于每个发现的问题，明确标注涉及的具体章节范围。

输出 JSON：
{
  "score": <0-10 整数, 10=无任何问题>,
  "issues": [
    {
      "severity": "major" | "minor",
      "dimension": "worldbuilding" | "character" | "plot" | "hook" | "setting_drift",
      "location": "涉及章节范围，如「第3-5章」或「第8章」",
      "description": "具体问题描述（50字以内）",
      "suggestion": "修复建议（50字以内）"
    }
  ]
}

如果没有发现任何问题，issues 返回空数组。"""


class ConsistencyChecker:
    """Check story-wide consistency by scanning all chapter summaries."""

    def __init__(self, llm: BaseChatModel | None = None):
        self.llm = llm or get_planning_llm()

    async def check(
        self,
        chapter_summaries: list[str],
        world_setting: dict | None = None,
        characters: list[dict] | None = None,
        pending_hooks: list[dict] | None = None,
    ) -> dict:
        """Run consistency check across all completed chapters.

        Returns: {score, issues, summary}
        """
        try:
            summaries_text = "\n\n".join(
                f"第{i+1}章: {s[:300]}"
                for i, s in enumerate(chapter_summaries)
            )
            if not summaries_text:
                return {"score": 10, "issues": [], "summary": "暂无章节，跳过检查"}

            world_text = json.dumps(
                world_setting or {}, ensure_ascii=False, indent=2
            )[:2000]
            chars_text = json.dumps(
                characters or [], ensure_ascii=False, indent=2
            )[:2000]
            hooks_text = json.dumps(
                pending_hooks or [], ensure_ascii=False, indent=2
            )[:2000]

            human = f"""==== 章节摘要 ====
{summaries_text}

==== 世界观设定 ====
{world_text}

==== 角色档案 ====
{chars_text}

==== 待处理伏笔 ====
{hooks_text}

请基于以上信息，检查所有已完成章节中的逻辑矛盾和不一致之处。"""

            response = await self.llm.ainvoke([
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=human),
            ])

            return self._parse(response.content or "")

        except Exception:
            logger.exception("Consistency check failed")
            return {
                "score": -1,
                "issues": [],
                "summary": "一致性检查执行失败",
            }

    def _parse(self, content: str) -> dict:
        try:
            start = content.index("{")
            end = content.rindex("}") + 1
            data = json.loads(content[start:end])
            return {
                "score": data.get("score", -1),
                "issues": data.get("issues", []),
                "summary": data.get("summary", ""),
            }
        except (ValueError, json.JSONDecodeError):
            logger.warning("Failed to parse consistency check result")
            return {"score": -1, "issues": [], "summary": "检查结果解析失败"}
