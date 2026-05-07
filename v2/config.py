"""LeadHunterOS v2 - Centralized configuration.

LLM Priority Order (as of May 2026):
  1. Lemonade Server (AMD local - PRIMARY, zero cost)
  2. Claude Opus 4 / Sonnet 4.5 (heavy/complex tasks)
  3. OpenAI GPT-4.1 (fallback or preference)
  4. Perplexity Sonar Pro (research/web-search tasks)

All external APIs: US-based only.
Local models from anywhere are fine.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM BACKEND SELECTION ───────────────────────────────────────────────
# Options: 'local', 'claude', 'openai', 'perplexity', 'auto'
# 'auto' = local first, falls back by task complexity
DEFAULT_LLM_BACKEND: str = os.getenv("DEFAULT_LLM_BACKEND", "auto")

# ── PRIMARY: LEMONADE SERVER (AMD Local) ───────────────────────────────
# Lemonade v10.3 - AMD's open-source local LLM server
# OpenAI-compatible API at http://localhost:13305/v1
# Install: pip install lemonade-server OR https://lemonade-server.ai
# Runs on: Ryzen AI NPU, Radeon ROCm GPU, Vulkan iGPU, CPU fallback
LEMONADE_BASE_URL: str = os.getenv("LEMONADE_BASE_URL", "http://localhost:13305/v1")
LEMONADE_API_KEY: str = os.getenv("LEMONADE_API_KEY", "lemonade")  # unused but required

# Recommended models for AMD PCs (Hermes function-calling compatible):
#   Qwen3-14B-Instruct-Q4_K_M  <- best quality, needs 16GB VRAM (RX 7600)
#   Qwen3-7B-Instruct-Q4_K_M   <- recommended for 8GB VRAM or laptop
#   Qwen3-4B-Instruct-Q4_K_M   <- fastest, good for scoring tasks
#   Mistral-7B-Instruct-Q4_K_M <- alternative if Qwen not available
LEMONADE_MODEL: str = os.getenv("LEMONADE_MODEL", "Qwen3-14B-Instruct-Q4_K_M")
LEMONADE_MODEL_LIGHT: str = os.getenv("LEMONADE_MODEL_LIGHT", "Qwen3-7B-Instruct-Q4_K_M")

# ── CLAUDE (Anthropic US - heavy/complex tasks) ──────────────────────────
# Use for: complex reasoning, writing quality outreach, hard enrichment
# Claude Pro account or API key both work
ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL_HEAVY: str = os.getenv("CLAUDE_MODEL_HEAVY", "claude-opus-4-5")   # Most capable
CLAUDE_MODEL_DEFAULT: str = os.getenv("CLAUDE_MODEL_DEFAULT", "claude-sonnet-4-5")  # Balanced

# ── OPENAI (ChatGPT Plus / API - fallback or preference) ─────────────────
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4.1")  # or gpt-4o
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# ── PERPLEXITY (Research/web-search tasks) ─────────────────────────────
# Use for: deep company research, finding signals with real-time web search
# Perplexity Pro account or API key
PERPLEXITY_API_KEY: str | None = os.getenv("PERPLEXITY_API_KEY")
PERPLEXITY_MODEL: str = os.getenv("PERPLEXITY_MODEL", "sonar-pro")  # real-time web search
PERPLEXITY_BASE_URL: str = "https://api.perplexity.ai"

# ── DATABASE ────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/leadhunteros"
)

# ── US-BASED DATA SOURCE APIs ──────────────────────────────────────────
APOLLO_API_KEY: str | None = os.getenv("APOLLO_API_KEY")
APOLLO_BASE_URL: str = "https://api.apollo.io/v1"

HUNTER_API_KEY: str | None = os.getenv("HUNTER_API_KEY")
HUNTER_BASE_URL: str = "https://api.hunter.io/v2"

NEWSAPI_KEY: str | None = os.getenv("NEWSAPI_KEY")
NEWSAPI_BASE_URL: str = "https://newsapi.org/v2"

REDDIT_CLIENT_ID: str | None = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET: str | None = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT: str = os.getenv("REDDIT_USER_AGENT", "LeadHunterOS/2.0")

# ── OUTREACH ─────────────────────────────────────────────────────────
SENDGRID_API_KEY: str | None = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL: str = os.getenv("FROM_EMAIL", "outreach@yourdomain.com")

# ── AGENT SETTINGS ───────────────────────────────────────────────────
AGENT_MAX_ITERATIONS: int = int(os.getenv("AGENT_MAX_ITERATIONS", "20"))
AGENT_LOOP_INTERVAL_MINUTES: int = int(os.getenv("AGENT_LOOP_INTERVAL_MINUTES", "60"))
ICP_SCORE_THRESHOLD: int = int(os.getenv("ICP_SCORE_THRESHOLD", "70"))

# ICP targeting defaults (comma-separated)
ICP_INDUSTRIES: str = os.getenv("ICP_INDUSTRIES", "SaaS,B2B Software,Fintech,HealthTech")
ICP_COMPANY_SIZE_MIN: int = int(os.getenv("ICP_COMPANY_SIZE_MIN", "10"))
ICP_COMPANY_SIZE_MAX: int = int(os.getenv("ICP_COMPANY_SIZE_MAX", "500"))
ICP_TITLES: str = os.getenv("ICP_TITLES", "VP Sales,Head of Revenue,CRO,Founder,CEO")
ICP_KEYWORDS: str = os.getenv("ICP_KEYWORDS", "sales automation,outbound,lead generation,revenue ops")


def get_available_backends() -> list[str]:
    """Return list of configured LLM backends in priority order."""
    backends = ["local"]  # Lemonade always available (local)
    if ANTHROPIC_API_KEY:
        backends.append("claude")
    if OPENAI_API_KEY:
        backends.append("openai")
    if PERPLEXITY_API_KEY:
        backends.append("perplexity")
    return backends


def validate_config() -> list[str]:
    """Return list of warnings for missing optional config."""
    warnings = []
    if not APOLLO_API_KEY:
        warnings.append("APOLLO_API_KEY not set - lead search/enrichment disabled")
    if not HUNTER_API_KEY:
        warnings.append("HUNTER_API_KEY not set - email lookup disabled")
    if not ANTHROPIC_API_KEY:
        warnings.append("ANTHROPIC_API_KEY not set - Claude backend unavailable")
    if not OPENAI_API_KEY:
        warnings.append("OPENAI_API_KEY not set - OpenAI backend unavailable")
    if not PERPLEXITY_API_KEY:
        warnings.append("PERPLEXITY_API_KEY not set - research mode unavailable")
    if not NEWSAPI_KEY:
        warnings.append("NEWSAPI_KEY not set - news signals disabled")
    if not REDDIT_CLIENT_ID:
        warnings.append("REDDIT_CLIENT_ID not set - Reddit signals disabled")
    return warnings
