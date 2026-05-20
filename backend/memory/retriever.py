"""Vector-based context retrieval via local BGE embedding + pgvector."""

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.embedding import EmbeddingService

logger = logging.getLogger(__name__)


class ContextRetriever:
    """Retrieves relevant content via pgvector similarity search.

    Uses local BGE-large-zh-v1.5 for embedding generation.
    Stores vectors in chapter_embeddings table for reuse.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def index_chapter(
        self, chapter_id: UUID, content: str, chunk_size: int = 500
    ) -> None:
        """Split chapter into chunks, embed, and store in pgvector.

        Args:
            chapter_id: Chapter UUID.
            content: Full chapter text.
            chunk_size: Characters per chunk (~500 chars per chunk).
        """
        chunks = self._split_text(content, chunk_size)
        if not chunks:
            return

        embeddings = EmbeddingService.encode(chunks)

        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            await self.db.execute(
                text("""
                    INSERT INTO chapter_embeddings (id, chapter_id, chunk_index, content, embedding)
                    VALUES (gen_random_uuid(), :chapter_id, :chunk_index, :content, :embedding)
                """),
                {
                    "chapter_id": chapter_id,
                    "chunk_index": i,
                    "content": chunk,
                    "embedding": emb,
                },
            )
        await self.db.flush()
        logger.info(f"Indexed {len(chunks)} chunks for chapter {chapter_id}")

    async def retrieve_relevant_chunks(
        self, query_text: str, novel_id: UUID, top_k: int = 5
    ) -> list[str]:
        """Encode query and search for similar chunks from past chapters.

        Args:
            query_text: Natural language query (e.g., outline description).
            novel_id: Novel UUID to scope search.
            top_k: Number of chunks to return.

        Returns:
            List of relevant text chunks.
        """
        # Check if any embeddings exist
        result = await self.db.execute(
            text("""
                SELECT COUNT(*) FROM chapter_embeddings ce
                JOIN chapters c ON c.id = ce.chapter_id
                JOIN volumes v ON v.id = c.volume_id
                WHERE v.novel_id = :novel_id
            """),
            {"novel_id": novel_id},
        )
        count = result.scalar()
        if not count:
            return []

        # Encode query and search
        query_embedding = EmbeddingService.encode([query_text])[0]

        result = await self.db.execute(
            text("""
                SELECT ce.content, 1 - (ce.embedding <=> :query_vec) AS similarity
                FROM chapter_embeddings ce
                JOIN chapters c ON c.id = ce.chapter_id
                JOIN volumes v ON v.id = c.volume_id
                WHERE v.novel_id = :novel_id
                ORDER BY ce.embedding <=> :query_vec
                LIMIT :top_k
            """),
            {
                "query_vec": query_embedding,
                "novel_id": novel_id,
                "top_k": top_k,
            },
        )
        rows = result.fetchall()
        logger.info(f"Retrieved {len(rows)} relevant chunks")
        return [row[0] for row in rows]

    async def build_context_chunks(
        self, chapter_outline: dict, novel_id: UUID
    ) -> dict:
        """Build on-demand context from vector retrieval.

        Uses chapter outline as search query to find relevant
        worldbuilding and past chapter content.
        """
        query_parts = []
        for scene in chapter_outline.get("scenes", []):
            query_parts.append(scene.get("purpose", ""))
            query_parts.append(scene.get("setting", ""))
            for beat in scene.get("key_beats", []):
                query_parts.append(str(beat))
        query = " ".join(filter(None, query_parts))

        if not query.strip():
            return {"world_setting_chunks": [], "past_chapter_chunks": []}

        chunks = await self.retrieve_relevant_chunks(query, novel_id)

        return {
            "world_setting_chunks": chunks[:3],
            "past_chapter_chunks": chunks[3:],
        }

    def _split_text(self, text: str, chunk_size: int) -> list[str]:
        """Split long text into overlapping chunks, breaking at sentence boundaries."""
        sentences = text.replace("！", "。").replace("？", "。").replace("\n", "。").split("。")
        chunks = []
        current = ""
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if len(current) + len(sent) <= chunk_size:
                current += sent + "。"
            else:
                if current:
                    chunks.append(current.strip())
                current = sent + "。"
        if current.strip():
            chunks.append(current.strip())
        return chunks
