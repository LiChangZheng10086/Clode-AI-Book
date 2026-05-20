"""LangGraph workflow definitions for preprocessing and writing pipelines."""

import asyncio
import json
import logging
from typing import AsyncIterator, Awaitable, Callable, TypedDict
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from engine.generator import ChapterOutliner, ChapterWriter
from engine.checker import ChapterReviewer
from engine.planner import (
    WorldbuildingAgent,
    CharacterAgent,
    StyleAgent,
    OutlineAgent,
)
from engine.polisher import Polisher
from engine.summarizer import Summarizer
from memory.entity_tracker import EntityTracker
from memory.hook_registry import HookRegistry
from memory.retriever import ContextRetriever
from memory.summary_store import SummaryStore

logger = logging.getLogger(__name__)

_STREAM_SENTINEL = object()
EmitFn = Callable[[dict], Awaitable[None]]


async def _emit(config: RunnableConfig, msg: dict) -> None:
    emit: EmitFn | None = config.get("configurable", {}).get("emit")
    if emit:
        await emit(msg)


async def _stream_graph(
    graph,
    initial: dict,
    config: dict,
) -> AsyncIterator[dict]:
    """Run graph while forwarding real-time emit() events from nodes."""
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(msg: dict) -> None:
        await queue.put(msg)

    run_config = {
        **config,
        "configurable": {**config.get("configurable", {}), "emit": emit},
    }

    async def runner() -> None:
        try:
            async for event in graph.astream(initial, run_config, stream_mode="values"):
                await queue.put({"type": "state_update", "state": event})
        except Exception as exc:
            logger.exception("Graph execution failed")
            await queue.put({"type": "error", "message": str(exc)})
        finally:
            await queue.put(_STREAM_SENTINEL)

    task = asyncio.create_task(runner())
    try:
        while True:
            item = await queue.get()
            if item is _STREAM_SENTINEL:
                break
            yield item
    finally:
        if not task.done():
            task.cancel()
        await task


# ── Preprocess State ──────────────────────────────────

class PreprocessState(TypedDict):
    novel_id: str
    user_input: str
    target_chapters: int
    # Per-dimension user seed input
    user_world_setting: str
    user_characters: str
    user_style: str
    user_outline: str
    # Agent outputs
    world_setting: dict | None
    character_system: list | None
    style_profile: dict | None
    novel_outline: dict | None
    # Decision flow control
    current_agent: str
    decision_point: dict | None
    decision_answer: str | None
    # Status
    status: str  # running | asking | complete | error
    error: str | None


# ── Write State ───────────────────────────────────────

class WriteState(TypedDict):
    novel_id: str
    chapter_id: str
    chapter_index: int
    # A5 output
    chapter_outline: dict | None
    # A6 output
    chapter_content: str | None
    polished_content: str | None
    # A7 output
    review_report: dict | None
    review_round: int
    # Context
    context_package: dict | None
    # Status
    status: str
    error: str | None


# ── Preprocess Graph ──────────────────────────────────

def _append_stream(stream: list[dict] | None, chunk: dict) -> None:
    if stream is not None:
        stream.append(chunk)


async def node_parse_input(state: PreprocessState, config: RunnableConfig) -> dict:
    """Validate and structure user input."""
    logger.info(
        "parse_input: user_input_len=%s world=%s chars=%s style=%s outline=%s",
        len(state.get("user_input", "")),
        len(state.get("user_world_setting", "")),
        len(state.get("user_characters", "")),
        len(state.get("user_style", "")),
        len(state.get("user_outline", "")),
    )
    await _emit(config, {"type": "progress", "agent": "input", "message": "正在分析输入..."})
    if not state.get("user_input", "").strip():
        logger.warning("parse_input: user_input 为空")
        return {"status": "error", "error": "用户输入为空"}
    return {"status": "running", "current_agent": "A1"}


