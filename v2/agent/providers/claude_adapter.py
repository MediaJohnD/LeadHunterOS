"""Anthropic Claude provider adapter."""

from __future__ import annotations

from typing import Any

import config
from .base import (
    LLMCapability,
    LLMCompletionRequest,
    LLMCompletionResponse,
    LLMProviderAdapter,
    LLMProviderError,
    LLMProviderErrorKind,
)
from .utils import now_ms


class ClaudeAdapter(LLMProviderAdapter):
    name = "claude"

    def is_configured(self) -> bool:
        key = (config.ANTHROPIC_API_KEY or "").strip()
        return bool(key and "your-key" not in key)

    def detect_available(self) -> bool:
        return self.is_configured()

    def capabilities(self) -> LLMCapability:
        return LLMCapability(supports_tools=True, supports_streaming=False, supports_system_role=True)

    def default_model(self) -> str:
        return config.CLAUDE_MODEL

    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResponse:
        started = now_ms()
        try:
            import anthropic  # type: ignore
        except ImportError as exc:
            raise LLMProviderError(
                provider_name=self.name,
                kind=LLMProviderErrorKind.UNAVAILABLE,
                message=f"anthropic package missing: {exc}",
                retryable=False,
            )
        try:
            client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
            system_msg = ""
            user_messages: list[dict[str, Any]] = []
            for msg in request.messages:
                if msg.get("role") == "system":
                    system_msg = str(msg.get("content", ""))
                else:
                    user_messages.append(msg)

            kwargs: dict[str, Any] = {
                "model": self.default_model(),
                "max_tokens": request.max_tokens,
                "messages": user_messages,
            }
            if system_msg:
                kwargs["system"] = system_msg
            response = client.messages.create(**kwargs)
        except Exception as exc:
            text = str(exc).lower()
            if "credit" in text or "billing" in text or "insufficient" in text:
                raise LLMProviderError(
                    provider_name=self.name,
                    kind=LLMProviderErrorKind.AUTH,
                    message=str(exc),
                    retryable=False,
                )
            if "rate" in text or "429" in text:
                raise LLMProviderError(
                    provider_name=self.name,
                    kind=LLMProviderErrorKind.RATE_LIMIT,
                    message=str(exc),
                    retryable=True,
                )
            raise LLMProviderError(
                provider_name=self.name,
                kind=LLMProviderErrorKind.UNKNOWN,
                message=str(exc),
                retryable=False,
            )

        content = ""
        if getattr(response, "content", None):
            block = response.content[0]
            content = getattr(block, "text", "") or str(block)
        return LLMCompletionResponse(
            content=content,
            provider_name=self.name,
            model=self.default_model(),
            latency_ms=max(0, now_ms() - started),
            raw={"id": getattr(response, "id", "")},
            usage={},
            finish_reason="",
        )
