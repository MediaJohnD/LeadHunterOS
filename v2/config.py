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

# -- LLM BACKEND SELECTION ---------------------------------------------------
# Options: 'local', 'claude', 'openai', 'perplexity', 'auto'
# 'auto' = local first, falls back by task complexity
DEFAULT_LLM_BACKEND: str = os.getenv("DEFAULT_LLM_BACKEND", "auto")

# -- PRIMARY: LEMONADE SERVER (AMD Local) ------------------------------------
# Lemonade v10.3 - AMD's open-source local LLM server
# OpenAI-compatible API at http://localhost:13305/v1
# Runs on: Ryzen AI NPU, Radeon ROCm iGPU, CPU fallback
LEMONADE_BASE_URL: str = os.getenv("LEMONADE_BASE_URL", "http://localhost:13305/v1")
LEMONADE_API_KEY: str = os.getenv("LEMONADE_API_KEY", "lemonade")  # unused but required by client
LEMONADE_MODEL: str = os.getenv(
    "LEMONADE_MODEL",
    "user.Qwen3-7B-Instruct-Q4_K_M-GGUF",  # recommended for 8GB VRAM or laptop
    # "user.Qwen3-14B-Instruct-Q4_K_M-GGUF"  # best quality, needs 16GB VRAM (RX 7600)
    # "Qwen3-8B-GGUF"  # built-in alternative
)

# -- CLOUD FALLBACK: CLAUDE (Anthropic - US) ---------------------------------
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-opus-4-5")

# -- CLOUD FALLBACK: OPENAI (US) ---------------------------------------------
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

# -- CLOUD FALLBACK: PERPLEXITY (US) -----------------------------------------
PERPLEXITY_API_KEY: str = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_MODEL: str = os.getenv(
    "PERPLEXITY_MODEL", "llama-3.1-sonar-large-128k-online"
)

# -- LLM GENERATION SETTINGS ------------------------------------------------
TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.3"))
MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "4096"))

# -- DATABASE ----------------------------------------------------------------
DATABASE_URL: str = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/leadhunteros"
)

# -- US-BASED DATA SOURCE APIs -----------------------------------------------
APOLLO_API_KEY: str = os.getenv("APOLLO_API_KEY", "")
HUNTER_API_KEY: str = os.getenv("HUNTER_API_KEY", "")
CLEARBIT_API_KEY: str = os.getenv("CLEARBIT_API_KEY", "")
NEWSAPI_KEY: str = os.getenv("NEWSAPI_KEY", "")
REDDIT_CLIENT_ID: str = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET: str = os.getenv("REDDIT_CLIENT_SECRET", "")
LINKEDIN_CLIENT_ID: str = os.getenv("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET: str = os.getenv("LINKEDIN_CLIENT_SECRET", "")
CRUNCHBASE_API_KEY: str = os.getenv("CRUNCHBASE_API_KEY", "")

# -- AGENT SETTINGS ----------------------------------------------------------
AGENT_MAX_STEPS: int = int(os.getenv("AGENT_MAX_STEPS", "15"))
AGENT_LOOP_INTERVAL_MINUTES: int = int(os.getenv("AGENT_LOOP_INTERVAL_MINUTES", "60"))
AGENT_LOG_LEVEL: str = os.getenv("AGENT_LOG_LEVEL", "INFO")
ICP_SCORE_THRESHOLD: int = int(os.getenv("ICP_MIN_SCORE", "70"))
PREFER_LOCAL: bool = os.getenv("PREFER_LOCAL", "true").lower() == "true"
