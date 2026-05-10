"""LeadHunterOS v2 - Multi-provider LLM Router with normalized adapters."""

from __future__ import annotations

from dataclasses import asdict
import time
from typing import Any

from loguru import logger

import config
from agent.providers import (
    LLMCompletionRequest,
    LLMProviderError,
    LLMProviderErrorKind,
    build_provider_adapters,
)
from agent.telemetry import telemetry


class LLMRouter:
    """Routes LLM calls through provider adapters with normalized errors."""

    def __init__(self, preferred_backend: str | None = None) -> None:
        self.backend = preferred_backend or config.DEFAULT_LLM_BACKEND
        self.adapters = build_provider_adapters()
        self.available_backends: list[str] = []
        self._detect_backends()
        logger.info(
            f"LLM Router initialized. Backend={self.backend}, Available={self.available_backends}"
        )

    def _detect_backends(self) -> None:
        local_adapter = self.adapters.get("local")
        if local_adapter and local_adapter.detect_available():
            self.available_backends.append("local")
        if not config.ENABLE_CLOUD_FALLBACKS:
            return
        for name in ("claude", "openai", "perplexity"):
            adapter = self.adapters.get(name)
            if adapter and adapter.detect_available():
                self.available_backends.append(name)

    def route(self, messages: list[dict], task_type: str = "general") -> dict[str, Any]:
        order = self._get_backend_order(task_type)
        last_error: LLMProviderError | None = None
        trace_id, correlation_id = telemetry.new_trace()
        telemetry.emit(
            "llm.route.start",
            trace_id=trace_id,
            correlation_id=correlation_id,
            preferred_backend=self.backend,
            task_type=task_type,
            candidate_order=order,
        )
        req = LLMCompletionRequest(
            messages=messages,
            temperature=config.TEMPERATURE,
            max_tokens=config.MAX_TOKENS,
            task_type=task_type,
            stream=False,
            metadata={"trace_id": trace_id, "correlation_id": correlation_id},
        )
        for backend in order:
            adapter = self.adapters.get(backend)
            if adapter is None or backend not in self.available_backends:
                continue
            max_attempts = max(1, int(getattr(config, "ROUTER_RETRYABLE_ATTEMPTS", 1)))
            for attempt in range(1, max_attempts + 1):
                try:
                    telemetry.emit(
                        "llm.provider.attempt",
                        trace_id=trace_id,
                        correlation_id=correlation_id,
                        provider=backend,
                        model=adapter.default_model(),
                        attempt=attempt,
                    )
                    response = adapter.complete(req)
                    telemetry.emit(
                        "llm.provider.success",
                        trace_id=trace_id,
                        correlation_id=correlation_id,
                        provider=backend,
                        model=response.model,
                        latency_ms=response.latency_ms,
                        finish_reason=response.finish_reason,
                        usage=response.usage,
                        attempt=attempt,
                    )
                    return {
                        "content": response.content,
                        "backend": backend,
                        "model": response.model,
                        "latency_ms": response.latency_ms,
                        "usage": response.usage,
                        "finish_reason": response.finish_reason,
                    }
                except LLMProviderError as exc:
                    last_error = exc
                    telemetry.emit(
                        "llm.provider.error",
                        level="WARNING",
                        trace_id=trace_id,
                        correlation_id=correlation_id,
                        provider=backend,
                        error_kind=exc.kind.value,
                        retryable=exc.retryable,
                        status_code=exc.status_code,
                        message=exc.message,
                        attempt=attempt,
                    )
                    logger.warning(f"Backend {backend} failed (attempt {attempt}/{max_attempts}): {exc}")
                    if exc.retryable and attempt < max_attempts:
                        time.sleep(max(0, getattr(config, "ROUTER_RETRY_BACKOFF_MS", 300)) / 1000.0)
                        continue
                    break
                except Exception as exc:  # pragma: no cover
                    last_error = LLMProviderError(
                        provider_name=backend,
                        kind=LLMProviderErrorKind.UNKNOWN,
                        message=str(exc),
                        retryable=False,
                    )
                    telemetry.emit(
                        "llm.provider.error",
                        level="WARNING",
                        trace_id=trace_id,
                        correlation_id=correlation_id,
                        provider=backend,
                        error_kind="unknown",
                        retryable=False,
                        message=str(exc),
                        attempt=attempt,
                    )
                    logger.warning(f"Backend {backend} failed (attempt {attempt}/{max_attempts}): {exc}")
                    break

        detail = str(last_error) if last_error else "no available providers"
        telemetry.emit(
            "llm.route.failed",
            level="ERROR",
            trace_id=trace_id,
            correlation_id=correlation_id,
            detail=detail,
            available_backends=self.available_backends,
        )
        raise RuntimeError(
            f"All backends failed. Last error: {detail}. "
            f"Available: {self.available_backends}. "
            "Check local provider health and credentials."
        )

    def _get_backend_order(self, task_type: str) -> list[str]:
        preferred = [self.backend] if self.backend in {"local", "claude", "openai", "perplexity"} else []
        if task_type == "research":
            order = ["perplexity", "local", "claude", "openai"]
        elif task_type == "heavy":
            order = ["claude", "local", "openai", "perplexity"]
        else:
            order = ["local", "claude", "openai", "perplexity"]
        return preferred + [backend for backend in order if backend not in preferred]

    def get_status(self) -> dict[str, Any]:
        return {
            "default_backend": self.backend,
            "available_backends": self.available_backends,
            "lemonade_url": config.LEMONADE_BASE_URL,
            "lemonade_model": config.LEMONADE_MODEL,
            "lemonade_reachable": "local" in self.available_backends,
            "claude_configured": bool(self.adapters["claude"].is_configured()),
            "openai_configured": bool(self.adapters["openai"].is_configured()),
            "perplexity_configured": bool(self.adapters["perplexity"].is_configured()),
            "provider_capabilities": {
                name: asdict(adapter.capabilities())
                for name, adapter in self.adapters.items()
            },
        }
