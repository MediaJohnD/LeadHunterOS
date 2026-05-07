"""LeadHunterOS v2 - Multi-Backend LLM Router

Routes LLM calls to the best available backend:
  1. Lemonade Server (AMD local - PRIMARY)
     - via OpenAI-compatible API at http://localhost:13305/v1
     - Zero cost, fully local, AMD NPU/GPU/ROCm
  2. Claude (Anthropic US - heavy tasks)
  3. OpenAI (ChatGPT Plus / API - fallback)
  4. Perplexity (research/web-search tasks)

All cloud backends are US-based companies.
Local Lemonade runs models from any source (Qwen, Mistral, etc.)
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

import config


class LLMRouter:
    """Routes LLM calls across Lemonade (local AMD), Claude, OpenAI, and Perplexity."""

    def __init__(self) -> None:
        self.backend = config.DEFAULT_LLM_BACKEND
        self.available: list[str] = []
        self._detect_available()
        logger.info(
            f"LLM Router initialized. Backend={self.backend}, Available={self.available}"
        )

    def _detect_available(self) -> None:
        backends = []
        try:
            r = httpx.get(
                f"{config.LEMONADE_BASE_URL}/models",
                timeout=3,
                headers={"Authorization": f"Bearer {config.LEMONADE_API_KEY}"},
            )
            if r.status_code == 200:
                backends.append("local")
        except Exception:
            logger.warning("Lemonade not reachable - will skip local backend")

        if config.ANTHROPIC_API_KEY:
            backends.append("claude")
        if config.OPENAI_API_KEY:
            backends.append("openai")
        if config.PERPLEXITY_API_KEY:
            backends.append("perplexity")

        self.available = backends

    def route(
        self,
        messages: list[dict],
        task_type: str = "normal",
        force_backend: str | None = None,
    ) -> dict[str, Any]:
        """Route messages to the best backend. Returns dict with 'content' key."""
        backend = force_backend or self._pick_backend(task_type)
        logger.debug(f"Routing to backend={backend} task_type={task_type}")

        ordered = [backend] + [b for b in self.available if b != backend]
        for b in ordered:
            if b not in self.available:
                continue
            try:
                result = self._dispatch(b, messages)
                if result.get("content"):
                    return result
                logger.warning(f"Backend {b} returned empty content, trying next")
            except Exception as e:
                logger.warning(f"Backend {b} failed: {e}, trying next")

        raise RuntimeError(
            "All LLM backends failed. Check Lemonade is running and API keys are set in .env"
        )

    def _pick_backend(self, task_type: str) -> str:
        if self.backend != "auto":
            return self.backend
        if task_type == "heavy" and "claude" in self.available:
            return "claude"
        if task_type == "search" and "perplexity" in self.available:
            return "perplexity"
        if "local" in self.available:
            return "local"
        if "claude" in self.available:
            return "claude"
        if "openai" in self.available:
            return "openai"
        return self.available[0] if self.available else "local"

    def _dispatch(self, backend: str, messages: list[dict]) -> dict[str, Any]:
        dispatch_map = {
            "local": self._call_lemonade,
            "claude": self._call_claude,
            "openai": self._call_openai,
            "perplexity": self._call_perplexity,
        }
        fn = dispatch_map.get(backend)
        if not fn:
            raise ValueError(f"Unknown backend: {backend}")
        return fn(messages)

    def _call_lemonade(self, messages: list[dict]) -> dict[str, Any]:
        """Call Lemonade local AMD server (OpenAI-compatible API)."""
        payload = {
            "model": config.LEMONADE_MODEL,
            "messages": messages,
            "temperature": config.TEMPERATURE,
            "max_tokens": config.MAX_TOKENS,
        }
        r = httpx.post(
            f"{config.LEMONADE_BASE_URL}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {config.LEMONADE_API_KEY}"},
            timeout=180,
        )
        r.raise_for_status()
        data = r.json()

        # Handle Lemonade error responses gracefully
        if "error" in data:
            err = data["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise RuntimeError(f"Lemonade error: {msg}")

        if "choices" not in data or not data["choices"]:
            raise RuntimeError(f"Lemonade returned no choices: {data}")

        content = data["choices"][0]["message"]["content"] or ""
        logger.debug(f"Lemonade response: {content[:80]}...")
        return {"content": content, "backend": "local", "model": config.LEMONADE_MODEL}

    def _call_claude(self, messages: list[dict]) -> dict[str, Any]:
        """Call Anthropic Claude API."""
        import anthropic
        system_msg = ""
        conv_messages = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                conv_messages.append(m)

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=config.MAX_TOKENS,
            system=system_msg,
            messages=conv_messages,
        )
        content = response.content[0].text
        logger.debug(f"Claude response: {content[:80]}...")
        return {"content": content, "backend": "claude", "model": config.CLAUDE_MODEL}

    def _call_openai(self, messages: list[dict]) -> dict[str, Any]:
        """Call OpenAI API."""
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=messages,
            temperature=config.TEMPERATURE,
            max_tokens=config.MAX_TOKENS,
        )
        content = response.choices[0].message.content
        logger.debug(f"OpenAI response: {content[:80]}...")
        return {"content": content, "backend": "openai", "model": config.OPENAI_MODEL}

    def _call_perplexity(self, messages: list[dict]) -> dict[str, Any]:
        """Call Perplexity API (OpenAI-compatible)."""
        from openai import OpenAI
        client = OpenAI(
            api_key=config.PERPLEXITY_API_KEY,
            base_url="https://api.perplexity.ai",
        )
        response = client.chat.completions.create(
            model=config.PERPLEXITY_MODEL,
            messages=messages,
            max_tokens=config.MAX_TOKENS,
        )
        content = response.choices[0].message.content
        logger.debug(f"Perplexity response: {content[:80]}...")
        return {"content": content, "backend": "perplexity", "model": config.PERPLEXITY_MODEL}
