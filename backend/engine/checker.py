"""A7 — Two-stage chapter reviewer with few-shot guidance.

Stage 1 — Content & Consistency (6 dimensions):
  outline_compliance, worldbuilding_consistency, character_consistency,
  plot_logic, hook_management, detail_quality

Stage 2 — Style & AI Flavor (2 dimensions):
  style_adherence, ai_flavor

Each stage gets a focused prompt with only the data it needs, plus a
few-shot example that anchors scoring calibration.  Results are merged
into a single report matching the original 8-dimension schema so the
rest of the pipeline (revision loop, routing) is unchanged.
"""

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from core.llm import get_reviewer_llm

logger = logging.getLogger(__name__)

# ── Few-shot examples ──────────────────────────────────────────

_FEW_SHOT_PASS = {
    "overall": "pass",
    "scores": {
        "outline_compliance": 8,
        "worldbuilding_consistency": 9,
        "character_consistency": 8,
        "plot_logic": 8,
        "hook_management": 7,
        "detail_quality": 7,
        "style_adherence": 8,
        "ai_flavor": 7,
    },
    "issues": [
        {
            "severity": "minor",
            "dimension": "detail_quality",
            "location": "场景2，打斗段落",
            "problem": "打斗动作偏概括，缺少一个具体感官细节（如声响或气味）",
            "suggestion": "在「掌风呼啸而过」之前加一句「空气中弥漫着焦糊的灵力味」",
        },
    ],
    "overall_comment": "章节质量合格，大纲节拍全部覆盖，角色一致性好。有两个 minor 瑕疵但不影响整体。",
}

_FEW_SHOT_REVISION = {
    "overall": "revision_needed",
    "scores": {
        "outline_compliance": 5,
        "worldbuilding_consistency": 6,
        "character_consistency": 4,
        "plot_logic": 7,
        "hook_management": 6,
        "detail_quality": 5,
        "style_adherence": 6,
        "ai_flavor": 3,
    },
    "issues": [
        {
            "severity": "major",
            "dimension": "character_consistency",
            "location": "场景1，林凡与苏婉儿的对话",
            "problem": "林凡本应话语寡淡（设定：话少不超过4句），本章说了12句台词且语气热情",
            "suggestion": "将林凡台词删至3-4句，多余语义通过动作和神态表达",
        },
        {
            "severity": "major",
            "dimension": "ai_flavor",
            "location": "全文",
            "problem": "「然而」「就在这时」「突然」分别出现6次/4次/3次，句式高度雷同",
            "suggestion": "删掉一半，用环境切换或角色动作替代过渡",
        },
        {
            "severity": "minor",
            "dimension": "outline_compliance",
            "location": "场景3",
            "problem": "大纲要求林凡发现古戒新铭文，正文中此情节缺失",
            "suggestion": "在场景3末尾插入古戒铭文发光的段落",
        },
    ],
    "overall_comment": "角色严重OOC，AI味道重，必须修改。大纲也有遗漏。",
}

# ── Stage 1: Content & Consistency ────────────────────────────

_STAGE1_SYSTEM = """你是一位资深文学编辑，负责审核小说章节的**内容与一致性**。

你需要从以下 6 个维度逐项审核，每个维度给出 0-10 分：

1. **大纲符合度** — 场景是否完整？节拍是否都覆盖？有没有遗漏或多余的内容？
2. **世界观一致性** — 有没有违反设定规则？物品/能力/规则的描述是否前后一致？
3. **角色一致性** — 性格是否前后一致？对白是否符合角色设定？行为是否符合动机？
4. **情节逻辑** — 和前章的衔接是否连贯？有没有逻辑漏洞？事件之间的因果链是否成立？
5. **钩子管理** — 该推进的钩子推进了吗？该回收的回收了吗？有没有遗漏？
6. **细节质量** — 场景描写够不够？五感描写是否充分？情绪是否到位？

对于每个发现的问题，你必须：
- severity: **major**（严重影响阅读体验/逻辑漏洞）| **minor**（风格瑕疵/细节不足）
- location: 定位到具体段落或场景（如「场景2，林凡与青云真人的对话段落」）
- problem: 具体说明问题
- suggestion: 给出具体修改范例

评分校准参考（请严格对标）：
- **9-10**：完美。专业出版级，无需任何修改。
- **7-8**：良好。有少量 minor 瑕疵，不影响阅读。
- **5-6**：及格。有明显可改进之处，需修改。
- **0-4**：不及格。存在 major 问题，必须重写。

判定规则：
- 任何维度低于 6 分 → overall = "revision_needed"
- 存在 major 级别问题 → overall = "revision_needed"
- 合计 3 个及以上 minor 问题 → overall = "revision_needed"
- 否则 → overall = "pass"

输出 JSON：
{
  "stage": "consistency",
  "scores": { "outline_compliance": 8, ... },
  "issues": [ { "severity": "major", "dimension": "...", "location": "...", "problem": "...", "suggestion": "..." } ],
  "overall_comment": "整体评价..."
}"""

