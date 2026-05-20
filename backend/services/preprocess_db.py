"""Save preprocess pipeline outputs to database."""
import json
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import async_session
from core.json_utils import extract_json_block
from models.base import Character, Chapter, Novel, StyleProfile, Volume, WorldSetting

logger = logging.getLogger(__name__)


def _to_str(value: any, default: str = "") -> str:
    """Coerce a value to string — AI sometimes returns nested dicts for scalar fields."""
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _extract_world_type(data: dict) -> str:
    """Extract a short world_type label (max 200 chars) from the world_setting dict.

    AI may return world_type as a simple string ("修真") or a nested dict.
    """
    MAX_LEN = 200
    wt = data.get("world_type", "")
    if isinstance(wt, str) and wt.strip():
        return wt[:MAX_LEN]
    if isinstance(wt, dict):
        for key in ("name", "type", "label", "category"):
            v = wt.get(key)
            if isinstance(v, str) and v.strip():
                return v[:MAX_LEN]
        for v in wt.values():
            if isinstance(v, str) and len(v) <= MAX_LEN:
                return v
        return json.dumps(wt, ensure_ascii=False)[:MAX_LEN]
    if isinstance(wt, (list, dict)):
        return json.dumps(wt, ensure_ascii=False)[:MAX_LEN]
    return str(wt)[:MAX_LEN] if wt else ""


async def save_preprocess_results(
    novel_id: str,
    world_setting: dict | None,
    style_profile: dict | None,
    character_system: list | dict | None,
    novel_outline: dict | None,
) -> None:
    """Persist all four preprocess outputs to the database."""
    novel_uuid = UUID(novel_id)

    async with async_session() as db:
        # Verify novel exists (no autoflush needed)
        with db.no_autoflush:
            result = await db.execute(select(Novel).where(Novel.id == novel_uuid))
            if not result.scalar_one_or_none():
                logger.warning("Novel %s not found, skipping DB save", novel_id)
                return

        if world_setting:
            await _save_world_setting(db, novel_uuid, world_setting)

        if style_profile:
            await _save_style_profile(db, novel_uuid, style_profile)

        if character_system:
            await _save_characters(db, novel_uuid, character_system)

        await db.commit()

        # Outline needs a separate session to avoid FK conflicts
        if novel_outline:
            await _save_outline(novel_uuid, novel_outline)

    logger.info(
        "Preprocess results saved to DB: novel=%s world=%s style=%s chars=%s outline=%s",
        novel_id,
        bool(world_setting),
        bool(style_profile),
        bool(character_system),
        bool(novel_outline),
    )


async def _save_world_setting(db: AsyncSession, novel_id: UUID, data: dict) -> None:
    with db.no_autoflush:
        result = await db.execute(select(WorldSetting).where(WorldSetting.novel_id == novel_id))
        ws = result.scalar_one_or_none()
    if ws is None:
        ws = WorldSetting(novel_id=novel_id)
        db.add(ws)
    ws.world_type = _extract_world_type(data)
    ws.settings = data
    logger.info("Saved world_setting for novel %s", novel_id)


async def _save_style_profile(db: AsyncSession, novel_id: UUID, data: dict) -> None:
    with db.no_autoflush:
        result = await db.execute(select(StyleProfile).where(StyleProfile.novel_id == novel_id))
        sp = result.scalar_one_or_none()
    if sp is None:
        sp = StyleProfile(novel_id=novel_id)
        db.add(sp)
    sp.extracted_params = data
    logger.info("Saved style_profile for novel %s", novel_id)


async def _save_characters(db: AsyncSession, novel_id: UUID, data: list | dict) -> None:
    with db.no_autoflush:
        existing = await db.execute(select(Character).where(Character.novel_id == novel_id))
        for char in existing.scalars().all():
            await db.delete(char)

    chars = _extract_characters(data)
    for c in chars:
        char = Character(
            novel_id=novel_id,
            name=_to_str(c.get("name", "未命名")),
            role=_to_str(c.get("role", "supporting")),
            profile=c.get("profile", {}),
            voice_config=c.get("voice", c.get("voice_config")),
            relationships=c.get("relationships"),
            arc=c.get("arc"),
        )
        db.add(char)
    logger.info("Saved %s characters for novel %s", len(chars), novel_id)


