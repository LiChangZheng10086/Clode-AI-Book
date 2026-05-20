"""De-AI polishing pass: runs automatically after content generation."""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from core.llm import get_polishing_llm


class Polisher:
    """Runs auto de-AI polishing after content generation.

    Changes expression style, not content. Uses higher temperature
    for sentence variety, rhythm, and word choice diversity.
    """

    SYSTEM_PROMPT = """你是一位资深文学编辑。你的任务是润色以下小说段落，
使其读起来更像人类作家的手笔，而非 AI 生成。

润色规则：
1. 打破重复句式：如果连续句子结构相似，改写其中一部分
2. 替换 AI 高频词：然而/因此/此外/总而言之/值得注意的是/突然/就在这时 → 换成更自然的表达
3. 增加句长变化：混合使用短句(3-8字)、中句、长句(30+字)
4. 增强五感描写：加入视觉/听觉/触觉/气味/温度细节
5. 角色对白差异化：确保不同角色说话方式不同
6. 删掉多余的"说理"段落：角色已经在行动中就不要再解释
7. 增加留白：删掉不必要的过渡句和心理直述，让读者自己脑补

格式要求：
- 必须保留原文的段落结构，用空行（两个换行）分隔段落
- 对话独立成段，每个角色的对白单独一段
- 场景转换时用空行分隔

严禁修改的内容：
- 不要改变情节走向
- 不要改变角色行为和对话语义
- 不要改变关键信息（设定、关系、伏笔）
- 不要增删角色
- 不要改变章节结构

只改变表达方式，不改变信息本身。

输出润色后的完整正文，不要任何解释或标记。"""

    def __init__(self, llm: BaseChatModel | None = None):
        self.llm = llm or get_polishing_llm()

    async def polish(self, content: str) -> str:
        system = SystemMessage(content=self.SYSTEM_PROMPT)
        human = HumanMessage(content=f"请润色以下章节正文：\n\n{content}")
        response = await self.llm.ainvoke([system, human])
        return response.content

    async def stream_polish(self, content: str):
        system = SystemMessage(content=self.SYSTEM_PROMPT)
        human = HumanMessage(content=f"请润色以下章节正文：\n\n{content}")
        async for chunk in self.llm.astream([system, human]):
            if chunk.content:
                yield chunk.content
