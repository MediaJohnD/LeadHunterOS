"""Local Lemonade provider adapter."""

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


class LocalLemonadeAdapter(LLMProviderAdapter):
    name = "local"

    def __init__(self) -> None:
        self.base_url = config.LEMONADE_BASE_URL.rstrip("/")
        self.api_key = config.LEMONADE_API_KEY
        self.model = config.LEMONADE_MODEL

    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    def detect_available(self) -> bool:
        if not self.is_configured():
            return False
        try:
            resp = httpx.get(f"{self.base_url}/models", timeout=5)
            if resp.status_code != 200:
                return False
            data = resp.json()
            models = data.get("data", []) if isinstance(data, dict) else []
            if self.model == "auto" and models:
                first = models[0].get("id")
                if first:
                    config.LEMONADE_MODEL = first
                    self.model = first
            return bool(models)
        except Exception:
            return False

    def capabilities(self) -> LLMCapability:
        return LLMCapability(
            supports_tools=True,
            supports_streaming=False,
            supports_system_role=True,
            max_context_tokens=4096,
        )

    def default_model(self) -> str:
        return self.model

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
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=max(60, config.LOCAL_LLM_TIMEOUT_SECONDS),
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