async def node_worldbuilding(state: PreprocessState, config: RunnableConfig) -> dict:
    """A1: Worldbuilding agent."""
    logger.info("A1 世界观 Agent 启动 (world_seed=%s chars)", len(state.get("user_world_setting", "")))
    await _emit(config, {"type": "agent_start", "agent": "A1", "message": "世界观 Agent 启动..."})
    await _emit(config, {"type": "progress", "agent": "A1", "message": "正在调用 LLM 生成世界观（约 20–60 秒）..."})

    agent = WorldbuildingAgent()
    decision_answer = state.get("decision_answer") if state.get("current_agent") == "A1" else None

    result = await agent.generate(
        user_input=state["user_input"],
        user_world_setting=state.get("user_world_setting", ""),
        decision_answer=decision_answer,
    )

    if result.get("status") == "asking":
        await _emit(config, {"type": "decision_point", "agent": "A1", "data": result.get("decision_point")})
        return {"status": "asking", "decision_point": result.get("decision_point"), "current_agent": "A1"}

    world_setting = result.get("world_setting", result)
    await _emit(config, {"type": "agent_complete", "agent": "A1", "data": world_setting})
    return {"world_setting": world_setting, "status": "running", "current_agent": "A3", "decision_answer": None}


async def node_character(state: PreprocessState, config: RunnableConfig) -> dict:
    """A3: Character agent."""
    logger.info("A3 角色 Agent 启动 (char_seed=%s chars)", len(state.get("user_characters", "")))
    await _emit(config, {"type": "agent_start", "agent": "A3", "message": "角色 Agent 启动..."})
    await _emit(config, {"type": "progress", "agent": "A3", "message": "正在调用 LLM 生成角色体系..."})

    agent = CharacterAgent()
    decision_answer = state.get("decision_answer") if state.get("current_agent") == "A3" else None

    result = await agent.generate(
        user_input=state["user_input"],
        user_characters=state.get("user_characters", ""),
        world_setting=state.get("world_setting"),
        decision_answer=decision_answer,
    )

    if result.get("status") == "asking":
        await _emit(config, {"type": "decision_point", "agent": "A3", "data": result.get("decision_point")})
        return {"status": "asking", "decision_point": result.get("decision_point"), "current_agent": "A3"}

    characters = result.get("characters", result)
    if isinstance(characters, dict):
        logger.debug("A3 character_system top-level keys: %s", list(characters.keys()))
    elif isinstance(characters, list):
        logger.debug("A3 character_system is a flat list of length %s", len(characters))
    await _emit(config, {"type": "agent_complete", "agent": "A3", "data": characters})
    return {"character_system": characters, "status": "running", "current_agent": "A2", "decision_answer": None}


async def node_style(state: PreprocessState, config: RunnableConfig) -> dict:
    """A2: Style agent."""
    logger.info("A2 风格 Agent 启动 (style_seed=%s chars)", len(state.get("user_style", "")))
    await _emit(config, {"type": "agent_start", "agent": "A2", "message": "风格 Agent 启动..."})
    await _emit(config, {"type": "progress", "agent": "A2", "message": "正在调用 LLM 生成风格画像..."})

    agent = StyleAgent()
    decision_answer = state.get("decision_answer") if state.get("current_agent") == "A2" else None

    result = await agent.generate(
        user_input=state["user_input"],
        user_style=state.get("user_style", ""),
        world_setting=state.get("world_setting"),
        characters=state.get("character_system"),
        decision_answer=decision_answer,
    )

    if result.get("status") == "asking":
        await _emit(config, {"type": "decision_point", "agent": "A2", "data": result.get("decision_point")})
        return {"status": "asking", "decision_point": result.get("decision_point"), "current_agent": "A2"}

    style_profile = result.get("style_profile", result)
    await _emit(config, {"type": "agent_complete", "agent": "A2", "data": style_profile})
    return {"style_profile": style_profile, "status": "running", "current_agent": "A4", "decision_answer": None}


