"""A1-A4 Preprocessing agents: Worldbuilding, Character, Style, Outline."""

import json
import logging
from typing import AsyncIterator

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from core.json_utils import extract_json_block, parse_llm_json
from core.llm import get_planning_llm

logger = logging.getLogger(__name__)

_SKIP_ASKING_HINT = (
    "\n\n【重要】用户已在对应维度提供了较完整的构想（见上文专项输入）。"
    "请直接基于用户输入完善并输出完整 JSON，status 必须为 \"complete\"，"
    "不要生成 status: \"asking\" 的决策点。"
)

# Backward-compatible aliases for modules that still import from planner.
# New code should import directly from core.json_utils.
_extract_json = extract_json_block


def _parse_llm_response(content: str, fallback_key: str) -> dict:
    """Parse LLM response, returning a dict with structured fallback on failure."""
    return parse_llm_json(content, fallback_key=fallback_key)


class WorldbuildingAgent:
    """A1: Generates and refines world setting based on user input."""

    SYSTEM_PROMPT = """你是一位资深世界观架构师，专长于为小说构建完整、自洽的世界体系。

基于用户的输入，分阶段完善小说的世界观：

第一阶段 — 类型识别与核心体系：
从用户输入判断世界类型（修真/魔法/科幻/都市异能/末日/武侠等），识别已有设定，
列出缺失的核心维度。如果核心维度不明确（如无法判断修炼体系类型、世界规模），
生成一个决策点向用户提问。如果核心维度已明确，则直接进入第二阶段。

第二阶段 — 结构补全：
自动完善以下维度：
- world_type: 世界类型和时代背景
- geography: 地理格局（大陆/城市/特殊地点）
- power_system: 力量体系（境界/等级/规则/代价）
- factions: 势力分布（宗门/国家/组织/种族）
- items: 关键物品（法宝/科技/文物）
- rules: 世界规则（禁忌/天道/物理法则）
- history: 重大历史事件

第三阶段 — 输出结构化的世界观设定 JSON。

原则：
1. 所有设定内部自洽，没有矛盾
2. 力量体系必须有代价和限制，不能无限膨胀
3. 势力之间的关系要有张力和冲突可能
4. 为后续角色和大纲留出扩展空间

输出格式：
当需要用户决策时：
{"status": "asking", "phase": "core_system", "decision_point": {"question": "...", "options": [...], "recommendation": {...}}}

当世界观完整时：
{"status": "complete", "world_setting": {"world_type": "...", "geography": {...}, "power_system": {...}, "factions": [...], "items": [...], "rules": [...], "history": [...]}}"""

    def __init__(self, llm: BaseChatModel | None = None):
        self.llm = llm or get_planning_llm()

    async def generate(
        self, user_input: str, user_world_setting: str = "",
        decision_answer: str | None = None,
    ) -> dict:
        messages = [SystemMessage(content=self.SYSTEM_PROMPT)]
        context = f"用户总体构想：\n{user_input}"
        if user_world_setting:
            context += f"\n\n用户对世界观的构想（请在此基础上完善和扩展）：\n{user_world_setting}"
        if decision_answer:
            context += f"\n\n用户对上一步决策的回答：{decision_answer}\n请继续下一阶段。"
        if user_world_setting and len(user_world_setting.strip()) >= 80:
            context += _SKIP_ASKING_HINT
        messages.append(HumanMessage(content=context))
        logger.info("A1 LLM 请求开始 (context_len=%s)", len(context))
        response = await self.llm.ainvoke(messages)
        logger.info("A1 LLM 请求完成 (response_len=%s)", len(response.content or ""))
        return self._parse_response(response.content)

    async def stream_generate(
        self, user_input: str, user_world_setting: str = "",
        decision_answer: str | None = None,
    ) -> AsyncIterator[dict]:
        messages = [SystemMessage(content=self.SYSTEM_PROMPT)]
        context = f"用户总体构想：\n{user_input}"
        if user_world_setting:
            context += f"\n\n用户对世界观的构想（请在此基础上完善和扩展）：\n{user_world_setting}"
        if decision_answer:
            context += f"\n\n用户对上一步决策的回答：{decision_answer}\n请继续下一阶段，输出完整 JSON。"
        messages.append(HumanMessage(content=context))
        async for chunk in self.llm.astream(messages):
            if chunk.content:
                yield {"type": "stream", "content": chunk.content}

    def _parse_response(self, content: str) -> dict:
        return _parse_llm_response(content, "world_setting")