def _extract_characters(data: list | dict) -> list[dict]:
    """Normalize character_system into a flat list of character dicts."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []

    logger.debug("_extract_characters input keys: %s", list(data.keys()))

    # If JSON parsing failed upstream, data may be {"raw": "<full LLM response>"}
    # Try to re-extract JSON from the raw text.
    if list(data.keys()) == ["raw"] and isinstance(data["raw"], str):
        logger.debug("_extract_characters: raw fallback, attempting re-extraction (%d chars)", len(data["raw"]))
        parsed = _try_parse_raw_json(data["raw"])
        if parsed:
            data = parsed
            logger.debug("_extract_characters: re-extracted from raw, new keys=%s", list(data.keys()))

    # AI may wrap characters inside common wrapper keys — unwrap them
    inner = data
    for wrapper in ("characters", "character_system", "character", "data", "result", "role_system"):
        if wrapper in inner and isinstance(inner[wrapper], dict):
            inner = inner[wrapper]
            logger.debug("_extract_characters unwrapped via key=%s, new keys=%s", wrapper, list(inner.keys()))
        elif wrapper in inner and isinstance(inner[wrapper], list):
            # Flat list of character dicts under a wrapper
            logger.debug("_extract_characters found flat list under key=%s (len=%s)", wrapper, len(inner[wrapper]))
            return inner[wrapper]

    # Handle top-level "relationships" — extract character references if present
    relationships = inner.pop("relationships", None)

    # If the unwrapped dict itself looks like a single character (has name/role), return it
    if _looks_like_character(inner):
        inner.setdefault("role", inner.get("role", "supporting"))
        return [inner]

    result: list[dict] = []

    # protagonist — may be a dict, a list, or missing
    for proto_key in ("protagonist", "protagonists", "main_character", "main_characters", "hero"):
        p = inner.get(proto_key)
        if isinstance(p, dict):
            p.setdefault("role", "protagonist")
            result.append(p)
        elif isinstance(p, list):
            for item in p:
                if isinstance(item, dict):
                    item.setdefault("role", "protagonist")
                    result.append(item)

    # supporting / antagonist / npcs
    _ROLE_ALIASES = {
        "supporting": ("supporting_cast", "supporting_characters", "supporting_roles", "side_characters"),
        "antagonist": ("antagonist", "antagonists", "villains", "villain"),
        "npc": ("npcs", "npc", "minor_characters", "background_characters"),
    }
    for role, keys in _ROLE_ALIASES.items():
        for key in keys:
            arr = inner.get(key)
            if isinstance(arr, list):
                for item in arr:
                    if isinstance(item, dict):
                        item.setdefault("role", role)
                        result.append(item)
            elif isinstance(arr, dict):
                arr.setdefault("role", role)
                result.append(arr)

    return result


def _looks_like_character(d: dict) -> bool:
    """Return True if dict has fields suggesting it represents a single character."""
    char_fields = ("name", "role", "profile", "voice", "personality", "background")
    return any(f in d for f in char_fields)


def _try_parse_raw_json(raw_text: str) -> dict | None:
    return extract_json_block(raw_text)


async def _save_outline(novel_id: UUID, data: dict) -> None:
    """Save novel outline: merge volumes and chapters, preserving existing content."""
    async with async_session() as db:
        with db.no_autoflush:
            novel_result = await db.execute(select(Novel).where(Novel.id == novel_id))
            novel = novel_result.scalar_one_or_none()
            if not novel:
                return

        # AI may wrap outline inside common wrapper keys — unwrap first
        inner = data
        for wrapper in ("novel_outline", "outline", "data", "result"):
            if wrapper in inner and isinstance(inner[wrapper], dict):
                inner = inner[wrapper]
                logger.debug("_save_outline unwrapped via key=%s, new keys=%s", wrapper, list(inner.keys()))

        # If JSON parsing failed upstream, the raw text is stored under "raw" — try to extract
        if list(inner.keys()) == ["raw"] and isinstance(inner["raw"], str):
            raw_text = inner["raw"]
            logger.debug("_save_outline attempting JSON extraction from raw text (len=%s)", len(raw_text))
            parsed = _try_parse_raw_json(raw_text)
            if parsed:
                inner = parsed
                logger.debug("_save_outline extracted JSON from raw, keys=%s", list(inner.keys()))

        logger.debug("_save_outline looking for volumes, available keys: %s", list(inner.keys()))

        volumes = inner.get("volumes", [])
        if not volumes:
            st = inner.get("structure")
            if isinstance(st, list):
                volumes = st
            elif isinstance(st, dict) and "volumes" in st:
                volumes = st["volumes"]
        if not volumes:
            volumes = inner.get("volume_plan", [])
        if not volumes and isinstance(inner.get("chapters"), list):
            volumes = [{"index": 1, "title": "正文", "chapters": inner["chapters"]}]
        if not volumes and "scenes" in inner:
            logger.debug("_save_outline wrapping single-chapter data (index=%s) into a volume", inner.get("index"))
            volumes = [{"index": 1, "title": "正文", "chapters": [inner]}]

        if not isinstance(volumes, list):
            logger.warning("Outline volumes not a list, skipping outline save")
            return

        # Load existing volumes for this novel (do NOT delete — merge)
        with db.no_autoflush:
            existing_vols_result = await db.execute(
                select(Volume).where(Volume.novel_id == novel_id).order_by(Volume.index)
            )
            existing_vols = existing_vols_result.scalars().all()

        # Build lookup: existing volumes by index
        existing_vol_by_index: dict[int, Volume] = {}
        for v in existing_vols:
            if v.index not in existing_vol_by_index:
                existing_vol_by_index[v.index] = v

        # Load all existing chapters for this novel
        existing_chapters_by_vol: dict[int, dict[int, Chapter]] = {}
        for v in existing_vols:
            ch_result = await db.execute(
                select(Chapter).where(Chapter.volume_id == v.id).order_by(Chapter.index)
            )
            existing_chapters_by_vol[v.index] = {}
            for ch in ch_result.scalars().all():
                existing_chapters_by_vol[v.index][ch.index] = ch

        seen_vol_indices: set[int] = set()
        created_count = 0
        updated_count = 0

        for vol_data in volumes:
            if not isinstance(vol_data, dict):
                continue
            vol_index = vol_data.get("index", 1)
            seen_vol_indices.add(vol_index)

            # Upsert volume: update existing or create new
            if vol_index in existing_vol_by_index:
                vol = existing_vol_by_index[vol_index]
                vol.title = _to_str(vol_data.get("title", vol.title or ""))
                vol.summary = vol_data.get("summary", vol.summary)
                vol.status = "outlined"
            else:
                vol = Volume(
                    novel_id=novel_id,
                    index=vol_index,
                    title=_to_str(vol_data.get("title", "")),
                    summary=vol_data.get("summary", ""),
                    status="outlined",
                )
                db.add(vol)
                await db.flush()
                existing_chapters_by_vol[vol_index] = {}
                created_count += 1

            # Upsert chapters within this volume
            chapters = vol_data.get("chapters", [])
            if isinstance(chapters, list):
                existing_chs = existing_chapters_by_vol.get(vol_index, {})
                for ch_data in chapters:
                    if not isinstance(ch_data, dict):
                        continue
                    ch_index = ch_data.get("index", 1)

                    if ch_index in existing_chs:
                        ch = existing_chs[ch_index]
                        # Only update outline/title if chapter has no written content yet
                        if not ch.content:
                            ch.title = _to_str(ch_data.get("title", ch.title or ""))
                            ch.outline = ch_data
                            ch.target_word_count = ch_data.get("target_word_count", ch.target_word_count)
                            ch.status = "outlining"
                            updated_count += 1
                    else:
                        ch = Chapter(
                            volume_id=vol.id,
                            index=ch_index,
                            title=_to_str(ch_data.get("title", "")),
                            outline=ch_data,
                            target_word_count=ch_data.get("target_word_count", 3000),
                            status="outlining",
                        )
                        db.add(ch)
                        created_count += 1

        # Remove volumes that are no longer in the outline AND have no chapters with content
        for vol_index, vol in existing_vol_by_index.items():
            if vol_index not in seen_vol_indices:
                chs = existing_chapters_by_vol.get(vol_index, {})
                has_content = any(ch.content for ch in chs.values())
                if not has_content:
                    await db.delete(vol)

        novel.status = "preprocess"
        await db.flush()
        await db.commit()
        logger.info(
            "Saved outline: %s volumes for novel %s (created=%s updated=%s)",
            len(volumes), novel_id, created_count, updated_count,
        )