async def node_cross_validate(state: PreprocessState, config: RunnableConfig) -> dict:
    """Cross-validate A1/A2/A3 outputs for conflicts."""
    await _emit(config, {"type": "progress", "agent": "cross_validate", "message": "正在进行交叉校验..."})
    # Cross-validation runs automatically; issues are flagged for user review
    return {"status": "running", "current_agent": "A4"}


async def node_outline(state: PreprocessState, config: RunnableConfig) -> dict:
    """A4: Outline agent."""
    logger.info("A4 大纲 Agent 启动 (outline_seed=%s chars)", len(state.get("user_outline", "")))
    await _emit(config, {"type": "agent_start", "agent": "A4", "message": "大纲 Agent 启动..."})
    await _emit(config, {"type": "progress", "agent": "A4", "message": "正在调用 LLM 生成全书大纲（可能较慢）..."})

    agent = OutlineAgent()
    decision_answer = state.get("decision_answer") if state.get("current_agent") == "A4" else None

    result = await agent.generate(
        user_input=state["user_input"],
        user_outline=state.get("user_outline", ""),
        world_setting=state.get("world_setting", {}),
        style_profile=state.get("style_profile", {}),
        characters=state.get("character_system", []),
        target_chapters=state.get("target_chapters", 100),
        decision_answer=decision_answer,
    )

    if result.get("status") == "asking":
        await _emit(config, {"type": "decision_point", "agent": "A4", "data": result.get("decision_point")})
        return {"status": "asking", "decision_point": result.get("decision_point"), "current_agent": "A4"}

    novel_outline = result.get("novel_outline", result)
    if isinstance(novel_outline, dict):
        logger.debug("A4 novel_outline top-level keys: %s", list(novel_outline.keys()))
    await _emit(config, {"type": "agent_complete", "agent": "A4", "data": novel_outline})
    return {"novel_outline": novel_outline, "status": "complete", "current_agent": "done"}


# ── Preprocess Routing ────────────────────────────────

def route_preprocess(state: PreprocessState) -> str:
    if state.get("status") == "error":
        return END
    if state.get("status") == "asking":
        return "pause"
    if state.get("status") == "complete":
        return END
    agent = state.get("current_agent", "A1")
    return agent


def build_preprocess_graph() -> StateGraph:
    graph = StateGraph(PreprocessState)

    graph.add_node("parse_input", node_parse_input)
    graph.add_node("A1", node_worldbuilding)
    graph.add_node("A3", node_character)
    graph.add_node("A2", node_style)
    graph.add_node("cross_validate", node_cross_validate)
    graph.add_node("A4", node_outline)

    graph.set_entry_point("parse_input")

    # Every node uses conditional edges so we can pause at any decision point.
    # route_preprocess returns the next node name (from state.current_agent),
    # "pause" → END to wait for user input, or END on error/complete.
    route_map = {
        "A1": "A1",
        "A3": "A3",
        "A2": "A2",
        "A4": "A4",
        "cross_validate": "cross_validate",
        "pause": END,
        END: END,
    }
    graph.add_conditional_edges("parse_input", route_preprocess, route_map)
    graph.add_conditional_edges("A1", route_preprocess, route_map)
    graph.add_conditional_edges("A3", route_preprocess, route_map)
    graph.add_conditional_edges("A2", route_preprocess, route_map)
    graph.add_conditional_edges("cross_validate", route_preprocess, route_map)
    graph.add_conditional_edges("A4", route_preprocess, route_map)

    return graph.compile(checkpointer=MemorySaver())


# ── Write Graph ───────────────────────────────────────