class CharacterAgent:
    """A3: Generates characters from user input and world setting."""

    SYSTEM_PROMPT = """你是一位角色设计师，专长于为小说创造有深度的人物。

基于用户输入和已有的世界观设定，分阶段完善角色体系：

第一阶段 — 主角定位：
根据用户输入和世界观，确定主角的核心人设。如果用户输入中主角的出身、
性格、动机不明确，生成决策点向用户提问。否则自动补全并进入下一阶段。

第二阶段 — 角色系统生成：
- protagonist: 完善主角 {name, role: "protagonist", profile: {appearance, personality, background, motivation, flaws}, voice: {style, catchphrase, taboo}, arc: [{stage, chapter_range, description}]}
- supporting_cast: 生成配角 [{name, role: "supporting", profile, voice, relationship_to_protagonist, function_in_story}]
- antagonist: 生成反派 [{name, role: "antagonist", profile, voice, motivation, layers (不要纯恶人), arc}]
- npcs: 生成功能性 NPC [{name, role: "npc", function: "..."}]

第三阶段 — 角色关系图：
生成角色间的关系网 [{source, target, relation_type, description, tension_level}]

原则：
1. 反派要有说服力的动机和层次，不能是纯恶人
2. 每个角色有独特的说话方式（语调卡），从台词能区分是谁
3. 成长弧线标注章节区间，和大纲联动
4. 配角的功能要明确：推动剧情/揭示主题/映衬主角/提供喜剧 relief
5. 角色数量与目标章节数匹配（150章约主+配+反+NPC 15-25个核心角色）

输出格式同 Agent 1：有决策点时 status: "asking"，完整时 status: "complete"。"""

    def __init__(self, llm: BaseChatModel | None = None):
        self.llm = llm or get_planning_llm()

    async def generate(
        self,
        user_input: str,
        user_characters: str = "",
        world_setting: dict | None = None,
        decision_answer: str | None = None,
    ) -> dict:
        messages = [SystemMessage(content=self.SYSTEM_PROMPT)]
        context = f"用户总体构想：\n{user_input}"
        if user_characters:
            context += f"\n\n用户对角色的构想（请在此基础上完善和扩展）：\n{user_characters}"
        if world_setting:
            context += f"\n\n已有世界观设定：\n{json.dumps(world_setting, ensure_ascii=False, indent=2)}"
        if decision_answer:
            context += f"\n\n用户对上一步决策的回答：{decision_answer}\n请继续下一阶段。"
        if user_characters and len(user_characters.strip()) >= 80:
            context += _SKIP_ASKING_HINT
        messages.append(HumanMessage(content=context))
        logger.info("A3 LLM 请求开始 (context_len=%s)", len(context))
        response = await self.llm.ainvoke(messages)
        logger.info("A3 LLM 请求完成 (response_len=%s)", len(response.content or ""))
        return self._parse_response(response.content)

    async def stream_generate(
        self,
        user_input: str,
        user_characters: str = "",
        world_setting: dict | None = None,
        decision_answer: str | None = None,
    ) -> AsyncIterator[dict]:
        messages = [SystemMessage(content=self.SYSTEM_PROMPT)]
        context = f"用户总体构想：\n{user_input}"
        if user_characters:
            context += f"\n\n用户对角色的构想（请在此基础上完善和扩展）：\n{user_characters}"
        if world_setting:
            context += f"\n\n已有世界观设定：\n{json.dumps(world_setting, ensure_ascii=False, indent=2)}"
        if decision_answer:
            context += f"\n\n用户对上一步决策的回答：{decision_answer}\n请继续下一阶段，输出完整 JSON。"
        messages.append(HumanMessage(content=context))
        async for chunk in self.llm.astream(messages):
            if chunk.content:
                yield {"type": "stream", "content": chunk.content}

    def _parse_response(self, content: str) -> dict:
        return _parse_llm_response(content, "characters")


