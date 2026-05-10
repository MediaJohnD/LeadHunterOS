"""Provider adapter factory."""

from __future__ import annotations

from .base import LLMProviderAdapter
from .claude_adapter import ClaudeAdapter
from .local_adapter import LocalLemonadeAdapter
from .openai_adapter import OpenAIAdapter
from .perplexity_adapter import PerplexityAdapter


def build_provider_adapters() -> dict[str, LLMProviderAdapter]:
    adapters: list[LLMProviderAdapter] = [
        LocalLemonadeAdapter(),
        ClaudeAdapter(),
        OpenAIAdapter(),
        PerplexityAdapter(),
    ]
    return {adapter.name: adapter for adapter in adapters}
