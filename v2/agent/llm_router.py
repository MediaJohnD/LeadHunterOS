"""LeadHunterOS v2 - Multi-Backend LLM Router

Routes LLM calls to the best available backend:
  1. Lemonade Server (AMD local - PRIMARY)
     - via OpenAI-compatible API at http://localhost:13305/api/v1
     - Zero cost, fully local, AMD NPU/GPU/ROCm
     - Uses Qwen, Mistral, or any quantized GGUF model
  2. Claude (Anthropic US - heavy tasks)
  3. OpenAI (ChatGPT Plus / API - fallback)
  4. Perplexity (research/web-search tasks)

All cloud backends are US-based companies.
Local Lemonade runs models from any source (Qwen, Mistral, etc.)

NOTE: LEMONADE_BASE_URL in .env must be http://localhost:13305/api/v1
      (NOT /v1 - Lemonade v10+ uses /api/v1 path)
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

import config


class LLMRouter:
    """Routes LLM calls across Lemonade (local AMD), Claude, OpenAI, and Perplexity."""

    def __init__(self, preferred_backend: str | None = None) -> None:
        self.backend = preferred_backend or config.DEFAULT_LLM_BACKEND
        self.available_backends: list[str] = []
        self._detect_backends()
        logger.info(
            f"LLM Router initialized. Backend={self.backend}, Available={self.available_backends}"
        )

    def _detect_backends(self) -> None:
        """Detect which backends are available."""
        # Always try Lemonade first
        if self._check_lemonade():
            self.available_backends.append("local")
        if not config.ENABLE_CLOUD_FALLBACKS:
            return
        if self._has_real_key(config.ANTHROPIC_API_KEY, "sk-ant-your-key-here"):
            self.available_backends.append("claude")
        if self._has_real_key(config.OPENAI_API_KEY, "sk-your-key-here"):
            self.available_backends.append("openai")
        if self._has_real_key(config.PERPLEXITY_API_KEY, "pplx-your-key-here"):
            self.available_backends.append("perplexity")

    @staticmethod
    def _has_real_key(value: str, placeholder: str) -> bool:
        value = (value or "").strip()
        return bool(value and value != placeholder and "your-key" not in value)

    def _check_lemonade(self) -> bool:
        """Check if Lemonade server is running."""
        try:
            # Use /models endpoint to check availability
            # LEMONADE_BASE_URL should be http://localhost:13305/api/v1
            r = httpx.get(
                f"{config.LEMONADE_BASE_URL}/models",
                timeout=5,
            )
            if r.status_code == 200:
                data = r.json()
                models = data.get("data", [])
                if models:
                    model_ids = [m.get("id", "") for m in models]
                    logger.info(f"Lemonade available. Models: {model_ids}")
                    # Auto-detect the loaded model if config says 'auto'
                    if config.LEMONADE_MODEL == "auto" and model_ids:
                        config.LEMONADE_MODEL = model_ids[0]
                        logger.info(f"Auto-selected Lemonade model: {config.LEMONADE_MODEL}")
                    return True
                else:
                    logger.warning("Lemonade running but no models loaded. Run: lemonade load <model>")
                    return False
            return False
        except Exception as e:
            logger.warning(f"Lemonade not available: {e}")
            return False

    def route(self, messages: list[dict], task_type: str = "general") -> dict[str, Any]:
        """Route a request to the best available backend.

        Args:
            messages: OpenAI-format message list
            task_type: 'general', 'research', 'heavy' - influences backend selection

        Returns:
            dict with 'content', 'backend', 'model' keys
        """
        # Build ordered list of backends to try
        order = self._get_backend_order(task_type)
        last_error = None

        for backend in order:
            if backend not in self.available_backends:
                continue
            try:
                logger.info(f"Trying backend: {backend}")
                if backend == "local":
                    return self._call_lemonade(messages)
                elif backend == "claude":
                    return self._call_claude(messages)
                elif backend == "openai":
                    return self._call_openai(messages)
                elif backend == "perplexity":
                    return self._call_perplexity(messages)
            except Exception as e:
                logger.warning(f"Backend {backend} failed: {e}")
                last_error = e
                continue

        raise RuntimeError(
            f"All backends failed. Last error: {last_error}. "
            f"Available: {self.available_backends}. "
            f"Check: Is Lemonade running? (lemonade status) "
            f"Is a model loaded? (lemonade load <model>)"
        )

    def _get_backend_order(self, task_type: str) -> list[str]:
        """Return backend priority order based on task type."""
        if self.backend in {"local", "claude", "openai", "perplexity"}:
            preferred = [self.backend]
        else:
            preferred = []

        if task_type == "research":
            # Perplexity is best for web research, then local, then others
            order = ["perplexity", "local", "claude", "openai"]
        elif task_type == "heavy":
            # Heavy reasoning: Claude first, then local, then OpenAI
            order = ["claude", "local", "openai", "perplexity"]
        else:
            # Default: local first (free + private), then cloud fallbacks
            order = ["local", "claude", "openai", "perplexity"]
        return preferred + [backend for backend in order if backend not in preferred]

    def _call_lemonade(self, messages: list[dict]) -> dict[str, Any]:
        """Call Lemonade local AMD server (OpenAI-compatible API).

        Lemonade v10+ endpoint: http://localhost:13305/api/v1/chat/completions
        The LEMONADE_BASE_URL in config should be http://localhost:13305/api/v1
        """
        payload = {
            "model": config.LEMONADE_MODEL,
            "messages": messages,
            "temperature": config.TEMPERATURE,
            "max_tokens": config.MAX_TOKENS,
        }
        logger.debug(f"Lemonade request: model={config.LEMONADE_MODEL}, url={config.LEMONADE_BASE_URL}")
        r = httpx.post(
            f"{config.LEMONADE_BASE_URL}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {config.LEMONADE_API_KEY}"},
            timeout=max(60, config.LOCAL_LLM_TIMEOUT_SECONDS),
        )
        r.raise_for_status()
        data = r.json()

        # Validate response structure
        if "choices" not in data:
            error_msg = data.get("error", data)
            raise RuntimeError(f"Lemonade returned no choices: {error_msg}")

        content = data["choices"][0]["message"]["content"]
        logger.info(f"Lemonade response received ({len(content)} chars)")
        return {
            "content": content,
            "backend": "local",
            "model": config.LEMONADE_MODEL,
        }

    def _call_claude(self, messages: list[dict]) -> dict[str, Any]:
        """Call Anthropic Claude API (US-based, heavy tasks)."""
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

        # Separate system message from user messages
        system_msg = ""
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                user_messages.append(msg)

        kwargs: dict[str, Any] = {
            "model": config.CLAUDE_MODEL,
            "max_tokens": config.MAX_TOKENS,
            "messages": user_messages,
        }
        if system_msg:
            kwargs["system"] = system_msg

        response = client.messages.create(**kwargs)
        content = response.content[0].text
        logger.info(f"Claude response received ({len(content)} chars)")
        return {
            "content": content,
            "backend": "claude",
            "model": config.CLAUDE_MODEL,
        }

    def _call_openai(self, messages: list[dict]) -> dict[str, Any]:
        """Call OpenAI API (US-based, fallback)."""
        payload = {
            "model": config.OPENAI_MODEL,
            "messages": messages,
            "temperature": config.TEMPERATURE,
            "max_tokens": config.MAX_TOKENS,
        }
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {config.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        if "choices" not in data:
            raise RuntimeError(f"OpenAI returned no choices: {data}")
        content = data["choices"][0]["message"]["content"]
        logger.info(f"OpenAI response received ({len(content)} chars)")
        return {
            "content": content,
            "backend": "openai",
            "model": config.OPENAI_MODEL,
        }

    def _call_perplexity(self, messages: list[dict]) -> dict[str, Any]:
        """Call Perplexity API (US-based, research/web-search tasks).

        Use model 'sonar' for current web-grounded answers.
        """
        payload = {
            "model": config.PERPLEXITY_MODEL,
            "messages": messages,
            "temperature": config.TEMPERATURE,
            "max_tokens": config.MAX_TOKENS,
        }
        r = httpx.post(
            "https://api.perplexity.ai/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {config.PERPLEXITY_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        if "choices" not in data:
            raise RuntimeError(f"Perplexity returned no choices: {data}")
        content = data["choices"][0]["message"]["content"]
        logger.info(f"Perplexity response received ({len(content)} chars)")
        return {
            "content": content,
            "backend": "perplexity",
            "model": config.PERPLEXITY_MODEL,
        }

    def get_status(self) -> dict[str, Any]:
        """Return current router status for diagnostics."""
        lemonade_ok = self._check_lemonade()
        return {
            "default_backend": self.backend,
            "available_backends": self.available_backends,
            "lemonade_url": config.LEMONADE_BASE_URL,
            "lemonade_model": config.LEMONADE_MODEL,
            "lemonade_reachable": lemonade_ok,
            "claude_configured": self._has_real_key(config.ANTHROPIC_API_KEY, "sk-ant-your-key-here"),
            "openai_configured": self._has_real_key(config.OPENAI_API_KEY, "sk-your-key-here"),
            "perplexity_configured": self._has_real_key(config.PERPLEXITY_API_KEY, "pplx-your-key-here"),
        }
