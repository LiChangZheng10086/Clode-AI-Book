"""Local BGE embedding service. Loads once, reused across requests."""

import logging
from typing import ClassVar

from core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Lazy-loads BGE-large-zh-v1.5 for local embedding generation.

    Singleton pattern — model loaded once on first use, freed on shutdown.
    On M1 Pro with 32GB RAM: ~1.5GB RAM, ~100ms per short text encode.
    """

    _model: ClassVar = None

    @classmethod
    def _load(cls):
        if cls._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer

            device = settings.embedding_device
            if device == "cpu":
                # Auto-detect MPS on Apple Silicon
                import torch
                device = "mps" if torch.backends.mps.is_available() else "cpu"

            cls._model = SentenceTransformer(
                settings.embedding_model,
                device=device,
                trust_remote_code=True,
            )
            dim = cls._model.get_embedding_dimension()
            logger.info(f"Embedding model loaded: {settings.embedding_model} on {device} (dim={dim})")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise

    @classmethod
    def encode(cls, texts: list[str]) -> list[list[float]]:
        """Encode a batch of texts to vectors.

        Args:
            texts: List of strings to encode.

        Returns:
            List of float vectors, each of dimension embedding_dim (1024).
        """
        cls._load()
        embeddings = cls._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    @classmethod
    def unload(cls):
        """Release model memory. Call on app shutdown."""
        if cls._model is not None:
            del cls._model
            cls._model = None
            logger.info("Embedding model unloaded")
