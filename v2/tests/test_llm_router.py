from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, "v2")

from agent.llm_router import LLMRouter
import config
from agent.providers.base import (
    LLMCapability,
    LLMCompletionRequest,
    LLMCompletionResponse,
    LLMProviderAdapter,
    LLMProviderError,
    LLMProviderErrorKind,
)


class FakeAdapter(LLMProviderAdapter):
    def __init__(self, name: str, available: bool, should_fail: bool = False) -> None:
        self.name = name
        self._available = available
        self._should_fail = should_fail

    def is_configured(self) -> bool:
        return self._available

    def detect_available(self) -> bool:
        return self._available

    def capabilities(self) -> LLMCapability:
        return LLMCapability()

    def default_model(self) -> str:
        return "fake-model"

    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResponse:
        del request
        if self._should_fail:
            raise LLMProviderError(self.name, LLMProviderErrorKind.TIMEOUT, "timeout", retryable=True)
        return LLMCompletionResponse("ok", self.name, "fake-model", 1)


class FlakyAdapter(FakeAdapter):
    def __init__(self, name: str, available: bool) -> None:
        super().__init__(name, available, should_fail=False)
        self.calls = 0

    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResponse:
        del request
        self.calls += 1
        if self.calls == 1:
            raise LLMProviderError(self.name, LLMProviderErrorKind.TIMEOUT, "timeout", retryable=True)
        return LLMCompletionResponse("ok", self.name, "fake-model", 1)


class RouterTests(unittest.TestCase):
    def test_fallback(self) -> None:
        adapters = {
            "local": FakeAdapter("local", True, should_fail=True),
            "openai": FakeAdapter("openai", True, should_fail=False),
            "claude": FakeAdapter("claude", False),
            "perplexity": FakeAdapter("perplexity", False),
        }
        with patch("agent.llm_router.build_provider_adapters", return_value=adapters), patch.object(config, "ENABLE_CLOUD_FALLBACKS", True):
            router = LLMRouter(preferred_backend="local")
            response = router.route([{"role": "user", "content": "hi"}])
        self.assertEqual(response["backend"], "openai")

    def test_retryable_error_retries_same_provider(self) -> None:
        local = FlakyAdapter("local", True)
        adapters = {
            "local": local,
            "openai": FakeAdapter("openai", True, should_fail=False),
            "claude": FakeAdapter("claude", False),
            "perplexity": FakeAdapter("perplexity", False),
        }
        with patch("agent.llm_router.build_provider_adapters", return_value=adapters), \
             patch.object(config, "ENABLE_CLOUD_FALLBACKS", True), \
             patch.object(config, "ROUTER_RETRYABLE_ATTEMPTS", 2), \
             patch.object(config, "ROUTER_RETRY_BACKOFF_MS", 1):
            router = LLMRouter(preferred_backend="local")
            response = router.route([{"role": "user", "content": "hi"}])
        self.assertEqual(response["backend"], "local")
        self.assertEqual(local.calls, 2)


if __name__ == "__main__":
    unittest.main()