_STAGE1_FEW_SHOT = f"""
以下是一个**通过**示例（仅用于参考格式与评分尺度，不要照抄分数）：

审核报告：
{json.dumps(_FEW_SHOT_PASS, ensure_ascii=False, indent=2)}

以下是一个**需修改**示例：
{json.dumps(_FEW_SHOT_REVISION, ensure_ascii=False, indent=2)}
"""

_STAGE1_USER_TEMPLATE = """请审核以下章节（仅评估**内容与一致性**，风格相关留在下一阶段）。

==== 章节大纲 ====
{outline}

==== 章节正文 ====
{content}

==== 世界观设定（关键规则） ====
{world_setting}

==== 角色档案（含语调卡） ====
{characters}

==== 钩子注册表（本章相关） ====
{hooks}

==== 前章摘要（连续性检查参考） ====
{prev_summaries}

请逐项审核第1-6维度，输出 JSON。"""

# ── Stage 2: Style & AI Flavor ───────────────────────────────

_STAGE2_SYSTEM = """你是一位文学风格编辑，专门评估小说的**写作风格**和**AI痕迹**。

你需要从以下 2 个维度审核，每个维度 0-10 分：

1. **风格符合度** — 句长/节奏/描写比例是否符合风格画像？叙事视角是否一致？
2. **AI 味道** — 有没有 AI 高频词（然而/因此/突然/就在这时）？有没有重复句式？
   角色对白是否千人一面？有没有过度说理的「说明书式」段落？

评分校准参考：
- **9-10**：读起来完全是人类作家手笔，风格鲜明
- **7-8**：偶有 AI 痕迹但不明显，整体自然
- **5-6**：AI 痕迹明显，多处可识别出机器生成
- **0-4**：一眼 AI，句式高度雷同，需要大幅重写

判定规则（此阶段独立判定，不改变 Stage 1 的 overall）：
- style_adherence < 6 或 ai_flavor < 6 → 返回 stage_overall = "revision_needed"
- 否则 → "pass"

输出 JSON：
{
  "stage": "style",
  "scores": { "style_adherence": 7, "ai_flavor": 6 },
  "issues": [ { "severity": "minor", "dimension": "ai_flavor", "location": "...", "problem": "...", "suggestion": "..." } ],
  "stage_overall": "pass" | "revision_needed"
}"""

_STAGE2_USER_TEMPLATE = """请仅评估**风格**和**AI味道**，不要评估内容（内容已在上一阶段完成）。

==== 章节正文（前 3000 字） ====
{content}

==== 风格画像 ====
{style_profile}

请逐项审核第7-8维度，输出 JSON。"""


