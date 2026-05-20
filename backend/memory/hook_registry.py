"""Hook registry: lifecycle management for plot hooks."""

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.base import Hook


class HookRegistry:
    """Manages hooks: detect, track, resolve, flag overdue."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_new_hooks(
        self, novel_id: UUID, chapter_index: int, new_hooks: list[dict]
    ) -> None:
        """Register hooks detected in a completed chapter."""
        for h in new_hooks:
            hook = Hook(
                novel_id=novel_id,
                hook_type=h.get("type", "mystery"),
                description=h.get("description", ""),
                planted_chapter_index=chapter_index,
                target_chapter_range=h.get("target_chapter_range"),
                priority=h.get("priority", "minor"),
                status="unresolved",
                related_entities=h.get("related_entities"),
            )
            self.db.add(hook)
        await self.db.flush()

    async def get_pending_hooks(self, novel_id: UUID) -> list[dict]:
        """Get unresolved hooks ordered by priority and target range."""
        result = await self.db.execute(
            select(Hook)
            .where(Hook.novel_id == novel_id)
            .where(Hook.status.in_(["unresolved", "in_progress"]))
            .order_by(Hook.priority.desc(), Hook.planted_chapter_index)
        )
        hooks = result.scalars().all()
        return [
            {
                "id": str(h.id),
                "hook_type": h.hook_type,
                "description": h.description,
                "planted_chapter_index": h.planted_chapter_index,
                "target_chapter_range": h.target_chapter_range,
                "priority": h.priority,
                "status": h.status,
            }
            for h in hooks
        ]

    async def get_overdue_hooks(
        self, novel_id: UUID, current_chapter_index: int
    ) -> list[dict]:
        """Find hooks whose target resolution range has passed."""
        all_hooks = await self.get_pending_hooks(novel_id)
        overdue = []
        for h in all_hooks:
            target = h.get("target_chapter_range")
            if target and isinstance(target, list) and len(target) == 2:
                if current_chapter_index > target[1]:
                    overdue.append(h)
        return overdue

    async def mark_resolved(
        self, hook_id: UUID, chapter_index: int, note: str = ""
    ) -> None:
        """Mark a hook as resolved."""
        result = await self.db.execute(select(Hook).where(Hook.id == hook_id))
        hook = result.scalar_one_or_none()
        if hook:
            hook.status = "resolved"
            hook.resolved_chapter_index = chapter_index
            hook.resolution_note = note
            await self.db.flush()

    async def mark_advanced(self, hook_ids: list[UUID]) -> None:
        """Mark hooks as being advanced."""
        for hid in hook_ids:
            result = await self.db.execute(select(Hook).where(Hook.id == hid))
            hook = result.scalar_one_or_none()
            if hook and hook.status == "unresolved":
                hook.status = "in_progress"
        await self.db.flush()

    async def process_hook_updates(
        self,
        novel_id: UUID,
        chapter_index: int,
        new_hooks: list[dict],
        resolved_hook_ids: list[UUID],
        advanced_hook_ids: list[UUID],
    ) -> None:
        """Batch update hooks after chapter completion."""
        if new_hooks:
            await self.register_new_hooks(novel_id, chapter_index, new_hooks)
        if resolved_hook_ids:
            for hid in resolved_hook_ids:
                await self.mark_resolved(hid, chapter_index)
        if advanced_hook_ids:
            await self.mark_advanced(advanced_hook_ids)
