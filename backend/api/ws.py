"""WebSocket endpoints for real-time Agent streaming."""

import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from workflow.graph import workflow_manager
from services.preprocess_db import save_preprocess_results

logger = logging.getLogger(__name__)
router = APIRouter()


async def _load_write_context(novel_id: str, chapter_index: int) -> dict:
    """Load context package from DB for chapter writing.

    This is the critical function for chapter coherence — it must load:
    1. The chapter's own outline (novel_outline_beat)
    2. Volume summary
    3. Previous chapter summaries (from ChapterSummary table + chapter.summary)
    4. Previous chapter FULL CONTENT (essential for continuity)
    5. Pending hooks from Hook table
    6. Entity states from EntityState table
    7. World setting, style profile, character voices
    """
    from uuid import UUID
    from sqlalchemy import select
    from core.database import async_session
    from models.base import (
        Novel, Volume, Chapter, Character, WorldSetting, StyleProfile,
        ChapterSummary, EntityState, Hook,
    )

    novel_uuid = UUID(novel_id)
    ctx: dict = {
        "volume_summary": "无",
        "recent_summaries": [],
        "prev_chapter_content": "",
        "pending_hooks": [],
        "entity_states": {},
        "style_profile": {},
        "world_setting_chunks": [],
        "character_voices": [],
        "novel_outline_beat": {},
    }

    async with async_session() as db:
        # Novel
        result = await db.execute(select(Novel).where(Novel.id == novel_uuid))
        novel = result.scalar_one_or_none()
        if not novel:
            return ctx

        # Load all volumes and chapters, build ordered chapter list
        vol_result = await db.execute(
            select(Volume).where(Volume.novel_id == novel_uuid).order_by(Volume.index)
        )
        volumes = vol_result.scalars().all()

        current_volume = None
        current_volume_index = None
        current_chapter_id = None
        all_chapters = []  # (volume_index, chapter_index, chapter_row_object)
        prev_chapter = None  # immediately preceding chapter tuple

        for v in volumes:
            ch_result = await db.execute(
                select(Chapter).where(Chapter.volume_id == v.id).order_by(Chapter.index)
            )
            for ch in ch_result.scalars().all():
                all_chapters.append((v.index, ch.index, ch))
                if ch.index == chapter_index and v.id == ch.volume_id:
                    current_volume = v
                    current_volume_index = v.index
                    current_chapter_id = ch.id
                    if ch.outline:
                        ctx["novel_outline_beat"] = ch.outline

        # Sort by (volume_index, chapter_index) for correct global ordering
        all_chapters.sort(key=lambda x: (x[0], x[1]))

        if current_volume:
            ctx["volume_summary"] = current_volume.summary or f"第{current_volume.index}卷"

        # Find the immediately preceding chapter (global order)
        for i, (v_idx, ch_idx, ch) in enumerate(all_chapters):
            if v_idx == current_volume_index and ch_idx == chapter_index:
                if i > 0:
                    prev_chapter = all_chapters[i - 1]
                break

        # Load previous chapter FULL CONTENT — essential for continuity
        if prev_chapter:
            _vi, _ci, prev_ch = prev_chapter
            if prev_ch.content:
                ctx["prev_chapter_content"] = prev_ch.content[-500:]

        # Build a chapter_id → summary map from ChapterSummary table
        chapter_ids = [ch.id for (_v, _c, ch) in all_chapters]
        summary_map: dict = {}
        if chapter_ids:
            from models.base import ChapterSummary as CSModel
            cs_result = await db.execute(
                select(CSModel).where(
                    CSModel.chapter_id.in_(chapter_ids),
                    CSModel.summary_type == "chapter",
                )
            )
            for cs in cs_result.scalars().all():
                if cs.content:
                    summary_map[str(cs.chapter_id)] = cs.content

        # Build recent summaries (up to 3 previous chapters in global order)
        prev_summaries = []
        found_current = False
        for v_idx, ch_idx, ch in reversed(all_chapters):
            if ch.id == current_chapter_id:
                found_current = True
                continue
            if not found_current:
                continue
            summary_text = (
                summary_map.get(str(ch.id), "")
                or (ch.summary or "")
                or (_extract_outline_summary(ch.outline) if ch.outline else "")
            )
            prev_summaries.insert(0, {
                "volume": v_idx,
                "chapter": ch_idx,
                "title": ch.title,
                "summary": summary_text,
            })
            if len(prev_summaries) >= 3:
                break
        ctx["recent_summaries"] = prev_summaries

        # Pending hooks
        hook_result = await db.execute(
            select(Hook).where(
                Hook.novel_id == novel_uuid,
                Hook.status.in_(["unresolved", "in_progress"]),
            ).order_by(Hook.priority.desc(), Hook.planted_chapter_index)
        )
        ctx["pending_hooks"] = [
            {
                "id": str(h.id),
                "hook_type": h.hook_type,
                "description": h.description,
                "priority": h.priority,
                "planted_chapter_index": h.planted_chapter_index,
                "status": h.status,
            }
            for h in hook_result.scalars().all()
        ]

        # Entity states
        entity_result = await db.execute(
            select(EntityState).where(EntityState.novel_id == novel_uuid)
        )
        for e in entity_result.scalars().all():
            latest = e.state_snapshots[-1] if e.state_snapshots else None
            ctx["entity_states"][e.entity_name] = {
                "type": e.entity_type,
                "latest_state": latest.get("state", "") if latest else "",
            }

        # World setting
        ws_result = await db.execute(
            select(WorldSetting).where(WorldSetting.novel_id == novel_uuid)
        )
        world = ws_result.scalar_one_or_none()
        if world and world.settings:
            ctx["world_setting_chunks"] = [world.settings]

        # Style profile
        sp_result = await db.execute(
            select(StyleProfile).where(StyleProfile.novel_id == novel_uuid)
        )
        style = sp_result.scalar_one_or_none()
        if style and style.extracted_params:
            ctx["style_profile"] = style.extracted_params

        # Characters — build voice cards
        char_result = await db.execute(
            select(Character).where(Character.novel_id == novel_uuid)
        )
        for c in char_result.scalars().all():
            voice_card = {
                "name": c.name,
                "role": c.role,
                "profile": c.profile or {},
            }
            if c.voice_config:
                voice_card["voice"] = c.voice_config
            ctx["character_voices"].append(voice_card)

    return ctx


