import logging
import sys
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import ws
from api.novels import router as novels_router
from api.characters import router as characters_router
from api.chapters import router as chapters_router
from api.hooks import router as hooks_router
from api.settings import router as settings_router
from core.config import settings

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def setup_logging() -> None:
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG)
    console.setFormatter(fmt)

    # File handler — all logs (rotating 10MB × 5 files)
    file_all = RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_all.setLevel(logging.DEBUG)
    file_all.setFormatter(fmt)

    # File handler — errors only
    file_err = RotatingFileHandler(
        LOG_DIR / "error.log", maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_err.setLevel(logging.WARNING)
    file_err.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    # Remove uvicorn default handlers
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_all)
    root.addHandler(file_err)

    # Quiet down noisy libs
    for name in ("httpx", "httpcore", "openai", "urllib3", "asyncio"):
        logging.getLogger(name).setLevel(logging.WARNING)

    logging.getLogger("uvicorn.access").setLevel(logging.INFO)


setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("App starting up...")
    logger.info("LLM model: %s | base_url: %s", settings.llm_model, settings.llm_base_url)
    logger.info("DB: %s", settings.database_url)
    logger.info("=" * 60)

    # Ensure database tables exist (dev fallback — in production use alembic upgrade head)
    try:
        from core.database import engine, Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified/created via create_all")
    except Exception as exc:
        logger.warning(
            "Auto table creation failed (DB not reachable?): %s. "
            "Run 'alembic upgrade head' manually.",
            exc,
        )

    yield

    from core.embedding import EmbeddingService
    EmbeddingService.unload()
    logger.info("App shut down")


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(novels_router, prefix="/api/novels", tags=["novels"])
app.include_router(characters_router, prefix="/api/characters", tags=["characters"])
app.include_router(chapters_router, prefix="/api/chapters", tags=["chapters"])
app.include_router(hooks_router, prefix="/api/hooks", tags=["hooks"])
app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
app.include_router(ws.router, prefix="/api/ws", tags=["websocket"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