class StyleAgent:
    """A2: Generates writing style profile."""

    SYSTEM_PROMPT = """你是一位文学编辑，专长于分析和制定写作风格指南。

基于用户偏好、参考文本、世界观和角色体系，生成可量化可执行的风格参数。

你需要确定以下维度：
- narrative_pov: 叙事视角（第一人称/第三人称有限/第三人称全知/多视角）
- tense: 时态（过去式/现在式）
- tone: 情感基调（热血/冷峻/温情/暗黑/幽默等）
- sentence: {avg_length_range: [min, max], variance: "high"|"medium"|"low", rhythm_note: "..."}
- paragraph: {avg_sentences: [min, max], dialogue_density: 0.0-1.0}
- dialogue: {style: "...", inner_monologue: bool, inner_monologue_style: "..."}
- description: {action_ratio, dialogue_ratio, exposition_ratio, show_vs_tell: "..."}
- banned: {transitions: [...], cliches: [...], patterns: [...]}
- chapter_structure: {opening: "...", closing: "..."}

如果用户只给了模糊关键词（如"热血"），你需要：
1. 从关键词推导具体参数
2. 如果风格维度有重大分歧可能性（如叙事视角不确定），提问
3. 否则从关键词展开并输出完整风格画像

原则：
1. 所有参数必须可量化、可执行
2. 禁用词列表要具体（不能只是"避免重复"这种泛泛之谈）
3. 章节开头和结尾方式要给出具体模板
4. 结合角色数量调整对话密度（角色多→对话密度可高）

输出格式同 Agent 1。"""

    def __init__(self, llm: BaseChatModel | None = None):
        self.llm = llm or get_planning_llm()

    async def generate(
        self,
        user_input: str,
        user_style: str = "",
        world_setting: dict | None = None,
        characters: list | None = None,
        decision_answer: str | None = None,
    ) -> dict:
        messages = [SystemMessage(content=self.SYSTEM_PROMPT)]
        context = f"用户总体构想：\n{user_input}"
        if user_style:
            context += f"\n\n用户对风格的构想（请在此基础上完善和扩展）：\n{user_style}"
        if world_setting:
            context += f"\n\n世界观设定：\n{json.dumps(world_setting, ensure_ascii=False, indent=2)}"
        if characters:
            context += f"\n\n角色列表：\n{json.dumps(characters, ensure_ascii=False, indent=2)}"
        if decision_answer:
            context += f"\n\n用户对上一步决策的回答：{decision_answer}\n请继续下一阶段。"
        if user_style and len(user_style.strip()) >= 80:
            context += _SKIP_ASKING_HINT
        messages.append(HumanMessage(content=context))
        logger.info("A2 LLM 请求开始 (context_len=%s)", len(context))
        response = await self.llm.ainvoke(messages)
        logger.info("A2 LLM 请求完成 (response_len=%s)", len(response.content or ""))
        return self._parse_response(response.content)

    async def stream_generate(
        self,
        user_input: str,
        user_style: str = "",
        world_setting: dict | None = None,
        characters: list | None = None,
        decision_answer: str | None = None,
    ) -> AsyncIterator[dict]:
        messages = [SystemMessage(content=self.SYSTEM_PROMPT)]
        context = f"用户总体构想：\n{user_input}"
        if user_style:
            context += f"\n\n用户对风格的构想（请在此基础上完善和扩展）：\n{user_style}"
        if world_setting:
            context += f"\n\n世界观设定：\n{json.dumps(world_setting, ensure_ascii=False, indent=2)}"
        if characters:
            context += f"\n\n角色列表：\n{json.dumps(characters, ensure_ascii=False, indent=2)}"
        if decision_answer:
            context += f"\n\n用户对上一步决策的回答：{decision_answer}\n请继续，输出完整的 JSON 风格画像。"
        messages.append(HumanMessage(content=context))
        async for chunk in self.llm.astream(messages):
            if chunk.content:
                yield {"type": "stream", "content": chunk.content}

    def _parse_response(self, content: str) -> dict:
        return _parse_llm_response(content, "style_profile")