def _extract_outline_summary(outline: dict | None) -> str:
    """Extract summary text from an outline dict, for use as fallback."""
    if not isinstance(outline, dict):
        return ""
    if outline.get("summary"):
        return outline["summary"]
    scenes = outline.get("scenes", [])
    if isinstance(scenes, list) and scenes:
        first = scenes[0]
        if isinstance(first, dict) and first.get("description"):
            return first["description"]
    return ""


async def _save_chapter_outline(novel_id: str, chapter_index: int, outline: dict) -> None:
    """Persist a generated chapter outline to the database."""
    from uuid import UUID
    from sqlalchemy import select
    from core.database import async_session
    from models.base import Chapter, Volume

    try:
        novel_uuid = UUID(novel_id)
        async with async_session() as db:
            # Find the volume that contains this chapter
            vol_result = await db.execute(
                select(Volume).where(Volume.novel_id == novel_uuid).order_by(Volume.index)
            )
            volumes = vol_result.scalars().all()

            target_chapter = None
            for v in volumes:
                ch_result = await db.execute(
                    select(Chapter).where(Chapter.volume_id == v.id, Chapter.index == chapter_index)
                )
                target_chapter = ch_result.scalar_one_or_none()
                if target_chapter:
                    break

            if target_chapter:
                target_chapter.outline = outline
                target_chapter.status = "outlined"
                await db.commit()
                logger.info("Saved outline for chapter %s (novel=%s, index=%s)",
                            target_chapter.id, novel_id, chapter_index)
            else:
                logger.warning("Chapter not found: novel=%s index=%s, outline not saved to DB",
                               novel_id, chapter_index)
    except Exception:
        logger.exception("Failed to save chapter outline for novel=%s index=%s", novel_id, chapter_index)