class ChapterReviewer:
    """A7: Two-stage chapter reviewer.

    Stage 1 evaluates content & consistency (6 dimensions).
    Stage 2 evaluates style & AI flavor (2 dimensions).
    Results are merged into a single 8-dimension report.
    """

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
        logger.info(
            "A7 review start — content_len=%s outline_scenes=%s chars=%s hooks=%s",
            len(chapter_content or ""),
            len(chapter_outline.get("scenes", []) if isinstance(chapter_outline, dict) else []),
            len(characters) if isinstance(characters, list) else 0,
            len(hooks) if isinstance(hooks, list) else 0,
        )

        stage1 = await self._review_consistency(
            chapter_content=chapter_content or "",
            chapter_outline=chapter_outline or {},
            world_setting=world_setting or {},
            characters=characters or [],
            hooks=hooks or [],
            prev_summaries=prev_chapter_summaries or [],
        )

        stage2 = await self._review_style(
            chapter_content=chapter_content or "",
            style_profile=style_profile or {},
        )

        return self._merge_reports(stage1, stage2)

    # ── Stage 1 ──────────────────────────────────────────────

    async def _review_consistency(
        self,
        chapter_content: str,
        chapter_outline: dict,
        world_setting: dict,
        characters: list,
        hooks: list,
        prev_summaries: list[str],
    ) -> dict:
        # Truncate content to avoid exceeding token limits (keep ~4000 chars)
        content_snippet = chapter_content[:4000]

        # Only keep essential world-setting keys to reduce noise
        world_snippet = self._summarize_world(world_setting)

        # Only keep character names + role + voice, drop full profiles
        char_snippet = self._summarize_characters(characters)

        hooks_snippet = [
            {"hook_type": h.get("hook_type"), "description": h.get("description", ""),
             "priority": h.get("priority", "minor"), "status": h.get("status")}
            for h in (hooks or []) if isinstance(h, dict)
        ][:10]  # cap at 10 hooks

        human = _STAGE1_USER_TEMPLATE.format(
            outline=json.dumps(chapter_outline, ensure_ascii=False, indent=2)[:2000],
            content=content_snippet,
            world_setting=json.dumps(world_snippet, ensure_ascii=False, indent=2)[:2000],
            characters=json.dumps(char_snippet, ensure_ascii=False, indent=2)[:3000],
            hooks=json.dumps(hooks_snippet, ensure_ascii=False),
            prev_summaries=json.dumps(prev_summaries, ensure_ascii=False),
        )
        return await self._call_llm(_STAGE1_SYSTEM + _STAGE1_FEW_SHOT, human)

    # ── Stage 2 ──────────────────────────────────────────────

    async def _review_style(
        self,
        chapter_content: str,
        style_profile: dict,
    ) -> dict:
        # Stage 2 only needs content sample + style profile
        content_snippet = chapter_content[:3000]

        human = _STAGE2_USER_TEMPLATE.format(
            content=content_snippet,
            style_profile=json.dumps(style_profile, ensure_ascii=False, indent=2)[:2000],
        )
        stage2_system = _STAGE2_SYSTEM
        # Add one relevant few-shot for calibration
        flag = "AI 味道偏重" if any(
            w in (chapter_content or "").lower()
            for w in ("然而", "因此", "突然", "就在这时", "总而言之")
        ) else "风格自然"
        style_hint = (
            f"\n\n提示：本章初步扫描发现「{flag}」，请重点关注 AI 味道评分。\n"
        )
        return await self._call_llm(stage2_system + style_hint, human)

    # ── Merge ────────────────────────────────────────────────

    def _merge_reports(self, stage1: dict, stage2: dict) -> dict:
        """Merge two stage reports into the standard 8-dimension schema."""
        s1_scores = stage1.get("scores", {}) if isinstance(stage1, dict) else {}
        s2_scores = stage2.get("scores", {}) if isinstance(stage2, dict) else {}
        s1_issues = stage1.get("issues", []) if isinstance(stage1, dict) else []
        s2_issues = stage2.get("issues", []) if isinstance(stage2, dict) else []

        scores = {**s1_scores, **s2_scores}
        all_issues = (s1_issues if isinstance(s1_issues, list) else []) + (s2_issues if isinstance(s2_issues, list) else [])

        # overall = pass only when both stages pass
        any_major = any(i.get("severity") == "major" for i in all_issues)
        low_scores = [k for k, v in scores.items() if isinstance(v, (int, float)) and v < 6]
        minor_count = sum(1 for i in all_issues if i.get("severity") == "minor")

        if low_scores or any_major or minor_count >= 3:
            overall = "revision_needed"
        else:
            overall = "pass"

        # Combine comments
        c1 = stage1.get("overall_comment", "") if isinstance(stage1, dict) else ""
        c2 = stage2.get("stage_overall", "") if isinstance(stage2, dict) else ""
        combined = c1
        if c2:
            combined += f" | 风格阶段: {c2}"

        return {
            "overall": overall,
            "scores": scores,
            "issues": all_issues,
            "overall_comment": combined,
        }

    # ── Helpers ──────────────────────────────────────────────

    def _summarize_world(self, ws: dict) -> dict:
        """Keep only the most important world-setting fields."""
        important_keys = {"world_type", "geography", "power_system", "factions", "rules"}
        return {k: ws[k] for k in important_keys if k in ws}

    def _summarize_characters(self, chars: list) -> list:
        """Keep name + role + voice_config + arc, drop full profile."""
        result = []
        for c in (chars or []):
            if not isinstance(c, dict):
                continue
            result.append({
                "name": c.get("name", ""),
                "role": c.get("role", ""),
                "voice": c.get("voice", c.get("voice_config", {})),
                "arc": c.get("arc", []),
            })
        return result

    async def _call_llm(self, system_text: str, human_text: str) -> dict:
        """Send prompt and parse the JSON response."""
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=system_text),
                HumanMessage(content=human_text),
            ])
            return self._parse_response((response.content or ""))
        except Exception as exc:
            logger.exception("LLM call in A7 failed")
            return self._error_report(str(exc))

    def _parse_response(self, content: str) -> dict:
        from core.json_utils import extract_json_block
        result = extract_json_block(content)
        if result is not None:
            return result
        logger.warning("Failed to parse A7 response JSON (len=%s)", len(content))
        return self._error_report(content[:500])

    def _error_report(self, detail: str) -> dict:
        return {
            "scores": {},
            "issues": [{
                "severity": "major",
                "dimension": "parse_error",
                "location": "全文",
                "problem": f"审核器解析失败: {detail}",
                "suggestion": "请人工审核本章内容",
            }],
        }
