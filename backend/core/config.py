from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # App
    app_name: str = "Clode AI Book"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/clode_ai_book"
    database_sync_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/clode_ai_book"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM
    llm_model: str = "deepseek-chat"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 16384

    # Planning model (can differ from generation)
    planning_model: str = ""
    planning_temperature: float = 0.4

    # Reviewer model (stronger model for quality evaluation; empty = use llm_model)
    reviewer_model: str = ""
    reviewer_temperature: float = 0.2

    # Polishing model
    polishing_temperature: float = 0.9

    # Vector
    embedding_dim: int = 1024  # BGE-large-zh-v1.5
    embedding_model: str = "BAAI/bge-large-zh-v1.5"
    embedding_device: str = "cpu"  # MPS for Apple Silicon, cpu fallback

    # Chapter generation
    max_review_rounds: int = 3
    default_chapter_words: int = 3000

    # CORS
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
