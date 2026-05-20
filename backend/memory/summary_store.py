"""Layered summary management: chapter → volume → book."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from engine.summarizer import Summarizer
from models.base import Chapter, ChapterSummary, Volume


class SummaryStore:
    """Manages hierarchical summaries for long-context injection.

    Three layers injected into each chapter generation:
    - book_summary: ~500-1000 chars, always injected
    - volume_summary: ~300-500 chars, injected for current volume
    - recent_chapters: last 3-5 chapter summaries, for immediate continuity
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.summarizer = Summarizer()

    async def get_context_package(self, novel_id: UUID, current_chapter_index: int) -> dict:
        """Assemble summary context for chapter generation."""
        result = await self.db.execute(
            select(ChapterSummary)
            .join(Chapter)
            .join(Volume)
            .where(Volume.novel_id == novel_id)
            .where(ChapterSummary.summary_type == "book")
            .order_by(ChapterSummary.updated_at.desc())
            .limit(1)
        )
        book_summary = result.scalar_one_or_none()

        result = await self.db.execute(
            select(ChapterSummary)
            .join(Chapter)
            .join(Volume)
            .where(Volume.novel_id == novel_id)
            .where(ChapterSummary.summary_type == "volume")
            .where(Chapter.index <= current_chapter_index)
            .order_by(Chapter.index.desc())
            .limit(1)
        )
        volume_summary = result.scalar_one_or_none()

        result = await self.db.execute(
            select(ChapterSummary)
            .join(Chapter)
            .join(Volume)
            .where(Volume.novel_id == novel_id)
            .where(ChapterSummary.summary_type == "chapter")
            .where(Chapter.index < current_chapter_index)
            .order_by(Chapter.index.desc())
            .limit(5)
        )
        recent = result.scalars().all()

        return {
            "book_summary": book_summary.content if book_summary else "",
            "volume_summary": volume_summary.content if volume_summary else "",
            "recent_summaries": [s.content for s in reversed(recent)],
        }

    async def update_after_chapter(
        self, chapter_id: UUID, content: str, outline: dict
    ) -> dict:
        """After chapter completes: generate summary, update summaries."""
        result = await self.db.execute(
            select(Chapter).where(Chapter.id == chapter_id)
        )
        chapter = result.scalar_one_or_none()
        if not chapter:
            return {}

        # Generate chapter summary + extractions
        extracted = await self.summarizer.summarize_chapter(content, outline)

        # Save chapter summary
        chapter_summary = ChapterSummary(
            chapter_id=chapter_id,
            summary_type="chapter",
            content=extracted.get("summary", ""),
        )
        self.db.add(chapter_summary)

        # Update chapter record
        chapter.summary = extracted.get("summary", "")
        chapter.actual_word_count = len(content)

        await self.db.flush()

        # Check if volume just completed — update volume summary
        await self._maybe_update_volume_summary(chapter)

        # Check if book needs updated summary
        await self._maybe_update_book_summary(chapter)

        return extracted

    async def _maybe_update_volume_summary(self, chapter: Chapter) -> None:
        """Update volume summary if all chapters in volume are done."""
        result = await self.db.execute(
            select(Chapter)
            .where(Chapter.volume_id == chapter.volume_id)
            .order_by(Chapter.index)
        )
        chapters = result.scalars().all()

        done_count = sum(1 for ch in chapters if ch.status == "done")
        if done_count < len(chapters):
            return

        summaries = [ch.summary or "" for ch in chapters]
        volume_summary_text = await self.summarizer.summarize_volume(summaries)

        vol_summary = ChapterSummary(
            chapter_id=chapter.id,
            summary_type="volume",
            content=volume_summary_text,
        )
        self.db.add(vol_summary)
        await self.db.flush()

    async def _maybe_update_book_summary(self, chapter: Chapter) -> None:
        """Update book summary if needed."""
        result = await self.db.execute(
            select(ChapterSummary)
            .join(Chapter)
            .where(Chapter.volume_id == chapter.volume_id)
            .where(ChapterSummary.summary_type == "volume")
            .order_by(ChapterSummary.updated_at.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        if not latest:
            return

        result = await self.db.execute(
            select(ChapterSummary)
            .where(ChapterSummary.summary_type == "volume")
            .order_by(ChapterSummary.updated_at.desc())
        )
        all_volume_summaries = [s.content for s in result.scalars().all()]
        book_summary_text = await self.summarizer.update_book_summary(all_volume_summaries)

        book_summary = ChapterSummary(
            chapter_id=chapter.id,
            summary_type="book",
            content=book_summary_text,
        )
        self.db.add(book_summary)
        await self.db.flush()
