"""Utility helpers for provider adapters."""

from __future__ import annotations

import time
from typing import Any

import httpx

from .base import LLMProviderError, LLMProviderErrorKind


def now_ms() -> int:
    return int(time.time() * 1000)


def classify_httpx_error(provider_name: str, exc: Exception) -> LLMProviderError:
    if isinstance(exc, httpx.TimeoutException):
        return LLMProviderError(
            provider_name=provider_name,
            kind=LLMProviderErrorKind.TIMEOUT,
            message=str(exc),
            retryable=True,
        )
    if isinstance(exc, httpx.ConnectError):
        return LLMProviderError(
            provider_name=provider_name,
            kind=LLMProviderErrorKind.NETWORK,
            message=str(exc),
            retryable=True,
        )
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        body: Any
        try:
            body = exc.response.json()
        except Exception:
            body = exc.response.text
        if status == 401 or status == 403:
            return LLMProviderError(
                provider_name=provider_name,
                kind=LLMProviderErrorKind.AUTH,
                message="authentication failed",
                retryable=False,
                status_code=status,
                raw=body,
            )
        if status == 429:
            return LLMProviderError(
                provider_name=provider_name,
                kind=LLMProviderErrorKind.RATE_LIMIT,
                message="rate limited",
                retryable=True,
                status_code=status,
                raw=body,
            )
        if 500 <= status < 600:
            return LLMProviderError(
                provider_name=provider_name,
                kind=LLMProviderErrorKind.SERVER,
                message="provider server error",
                retryable=True,
                status_code=status,
                raw=body,
            )
        return LLMProviderError(
            provider_name=provider_name,
            kind=LLMProviderErrorKind.BAD_REQUEST,
            message="bad request",
            retryable=False,
            status_code=status,
            raw=body,
        )
    return LLMProviderError(
        provider_name=provider_name,
        kind=LLMProviderErrorKind.UNKNOWN,
        message=str(exc),
        retryable=False,
    )
