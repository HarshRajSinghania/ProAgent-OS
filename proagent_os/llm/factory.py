from __future__ import annotations

from functools import lru_cache

from proagent_os.config import get_settings
from proagent_os.llm.base import LLMProvider
from proagent_os.llm.mock import MockLLMProvider
from proagent_os.llm.openai_compat import OpenAICompatProvider


@lru_cache
def get_llm() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "openai":
        if not settings.llm_api_key:
            # Fall back to mock when key missing so boot never hard-fails
            return MockLLMProvider()
        return OpenAICompatProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )
    return MockLLMProvider()


def reset_llm_cache() -> None:
    get_llm.cache_clear()