class OutlineAgent:
    """A4: Generates full novel outline from all preprocessed data."""

    SYSTEM_PROMPT = """你是一位小说结构师，专长于设计故事结构和章节编排。

聚合世界观、角色、风格三方面的数据，生成完整的小说大纲。

你需要设计的是**整本书的宏观走向**，不是具体某一章的场景细节。

要求：
1. 确定故事结构（三幕式/五卷式/篇章式），按目标章节数均匀分布
2. 为每卷定义主题、主要剧情走向、本卷高潮
3. 为每章写一句话概要（核心事件），不要展开场景节拍
4. 标注关键伏笔的种植卷/章和回收卷/章
5. 标注主角在本卷的成长阶段

输出 JSON 格式：
{
  "status": "complete",
  "novel_outline": {
    "title": "...",
    "total_chapters": 100,
    "structure": "五卷式",
    "story_arc": "一句话概括全书主线",
    "volumes": [{
      "index": 1,
      "title": "...",
      "summary": "本卷主线剧情与核心冲突（100-200字）",
      "protagonist_stage": "主角在本卷的成长阶段",
      "chapters": [{
        "index": 1,
        "title": "...",
        "summary": "一句话核心事件",
        "target_word_count": 3000
      }]
    }]
  }
}

重要约束：
- 每章只需 title + summary（一句话），不要展开 scenes/beats（场景节拍由后续 Agent 按需生成）
- 卷的数量由目标章节数决定，建议每卷 8-15 章
- 章节总数尽量接近目标章节数
- 伏笔种植和回收在 volume.summary 中提及即可
- JSON 必须完整闭合，确保所有括号匹配

如果目标章节数和故事规模不匹配，生成决策点向用户确认结构方案。"""

    def __init__(self, llm: BaseChatModel | None = None):
        self.llm = llm or get_planning_llm()

    async def generate(
        self,
        user_input: str,
        user_outline: str = "",
        world_setting: dict = {},
        style_profile: dict = {},
        characters: list = [],
        target_chapters: int = 100,
        decision_answer: str | None = None,
    ) -> dict:
        messages = [SystemMessage(content=self.SYSTEM_PROMPT)]
        context = f"""用户总体构想：{user_input}"""
        if user_outline:
            context += f"\n\n用户对大纲的构想（请在此基础上完善和扩展）：\n{user_outline}"
        context += f"""
目标章节数：{target_chapters}

世界观设定：
{json.dumps(world_setting, ensure_ascii=False, indent=2)}

角色体系：
{json.dumps(characters, ensure_ascii=False, indent=2)}

风格画像：
{json.dumps(style_profile, ensure_ascii=False, indent=2)}"""
        if decision_answer:
            context += f"\n\n用户对上一步决策的回答：{decision_answer}\n请继续，输出完整的章节大纲 JSON。"
        if user_outline and len(user_outline.strip()) >= 80:
            context += _SKIP_ASKING_HINT
        messages.append(HumanMessage(content=context))
        logger.info("A4 LLM 请求开始 (context_len=%s)", len(context))
        response = await self.llm.ainvoke(messages)
        logger.info("A4 LLM 请求完成 (response_len=%s)", len(response.content or ""))
        return self._parse_response(response.content)

    async def stream_generate(
        self,
        user_input: str,
        user_outline: str = "",
        world_setting: dict = {},
        style_profile: dict = {},
        characters: list = [],
        target_chapters: int = 100,
        decision_answer: str | None = None,
    ) -> AsyncIterator[dict]:
        messages = [SystemMessage(content=self.SYSTEM_PROMPT)]
        context = f"""用户总体构想：{user_input}"""
        if user_outline:
            context += f"\n\n用户对大纲的构想（请在此基础上完善和扩展）：\n{user_outline}"
        context += f"""
目标章节数：{target_chapters}

世界观设定：
{json.dumps(world_setting, ensure_ascii=False, indent=2)}

角色体系：
{json.dumps(characters, ensure_ascii=False, indent=2)}

风格画像：
{json.dumps(style_profile, ensure_ascii=False, indent=2)}"""
        if decision_answer:
            context += f"\n\n用户对上一步决策的回答：{decision_answer}\n请继续，输出完整的章节大纲 JSON。"
        messages.append(HumanMessage(content=context))
        async for chunk in self.llm.astream(messages):
            if chunk.content:
                yield {"type": "stream", "content": chunk.content}

    def _parse_response(self, content: str) -> dict:
        return _parse_llm_response(content, "novel_outline")