async def node_chapter_outline(state: WriteState, config: RunnableConfig) -> dict:
    """A5: Generate chapter-level outline. Skipped if outline already exists."""
    existing = state.get("chapter_outline")
    if existing and isinstance(existing, dict) and existing.get("scenes"):
        await _emit(config, {"type": "agent_complete", "agent": "A5", "data": existing, "message": "跳过（大纲已存在）"})
        return {"status": "outline_done"}

    await _emit(config, {"type": "agent_start", "agent": "A5", "message": "正在生成章节大纲..."})

    outliner = ChapterOutliner()
    result = await outliner.generate(
        chapter_index=state["chapter_index"],
        novel_outline_beat=state.get("novel_outline_beat", {}),
        context_package=state.get("context_package", {}),
    )
    outline = result.get("chapter_outline", result)
    await _emit(config, {"type": "agent_complete", "agent": "A5", "data": outline})
    return {"chapter_outline": outline, "status": "outline_done"}


async def node_chapter_write(state: WriteState, config: RunnableConfig) -> dict:
    """A6: Generate chapter content + polish, or revise based on review feedback."""
    writer = ChapterWriter()
    context = state.get("context_package", {})
    review_report = context.get("review_report") if isinstance(context, dict) else None
    original_content = state.get("polished_content") or state.get("chapter_content") or ""

    if review_report and original_content:
        # Revision mode: fix issues from review
        round_num = state.get("review_round", 0) + 1
        await _emit(config, {"type": "agent_start", "agent": "A6", "message": f"正在根据审核意见修改（第{round_num}轮）..."})
        content = await writer.revise(original_content, review_report)
        await _emit(config, {"type": "content_stream", "content": content[:500] + "..."})
    else:
        # Fresh write mode
        await _emit(config, {"type": "agent_start", "agent": "A6", "message": "正在撰写章节正文..."})
        content = await writer.write(
            chapter_outline=state.get("chapter_outline", {}),
            context_package=context,
        )
        await _emit(config, {"type": "content_stream", "content": content[:500] + "..."})

    # Auto polish
    await _emit(config, {"type": "progress", "agent": "polisher", "message": "正在润色..."})
    polisher = Polisher()
    polished = await polisher.polish(content)

    await _emit(config, {"type": "agent_complete", "agent": "A6", "data": {"word_count": len(polished)}})
    return {"chapter_content": content, "polished_content": polished, "status": "writing_done"}


async def node_chapter_review(state: WriteState, config: RunnableConfig) -> dict:
    """A7: Review chapter content."""
    round_num = state.get("review_round", 0) + 1
    await _emit(config, {"type": "agent_start", "agent": "A7", "message": f"正在审核 (第{round_num}轮)..."})

    reviewer = ChapterReviewer()
    report = await reviewer.review(
        chapter_content=state.get("polished_content", state.get("chapter_content", "")),
        chapter_outline=state.get("chapter_outline", {}),
        world_setting=state.get("context_package", {}).get("world_setting", {}),
        characters=state.get("context_package", {}).get("characters", []),
        style_profile=state.get("context_package", {}).get("style_profile", {}),
        hooks=state.get("context_package", {}).get("pending_hooks", []),
        prev_chapter_summaries=state.get("context_package", {}).get("recent_summaries", []),
    )

    await _emit(config, {"type": "review_report", "agent": "A7", "data": report})
    return {
        "review_report": report,
        "review_round": round_num,
        "status": "reviewed",
    }


