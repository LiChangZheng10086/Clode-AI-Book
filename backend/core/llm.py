from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel

from .config import settings

# seconds — avoid hanging forever when API is unreachable
_LLM_TIMEOUT_SEC = 180


def _create_chatopenai(temperature: float, max_tokens: int, model: str | None = None) -> ChatOpenAI:
    # Do not pass custom httpx clients: they disable system proxy auto-detection.
    return ChatOpenAI(
        model=model or settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=_LLM_TIMEOUT_SEC,
    )


def get_llm(temperature: float | None = None, max_tokens: int | None = None) -> BaseChatModel:
    """Get the default LLM for general use."""
    return _create_chatopenai(
        temperature=temperature or settings.llm_temperature,
        max_tokens=max_tokens or settings.llm_max_tokens,
    )


def get_planning_llm() -> BaseChatModel:
    """Get LLM for planning/orchestration tasks (lower temperature)."""
    model = settings.planning_model or settings.llm_model
    return _create_chatopenai(
        temperature=settings.planning_temperature,
        max_tokens=settings.llm_max_tokens,
        model=model,
    )


def get_polishing_llm() -> BaseChatModel:
    """Get LLM for de-AI polishing (higher temperature for diversity)."""
    return get_llm(temperature=settings.polishing_temperature)


def get_reviewer_llm() -> BaseChatModel:
    """Get LLM for chapter review (low temperature for precision)."""
    return get_llm(temperature=0.2)
