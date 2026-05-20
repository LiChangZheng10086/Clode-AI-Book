"""Entity state timeline: tracks per-chapter state of all entities."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.base import EntityState


class EntityTracker:
    """Time-based entity state snapshots.

    After each chapter: records state changes for all entities that appeared.
    Before generation: retrieves latest state for requested entities.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_states(
        self, novel_id: UUID, entity_names: list[str]
    ) -> dict[str, dict]:
        """Get latest state for each named entity."""
        result = await self.db.execute(
            select(EntityState)
            .where(EntityState.novel_id == novel_id)
            .where(EntityState.entity_name.in_(entity_names))
        )
        entities = result.scalars().all()

        states = {}
        for entity in entities:
            if entity.state_snapshots:
                latest = entity.state_snapshots[-1]
                states[entity.entity_name] = latest.get("state", {})
        return states

    async def update_entities(
        self, novel_id: UUID, chapter_index: int, state_changes: list[dict]
    ) -> None:
        """Record entity state changes from chapter completion.

        Each state_change:
        {
            "entity_type": "character|item|faction|location",
            "entity_name": "...",
            "before": "...",
            "after": "...",
            "note": "..."
        }
        """
        for change in state_changes:
            result = await self.db.execute(
                select(EntityState)
                .where(EntityState.novel_id == novel_id)
                .where(EntityState.entity_type == change["entity_type"])
                .where(EntityState.entity_name == change["entity_name"])
            )
            entity = result.scalar_one_or_none()

            snapshot = {
                "chapter": chapter_index,
                "state": {
                    "status": change.get("after", ""),
                    "note": change.get("note", ""),
                },
            }

            if entity:
                entity.state_snapshots = (entity.state_snapshots or []) + [snapshot]
            else:
                entity = EntityState(
                    novel_id=novel_id,
                    entity_type=change["entity_type"],
                    entity_name=change["entity_name"],
                    state_snapshots=[snapshot],
                )
                self.db.add(entity)

        await self.db.flush()
