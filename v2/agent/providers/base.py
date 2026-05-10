"""Provider adapter contracts for Hermes LLM routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LLMProviderErrorKind(str, Enum):
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    NETWORK = "network"
    BAD_REQUEST = "bad_request"
    SERVER = "server"
    UNAVAILABLE = "unavailable"
    PARSE = "parse"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LLMCapability:
    supports_tools: bool = True
    supports_streaming: bool = False
    supports_system_role: bool = True
    max_context_tokens: int | None = None


@dataclass
class LLMCompletionRequest:
    messages: list[dict[str, Any]]
    temperature: float
    max_tokens: int
    task_type: str = "general"
    stream: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMCompletionResponse:
    content: str
    provider_name: str
    model: str
    latency_ms: int
    raw: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    finish_reason: str = ""


@dataclass
class LLMProviderError(Exception):
    provider_name: str
    kind: LLMProviderErrorKind
    message: str
    retryable: bool = False
    status_code: int | None = None
    raw: Any = None

    def __str__(self) -> str:
        suffix = f" status={self.status_code}" if self.status_code is not None else ""
        return f"{self.provider_name}:{self.kind}:{self.message}{suffix}"


class LLMProviderAdapter:
    name: str = "unknown"

    def is_configured(self) -> bool:
        raise NotImplementedError

    def detect_available(self) -> bool:
        raise NotImplementedError

    def capabilities(self) -> LLMCapability:
        raise NotImplementedError

    def default_model(self) -> str:
        raise NotImplementedError

    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResponse:
        raise NotImplementedError
