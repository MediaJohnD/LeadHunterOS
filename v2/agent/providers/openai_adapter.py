"""OpenAI provider adapter."""

from __future__ import annotations

from typing import Any

import httpx

import config
from .base import (
    LLMCapability,
    LLMCompletionRequest,
    LLMCompletionResponse,
    LLMProviderAdapter,
    LLMProviderError,
    LLMProviderErrorKind,
)
from .utils import classify_httpx_error, now_ms


class OpenAIAdapter(LLMProviderAdapter):
    name = "openai"
    endpoint = "https://api.openai.com/v1/chat/completions"

    def is_configured(self) -> bool:
        key = (config.OPENAI_API_KEY or "").strip()
        return bool(key and "your-key" not in key)

    def detect_available(self) -> bool:
        return self.is_configured()

    def capabilities(self) -> LLMCapability:
        return LLMCapability(supports_tools=True, supports_streaming=False, supports_system_role=True)

    def default_model(self) -> str:
        return config.OPENAI_MODEL

    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResponse:
        payload = {
            "model": self.default_model(),
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        started = now_ms()
        try:
            resp = httpx.post(
                self.endpoint,
                json=payload,
                headers={
                    "Authorization": f"Bearer {config.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=120,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except Exception as exc:
            raise classify_httpx_error(self.name, exc)

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMProviderError(
                provider_name=self.name,
                kind=LLMProviderErrorKind.PARSE,
                message="missing choices in response",
                retryable=False,
                raw=data,
            )
        msg = choices[0].get("message", {})
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = str(content)

        return LLMCompletionResponse(
            content=content,
            provider_name=self.name,
            model=self.default_model(),
            latency_ms=max(0, now_ms() - started),
            raw=data,
            usage=data.get("usage", {}) if isinstance(data, dict) else {},
            finish_reason=str(choices[0].get("finish_reason", "")),
        )
