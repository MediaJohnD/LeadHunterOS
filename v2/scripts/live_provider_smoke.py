"""Live provider smoke lane.

Purpose:
- Validate configured real providers can complete a tiny request.
- Classify failures clearly (missing creds, unavailable, request error).

Usage:
  python v2/scripts/live_provider_smoke.py
  SMOKE_PROVIDERS=openai,claude python v2/scripts/live_provider_smoke.py
"""

from __future__ import annotations

import os
import sys
from dataclasses import asdict

sys.path.insert(0, "v2")
from agent.providers import LLMCompletionRequest, LLMProviderError, build_provider_adapters


def _providers_from_env() -> list[str]:
    raw = os.getenv("SMOKE_PROVIDERS", "").strip()
    if not raw:
        return ["openai", "claude", "perplexity"]
    return [token.strip().lower() for token in raw.split(",") if token.strip()]


def main() -> int:
    adapters = build_provider_adapters()
    providers = _providers_from_env()
    request = LLMCompletionRequest(
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
        temperature=0.0,
        max_tokens=8,
        stream=False,
        task_type="general",
        metadata={"smoke": True},
    )

    failures = 0
    print("Live Provider Smoke")
    for provider in providers:
        adapter = adapters.get(provider)
        if not adapter:
            print(f"- {provider}: FAIL unknown provider")
            failures += 1
            continue
        caps = asdict(adapter.capabilities())
        if not adapter.is_configured():
            print(f"- {provider}: SKIP not configured")
            continue
        if not adapter.detect_available():
            print(f"- {provider}: FAIL configured but unavailable")
            failures += 1
            continue
        try:
            response = adapter.complete(request)
            text = (response.content or "").strip()
            ok = "ok" in text.lower()
            if ok:
                print(
                    f"- {provider}: PASS model={response.model} latency_ms={response.latency_ms} "
                    f"tool_calls={len(response.tool_calls)} stream={caps.get('streaming', False)}"
                )
            else:
                print(f"- {provider}: FAIL unexpected response={text!r}")
                failures += 1
        except LLMProviderError as exc:
            print(
                f"- {provider}: FAIL kind={exc.kind.value} retryable={exc.retryable} "
                f"status={exc.status_code} msg={exc.message}"
            )
            failures += 1
        except Exception as exc:  # pragma: no cover
            print(f"- {provider}: FAIL unexpected error={exc}")
            failures += 1

    if failures:
        print(f"Smoke result: FAIL ({failures} provider(s))")
        return 1
    print("Smoke result: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