@router.websocket("/preprocess/{novel_id}")
async def preprocess_ws(websocket: WebSocket, novel_id: str):
    await websocket.accept()
    logger.info(f"Preprocess WS connected for novel {novel_id}")

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            action = msg.get("action")

            if action == "start":
                user_input = msg.get("user_input", "")
                target_chapters = msg.get("target_chapters", 100)
                user_world_setting = msg.get("user_world_setting", "")
                user_characters = msg.get("user_characters", "")
                user_style = msg.get("user_style", "")
                user_outline = msg.get("user_outline", "")

                logger.info(
                    "Preprocess START novel=%s target_chapters=%s input_len=%s "
                    "world=%s chars=%s style=%s outline=%s",
                    novel_id, target_chapters, len(user_input),
                    len(user_world_setting), len(user_characters),
                    len(user_style), len(user_outline),
                )

                await websocket.send_json({
                    "type": "pipeline_start",
                    "message": "预处理流水线启动...",
                })

                try:
                    last_state: dict = {}
                    async for event in workflow_manager.run_preprocess(
                        novel_id, user_input, target_chapters,
                        user_world_setting, user_characters,
                        user_style, user_outline,
                    ):
                        await websocket.send_json(event)

                        if event.get("type") == "state_update":
                            last_state = event.get("state", {})

                        # decision_point may also be emitted directly from graph nodes
                        if event.get("type") == "decision_point":
                            await websocket.send_json({
                                "type": "decision_point",
                                "agent": event.get("agent"),
                                "data": event.get("data"),
                            })

                        state = event.get("state", last_state)
                        if event.get("type") == "state_update" and state.get("status") == "asking":
                            dp = state.get("decision_point")
                            await websocket.send_json({
                                "type": "decision_point",
                                "agent": state.get("current_agent"),
                                "data": dp,
                            })

                    if last_state.get("status") == "complete":
                        # Persist to database so other pages can read the results
                        await save_preprocess_results(
                            novel_id=novel_id,
                            world_setting=last_state.get("world_setting"),
                            style_profile=last_state.get("style_profile"),
                            character_system=last_state.get("character_system"),
                            novel_outline=last_state.get("novel_outline"),
                        )
                        await websocket.send_json({
                            "type": "pipeline_complete",
                            "message": "预处理流水线完成",
                            "data": {
                                "world_setting": last_state.get("world_setting"),
                                "character_system": last_state.get("character_system"),
                                "style_profile": last_state.get("style_profile"),
                                "novel_outline": last_state.get("novel_outline"),
                            },
                        })
                    elif last_state.get("status") == "asking":
                        logger.info("Preprocess paused at decision point, agent=%s", last_state.get("current_agent"))
                    elif last_state.get("status") == "error":
                        await websocket.send_json({
                            "type": "error",
                            "message": last_state.get("error") or "预处理失败",
                        })

                except Exception as e:
                    logger.exception("Preprocess pipeline error")
                    await websocket.send_json({"type": "error", "message": str(e)})

            elif action == "decide":
                answer = msg.get("answer", "")
                try:
                    last_state: dict = {}
                    async for event in workflow_manager.resume_preprocess(novel_id, answer):
                        await websocket.send_json(event)

                        if event.get("type") == "state_update":
                            last_state = event.get("state", {})

                        if event.get("type") == "decision_point":
                            await websocket.send_json({
                                "type": "decision_point",
                                "agent": event.get("agent"),
                                "data": event.get("data"),
                            })

                        state = event.get("state", last_state)
                        if event.get("type") == "state_update" and state.get("status") == "asking":
                            await websocket.send_json({
                                "type": "decision_point",
                                "agent": state.get("current_agent"),
                                "data": state.get("decision_point"),
                            })

                    if last_state.get("status") == "complete":
                        await save_preprocess_results(
                            novel_id=novel_id,
                            world_setting=last_state.get("world_setting"),
                            style_profile=last_state.get("style_profile"),
                            character_system=last_state.get("character_system"),
                            novel_outline=last_state.get("novel_outline"),
                        )
                        await websocket.send_json({
                            "type": "pipeline_complete",
                            "message": "预处理流水线完成",
                            "data": {
                                "world_setting": last_state.get("world_setting"),
                                "character_system": last_state.get("character_system"),
                                "style_profile": last_state.get("style_profile"),
                                "novel_outline": last_state.get("novel_outline"),
                            },
                        })
                    elif last_state.get("status") == "error":
                        await websocket.send_json({
                            "type": "error",
                            "message": last_state.get("error") or "预处理失败",
                        })

                except Exception as e:
                    logger.exception("Preprocess resume error")
                    await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        logger.info(f"Preprocess WS disconnected for novel {novel_id}")


