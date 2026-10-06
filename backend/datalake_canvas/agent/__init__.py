"""Agent layer: LLM providers and the query planner."""

from ..config import Settings
from .base import LLMProvider, ProviderUnavailable


def create_provider(settings: Settings) -> LLMProvider | None:
    """Build the configured provider, or ``None`` if it is not usable (e.g. no API key).

    To add a provider (say Anthropic): implement ``LLMProvider`` in a new module and add a
    branch here keyed on ``settings.llm_provider``.
    """
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            return None
        from .openai_provider import OpenAIProvider

        return OpenAIProvider(settings.openai_api_key, settings.openai_model)
    raise ProviderUnavailable(f"Unknown llm_provider {settings.llm_provider!r}")


__all__ = ["LLMProvider", "ProviderUnavailable", "create_provider"]