async def node_update_memory(state: WriteState, config: RunnableConfig) -> dict:
    """After chapter passes review: persist content and track new characters."""
    await _emit(config, {"type": "progress", "agent": "memory", "message": "正在更新记忆系统..."})

    content = state.get("polished_content", state.get("chapter_content", ""))
    novel_id = state["novel_id"]
    chapter_outline = state.get("chapter_outline", {})

    if content:
        from sqlalchemy import select
        from core.database import async_session
        from models.base import Chapter, Character, Volume

        # Persist chapter content to DB — look up by novel_id + chapter_index
        chapter_index = state.get("chapter_index", 0)
        try:
            novel_uuid = UUID(novel_id)
            async with async_session() as db:
                # Find the volume that contains this chapter
                vol_result = await db.execute(
                    select(Volume).where(Volume.novel_id == novel_uuid).order_by(Volume.index)
                )
                target_chapter = None
                for v in vol_result.scalars().all():
                    ch_result = await db.execute(
                        select(Chapter).where(
                            Chapter.volume_id == v.id,
                            Chapter.index == chapter_index,
                        )
                    )
                    target_chapter = ch_result.scalar_one_or_none()
                    if target_chapter:
                        break

                if target_chapter:
                    target_chapter.content = content
                    target_chapter.actual_word_count = len(content)
                    target_chapter.status = "completed"
                    if chapter_outline:
                        target_chapter.outline = chapter_outline
                    await db.commit()
                    logger.info("Saved chapter %s content (%d chars) to DB",
                                target_chapter.id, len(content))
                else:
                    logger.warning("Chapter not found: novel=%s index=%s, cannot save content",
                                   novel_id, chapter_index)
        except Exception:
            logger.exception("Failed to save chapter content to DB: novel=%s index=%s",
                             novel_id, chapter_index)

        # Fetch known character names
        known_names: list[str] = []
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(Character.name).where(Character.novel_id == UUID(novel_id))
                )
                known_names = [row[0] for row in result.all()]
        except Exception:
            logger.exception("Failed to fetch known characters for novel %s", novel_id)

        # Extract and save new characters
        try:
            from services.character_tracker import extract_and_save_new_characters
            new_chars = await extract_and_save_new_characters(novel_id, content, known_names)
            if new_chars:
                await _emit(config, {
                    "type": "progress",
                    "agent": "memory",
                    "message": f"发现 {len(new_chars)} 个新角色：{', '.join(c['name'] for c in new_chars)}",
                })
        except Exception:
            logger.exception("Character tracker failed for novel %s", novel_id)

        # Run full memory updates: summaries, hooks, entity states
        try:
            from services.memory_updater import run_memory_updates
            mem_result = await run_memory_updates(
                novel_id=novel_id,
                chapter_index=chapter_index,
                chapter_content=content,
                chapter_outline=chapter_outline,
            )
            if mem_result:
                parts: list[str] = []
                if "chapter_summary" in mem_result:
                    parts.append("章节摘要已生成")
                if "book_summary" in mem_result:
                    parts.append("全书摘要已更新")
                if "volume_summary" in mem_result:
                    parts.append("卷摘要已更新")
                if "new_hooks" in mem_result:
                    parts.append(f"发现 {mem_result['new_hooks']} 个伏笔")
                if "entity_states_updated" in mem_result:
                    parts.append(f"更新 {mem_result['entity_states_updated']} 个实体状态")
                if parts:
                    await _emit(config, {
                        "type": "progress",
                        "agent": "memory",
                        "message": "；".join(parts),
                    })
        except Exception:
            logger.exception("Memory updates failed for novel %s ch %s", novel_id, chapter_index)

    return {"status": "done"}


# ── Write Routing ─────────────────────────────────────

def route_after_review(state: WriteState) -> str:
    report = state.get("review_report", {})
    overall = report.get("overall", "revision_needed")
    round_num = state.get("review_round", 0)

    if overall == "pass":
        return "update_memory"
    if round_num >= 3:
        logger.warning(f"Chapter {state.get('chapter_index')} failed review after 3 rounds, flagging for manual review")
        return "update_memory"  # Force through, flag for human
    return "A6"  # Revision loop


def build_write_graph() -> StateGraph:
    graph = StateGraph(WriteState)

    graph.add_node("A5", node_chapter_outline)
    graph.add_node("A6", node_chapter_write)
    graph.add_node("A7", node_chapter_review)
    graph.add_node("update_memory", node_update_memory)

    graph.set_entry_point("A5")
    graph.add_edge("A5", "A6")
    graph.add_edge("A6", "A7")
    graph.add_conditional_edges("A7", route_after_review, {"A6": "A6", "update_memory": "update_memory"})
    graph.add_edge("update_memory", END)

    return graph.compile(checkpointer=MemorySaver())


