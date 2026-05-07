"""LeadHunterOS v2 - Multi-Backend LLM Router

Routes LLM calls to the best available backend:
  1. Lemonade Server (AMD local - PRIMARY)
     - Qwen3-14B / 7B Q4_K_M via OpenAI-compatible API
     - http://localhost:13305/v1
     - Zero cost, fully local, AMD NPU/GPU/ROCm

  2. Claude (Anthropic US - heavy tasks)
     - claude-opus-4-5 for complex reasoning
     - claude-sonnet-4-5 for balanced quality

  3. OpenAI (ChatGPT Plus / API - fallback)
     - gpt-4.1 or gpt-4o

  4. Perplexity (research/web-search tasks)
     - sonar-pro with built-in real-time web search

All cloud backends are US-based companies.
Local Lemonade runs models from any source (Qwen, Mistral, etc.)
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from loguru import logger

import config


class LLMRouter:
    """Routes calls to best available LLM backend."""

    def __init__(self, backend: str = "auto") -> None:
        """
        Args:
            backend: 'auto', 'local', 'claude', 'openai', 'perplexity'
                     'auto' = local first, fallback by availability + task
        """
        self.backend = backend or config.DEFAULT_LLM_BACKEND
        self.available = config.get_available_backends()
        logger.info(f"LLM Router initialized. Backend={self.backend}, Available={self.available}")

    # ── LEMONADE (Primary - AMD Local) ────────────────────────────────────

    def _call_lemonade(self, messages: list[dict], use_light: bool = False) -> str:
        """Call Lemonade Server (AMD local LLM - primary backend).

        Lemonade v10.3 OpenAI-compatible API:
        - Default port: 13305
        - Endpoint: http://localhost:13305/v1/chat/completions
        - Supports: Qwen3, Mistral, Gemma, Llama via GGUF
        - Hardware: Ryzen AI NPU, Radeon ROCm, Vulkan iGPU, CPU
        """
        model = config.LEMONADE_MODEL_LIGHT if use_light else config.LEMONADE_MODEL
        try:
            with httpx.Client(timeout=180) as client:  # Local can be slow on first run
                resp = client.post(
                    f"{config.LEMONADE_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {config.LEMONADE_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": 0.1,
                        "max_tokens": 4096,
                    },
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                logger.debug(f"Lemonade response ({model}): {content[:100]}...")
                return content
        except httpx.ConnectError:
            logger.warning(
                f"Lemonade Server not reachable at {config.LEMONADE_BASE_URL}. "
                "Is 'lemonade serve' running?"
            )
            raise
        except Exception as e:
            logger.warning(f"Lemonade error: {e}")
            raise

    # ── CLAUDE (Anthropic US - heavy tasks) ─────────────────────────────────

    def _call_claude(self, messages: list[dict], heavy: bool = False) -> str:
        """Call Anthropic Claude (US-based).

        Use for: complex reasoning, nuanced outreach writing, hard analysis.
        Supports Claude Pro accounts and direct API keys.
        """
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")

        model = config.CLAUDE_MODEL_HEAVY if heavy else config.CLAUDE_MODEL_DEFAULT
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
            system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
            user_msgs = [m for m in messages if m["role"] != "system"]
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=system_msg,
                messages=user_msgs,
            )
            content = response.content[0].text
            logger.debug(f"Claude response ({model}): {content[:100]}...")
            return content
        except Exception as e:
            logger.error(f"Claude error: {e}")
            raise

    # ── OPENAI (ChatGPT Plus / API - fallback) ─────────────────────────────

    def _call_openai(self, messages: list[dict]) -> str:
        """Call OpenAI GPT (US-based).

        Use for: when Claude is unavailable or user prefers GPT-4.1.
        Supports ChatGPT Plus accounts and direct API keys.
        """
        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured")
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=config.OPENAI_API_KEY,
                base_url=config.OPENAI_BASE_URL,
            )
            response = client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=messages,
                temperature=0.1,
                max_tokens=4096,
            )
            content = response.choices[0].message.content
            logger.debug(f"OpenAI response ({config.OPENAI_MODEL}): {content[:100]}...")
            return content
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            raise

    # ── PERPLEXITY (Research / web-search tasks) ──────────────────────────

    def _call_perplexity(self, messages: list[dict]) -> str:
        """Call Perplexity Sonar Pro (US-based, real-time web search).

        Use for: deep company research, finding real-time signals,
        research tasks that need current web data.
        Compatible with Perplexity Pro accounts and API keys.
        """
        if not config.PERPLEXITY_API_KEY:
            raise RuntimeError("PERPLEXITY_API_KEY not configured")
        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(
                    f"{config.PERPLEXITY_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {config.PERPLEXITY_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": config.PERPLEXITY_MODEL,  # sonar-pro
                        "messages": messages,
                        "temperature": 0.1,
                        "max_tokens": 4096,
                        "return_citations": True,
                        "search_recency_filter": "week",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                # Include citations if available
                citations = data.get("citations", [])
                if citations:
                    content += f"\n\nSources: {', '.join(citations[:3])}"
                logger.debug(f"Perplexity response: {content[:100]}...")
                return content
        except Exception as e:
            logger.error(f"Perplexity error: {e}")
            raise

    # ── MAIN ROUTING LOGIC ────────────────────────────────────────────────

    def complete(
        self,
        messages: list[dict],
        task_type: str = "standard",
    ) -> str:
        """Route LLM call to best backend.

        Args:
            messages: Chat messages list (OpenAI format)
            task_type: Hint for routing:
                'standard'  -> Lemonade local
                'heavy'     -> Claude Opus 4 (complex reasoning)
                'research'  -> Perplexity (real-time web search)
                'fallback'  -> try all in order
        """
        backend = self.backend

        # If explicitly set, use that backend
        if backend == "claude":
            return self._call_claude(messages, heavy=(task_type == "heavy"))
        elif backend == "openai":
            return self._call_openai(messages)
        elif backend == "perplexity":
            return self._call_perplexity(messages)
        elif backend == "local":
            return self._call_lemonade(messages)

        # AUTO mode: smart routing by task type + availability
        if task_type == "research" and config.PERPLEXITY_API_KEY:
            logger.info("Auto-routing to Perplexity (research task)")
            try:
                return self._call_perplexity(messages)
            except Exception:
                pass

        if task_type == "heavy" and config.ANTHROPIC_API_KEY:
            logger.info("Auto-routing to Claude Opus (heavy task)")
            try:
                return self._call_claude(messages, heavy=True)
            except Exception:
                pass

        # Default: try Lemonade local first
        logger.info("Routing to Lemonade (local AMD)")
        try:
            return self._call_lemonade(messages)
        except Exception:
            logger.warning("Lemonade unavailable, trying cloud fallbacks...")

        # Cloud fallbacks in priority order
        for fallback_name, fallback_fn in [
            ("claude", lambda: self._call_claude(messages)),
            ("openai", lambda: self._call_openai(messages)),
            ("perplexity", lambda: self._call_perplexity(messages)),
        ]:
            if fallback_name in self.available:
                try:
                    logger.info(f"Falling back to {fallback_name}")
                    return fallback_fn()
                except Exception as e:
                    logger.warning(f"{fallback_name} failed: {e}")
                    continue

        raise RuntimeError(
            "All LLM backends failed. "
            "Check that Lemonade is running (lemonade serve) "
            "or set ANTHROPIC_API_KEY / OPENAI_API_KEY in .env"
        )
