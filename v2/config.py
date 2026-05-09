"""LeadHunterOS v2 - Centralized configuration.

LLM Priority Order (as of May 2026):
  1. Lemonade Server (AMD local - PRIMARY, zero cost)
     - Endpoint: http://localhost:13305/api/v1  (v10+ uses /api/v1)
  2. Claude Opus 4 / Sonnet 4.5 (heavy/complex tasks)
  3. OpenAI GPT-4.1 (fallback or preference)
  4. Perplexity Sonar Pro (research/web-search tasks)

All external APIs: US-based only.
Local models from anywhere are fine.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _int(key: str, default: int) -> int:
    """Safe int parser - returns default if value is missing, empty, or non-numeric."""
    val = os.getenv(key, "").strip()
    if val and val.lstrip("-").isdigit():
        return int(val)
    return default


def _float(key: str, default: float) -> float:
    """Safe float parser - returns default if value is missing, empty, or non-numeric."""
    val = os.getenv(key, "").strip()
    try:
        return float(val) if val else default
    except ValueError:
        return default


# -- LLM BACKEND SELECTION --------------------------------------------------
# Options: 'local', 'claude', 'openai', 'perplexity'
DEFAULT_LLM_BACKEND: str = os.getenv("DEFAULT_LLM_BACKEND", "local")

# -- PRIMARY: LEMONADE SERVER (AMD Local) ------------------------------------
# Lemonade v10.3 - AMD's open-source local LLM server
# CRITICAL: Lemonade v10+ uses /api/v1 path (NOT /v1)
# Correct URL:   http://localhost:13305/api/v1
# Incorrect URL: http://localhost:13305/v1  <-- causes 404 errors
# Runs on: Ryzen AI NPU, Radeon ROCm iGPU, CPU fallback
LEMONADE_BASE_URL: str = os.getenv("LEMONADE_BASE_URL", "http://localhost:13305/api/v1")
LEMONADE_API_KEY: str = os.getenv("LEMONADE_API_KEY", "lemonade")

# Model name - 'auto' = auto-detect from running Lemonade instance
# Or set explicitly to match 'lemonade status' output exactly
# Examples:
#   user.Qwen3-7B-Instruct-Q4_K_M-GGUF  (recommended for 8GB VRAM / laptop)
#   user.Qwen3-14B-GGUF                  (best quality, needs 16GB VRAM)
LEMONADE_MODEL: str = os.getenv("LEMONADE_MODEL", "auto")

# -- CLOUD FALLBACK 1: CLAUDE (Anthropic - US) --------------------------------
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
# Current Claude API IDs use dateless IDs for 4.6+ releases.
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-opus-4-7")

# -- CLOUD FALLBACK 2: OPENAI (US) --------------------------------------------
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

# -- CLOUD FALLBACK 3: PERPLEXITY (US) ----------------------------------------
# Valid model as of 2026: 'sonar' (NOT llama-3.1-sonar-large-128k-online)
PERPLEXITY_API_KEY: str = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_MODEL: str = os.getenv("PERPLEXITY_MODEL", "sonar")

# -- GENERATION SETTINGS ------------------------------------------------------
# Uses safe parsers - will not crash if .env has stray values like 'auto'
TEMPERATURE: float = _float("TEMPERATURE", 0.7)
MAX_TOKENS: int = _int("MAX_TOKENS", 4096)

# -- AGENT SETTINGS -----------------------------------------------------------
AGENT_LOOP_INTERVAL_MINUTES: int = _int("AGENT_LOOP_INTERVAL_MINUTES", 60)
AGENT_MAX_ITERATIONS: int = _int("AGENT_MAX_ITERATIONS", 15)

# -- LEAD SEARCH SETTINGS -----------------------------------------------------
LEAD_SEARCH_QUERY: str = os.getenv("LEAD_SEARCH_QUERY", "B2B SaaS companies Series A funding")
LEAD_MAX_RESULTS: int = _int("LEAD_MAX_RESULTS", 50)
LEAD_OUTPUT_FORMAT: str = os.getenv("LEAD_OUTPUT_FORMAT", "json")
ICP_MIN_SCORE: int = _int("ICP_MIN_SCORE", 70)

# -- DATABASE SETTINGS --------------------------------------------------------
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./leadhunter.db")

# -- OPTIONAL PAID API KEYS ---------------------------------------------------
# Core public-signal tools work without these. Set only when using paid fallbacks.
APOLLO_API_KEY: str = os.getenv("APOLLO_API_KEY", "")
HUNTER_API_KEY: str = os.getenv("HUNTER_API_KEY", "")
NEWSAPI_KEY: str = os.getenv("NEWSAPI_KEY", "")