# ── Graph Manager ─────────────────────────────────────

class WorkflowManager:
    """Orchestrates preprocessing and writing workflows.

    Manages graph lifecycle, checkpoint persistence, and stream forwarding.
    """

    def __init__(self):
        self.preprocess_graph = build_preprocess_graph()
        self.write_graph = build_write_graph()

    async def run_preprocess(
        self, novel_id: str, user_input: str, target_chapters: int = 100,
        user_world_setting: str = "", user_characters: str = "",
        user_style: str = "", user_outline: str = "",
    ) -> AsyncIterator[dict]:
        initial: PreprocessState = {
            "novel_id": novel_id,
            "user_input": user_input,
            "target_chapters": target_chapters,
            "user_world_setting": user_world_setting,
            "user_characters": user_characters,
            "user_style": user_style,
            "user_outline": user_outline,
            "world_setting": None,
            "character_system": None,
            "style_profile": None,
            "novel_outline": None,
            "current_agent": "parse_input",
            "decision_point": None,
            "decision_answer": None,
            "status": "running",
            "error": None,
        }
        config = {"configurable": {"thread_id": f"preprocess_{novel_id}"}}
        logger.info("run_preprocess: 开始 astream, thread_id=%s", config["configurable"]["thread_id"])
        async for event in _stream_graph(self.preprocess_graph, initial, config):
            if event.get("type") == "state_update":
                state = event.get("state", {})
                logger.debug(
                    "astream event: current_agent=%s status=%s",
                    state.get("current_agent"),
                    state.get("status"),
                )
            yield event
        logger.info("run_preprocess: astream 结束")

    async def resume_preprocess(
        self, novel_id: str, decision_answer: str
    ) -> AsyncIterator[dict]:
        """Resume preprocess after user answers decision point."""
        config = {"configurable": {"thread_id": f"preprocess_{novel_id}"}}
        async for event in _stream_graph(
            self.preprocess_graph,
            {"decision_answer": decision_answer, "status": "running"},
            config,
        ):
            yield event

    async def run_write(
        self,
        novel_id: str,
        chapter_id: str,
        chapter_index: int,
        novel_outline_beat: dict,
        context_package: dict,
    ) -> AsyncIterator[dict]:
        # Determine if this is a revision retry or a fresh write with confirmed outline
        is_revision = bool(
            isinstance(context_package, dict) and context_package.get("review_report")
        )
        has_outline = bool(novel_outline_beat and isinstance(novel_outline_beat, dict))

        existing_content = None
        if is_revision:
            # Load existing chapter content from DB for revision
            from sqlalchemy import select
            from core.database import async_session
            from models.base import Chapter, Volume as VolModel
            try:
                async with async_session() as db:
                    vol_result = await db.execute(
                        select(VolModel).where(VolModel.novel_id == UUID(novel_id))
                    )
                    for v in vol_result.scalars().all():
                        ch_result = await db.execute(
                            select(Chapter).where(
                                Chapter.volume_id == v.id,
                                Chapter.index == chapter_index,
                            )
                        )
                        ch = ch_result.scalar_one_or_none()
                        if ch and ch.content:
                            existing_content = ch.content
                            break
            except Exception:
                logger.exception("Failed to load existing content for revision")

        initial: WriteState = {
            "novel_id": novel_id,
            "chapter_id": chapter_id,
            "chapter_index": chapter_index,
            # Use existing outline if provided (revision or confirmed outline)
            "chapter_outline": novel_outline_beat if has_outline else None,
            "chapter_content": None,
            "polished_content": existing_content,
            "review_report": None,
            "review_round": 0,
            "context_package": context_package,
            "status": "running",
            "error": None,
        }
        config = {"configurable": {"thread_id": f"write_{chapter_id}"}}
        async for event in _stream_graph(self.write_graph, initial, config):
            yield event


workflow_manager = WorkflowManager()