@router.websocket("/write/{novel_id}")
async def write_ws(websocket: WebSocket, novel_id: str):
    await websocket.accept()
    logger.info(f"Write WS connected for novel {novel_id}")

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            action = msg.get("action")
            logger.info("Write WS received action: %s", action)

            if action == "start_outline":
                chapter_id = msg.get("chapter_id", "")
                chapter_index = msg.get("chapter_index", 1)
                context_package = msg.get("context_package", {})

                # If frontend sent empty context, load from DB
                if not context_package or not context_package.get("volume_summary"):
                    context_package = await _load_write_context(novel_id, chapter_index)

                await websocket.send_json({
                    "type": "agent_start",
                    "agent": "A5",
                    "message": f"正在生成第{chapter_index}章大纲...",
                })

                try:
                    from engine.generator import ChapterOutliner
                    outliner = ChapterOutliner()
                    result = await outliner.generate(
                        chapter_index=chapter_index,
                        novel_outline_beat=context_package.get("novel_outline_beat", {}),
                        context_package=context_package,
                    )
                    chapter_outline = result.get("chapter_outline", result)

                    # Persist outline to DB
                    await _save_chapter_outline(novel_id, chapter_index, chapter_outline)

                    await websocket.send_json({
                        "type": "agent_complete",
                        "agent": "A5",
                        "message": "章节大纲生成完成",
                        "data": chapter_outline,
                    })
                except Exception as e:
                    logger.exception("A5 chapter outline failed")
                    await websocket.send_json({"type": "error", "message": str(e)})

            elif action == "start_write":
                chapter_id = msg.get("chapter_id", "")
                chapter_index = msg.get("chapter_index", 1)
                novel_outline_beat = msg.get("novel_outline_beat", {})
                context_package = msg.get("context_package", {})

                # If frontend sent empty context, load from DB
                if not context_package or not context_package.get("volume_summary"):
                    context_package = await _load_write_context(novel_id, chapter_index)

                await websocket.send_json({
                    "type": "pipeline_start",
                    "message": f"写作流水线启动 — 第{chapter_index}章",
                })

                try:
                    async for event in workflow_manager.run_write(
                        novel_id, chapter_id, chapter_index,
                        novel_outline_beat, context_package,
                    ):
                        await websocket.send_json(event)

                        state = event.get("state", {}) or {}
                        if state.get("status") == "done":
                            report = state.get("review_report", {})
                            if report.get("overall") == "pass":
                                await websocket.send_json({
                                    "type": "pipeline_complete",
                                    "message": "本章通过审核",
                                    "data": {
                                        "polished_content": state.get("polished_content"),
                                        "review_report": report,
                                    },
                                })
                            else:
                                await websocket.send_json({
                                    "type": "pipeline_stuck",
                                    "message": "审核3轮仍未通过，已挂起等待人工处理",
                                    "data": {
                                        "polished_content": state.get("polished_content"),
                                        "review_report": report,
                                    },
                                })
                        elif state.get("status") == "reviewed":
                            report = state.get("review_report", {})
                            if report.get("overall") != "pass" and state.get("review_round", 0) < 3:
                                await websocket.send_json({
                                    "type": "review_retry",
                                    "message": f"审核未通过，第{state.get('review_round')}轮修改",
                                    "data": report,
                                })

                except Exception as e:
                    logger.exception("Write pipeline error")
                    await websocket.send_json({"type": "error", "message": str(e)})

            elif action == "confirm_manual":
                # User manually approved after 3 failed review rounds
                chapter_id = msg.get("chapter_id", "")
                await websocket.send_json({
                    "type": "manual_confirm_ack",
                    "chapter_id": chapter_id,
                    "message": "已标记为人工通过",
                })

            elif action == "retry_outline":
                chapter_id = msg.get("chapter_id", "")
                await websocket.send_json({
                    "type": "retry_ack",
                    "message": "重新生成大纲",
                })

    except WebSocketDisconnect:
        logger.info(f"Write WS disconnected for novel {novel_id}")
