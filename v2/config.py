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

# -- LLM BACKEND SELECTION --------------------------------------------------
# Options: 'local', 'claude', 'openai', 'perplexity', 'auto'
# 'auto' = local first, falls back by task complexity
DEFAULT_LLM_BACKEND: str = os.getenv("DEFAULT_LLM_BACKEND", "local")

# -- PRIMARY: LEMONADE SERVER (AMD Local) ------------------------------------
# Lemonade v10.3 - AMD's open-source local LLM server
# CRITICAL: Lemonade v10+ uses /api/v1 path (NOT /v1)
# Correct URL:   http://localhost:13305/api/v1
# Incorrect URL: http://localhost:13305/v1  <-- causes 404 errors
# Runs on: Ryzen AI NPU, Radeon ROCm iGPU, CPU fallback
LEMONADE_BASE_URL: str = os.getenv("LEMONADE_BASE_URL", "http://localhost:13305/api/v1")
LEMONADE_API_KEY: str = os.getenv("LEMONADE_API_KEY", "lemonade")  # unused but required by client libs

# Model name - set to 'auto' to auto-detect from running Lemonade instance
# Or set explicitly to match 'lemonade status' output exactly
# Examples:
#   user.Qwen3-7B-Instruct-Q4_K_M-GGUF  (recommended for 8GB VRAM / laptop)
#   user.Qwen3-14B-GGUF                  (best quality, needs 16GB VRAM)
#   Qwen3-8B-GGUF                        (built-in alternative)
LEMONADE_MODEL: str = os.getenv("LEMONADE_MODEL", "auto")

# -- CLOUD FALLBACK 1: CLAUDE (Anthropic - US) --------------------------------
# Heavy reasoning tasks - only when Lemonade unavailable or task_type='heavy'
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-opus-4-5")

# -- CLOUD FALLBACK 2: OPENAI (US) --------------------------------------------
# General fallback when local and Claude both unavailable
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

# -- CLOUD FALLBACK 3: PERPLEXITY (US) ----------------------------------------
# Best for research/web-search tasks (task_type='research')
# Valid model as of 2026: 'sonar' (NOT llama-3.1-sonar-large-128k-online)
PERPLEXITY_API_KEY: str = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_MODEL: str = os.getenv("PERPLEXITY_MODEL", "sonar")

# -- GENERATION SETTINGS ------------------------------------------------------
TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.7"))
MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "4096"))

# -- AGENT SETTINGS -----------------------------------------------------------
AGENT_LOOP_INTERVAL_MINUTES: int = int(os.getenv("AGENT_LOOP_INTERVAL_MINUTES", "60"))

# -- LEAD SEARCH SETTINGS -----------------------------------------------------
LEAD_SEARCH_QUERY: str = os.getenv("LEAD_SEARCH_QUERY", "B2B SaaS companies Series A funding")
LEAD_MAX_RESULTS: int = int(os.getenv("LEAD_MAX_RESULTS", "50"))
LEAD_OUTPUT_FORMAT: str = os.getenv("LEAD_OUTPUT_FORMAT", "json")

# -- DATABASE SETTINGS --------------------------------------------------------
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./leadhunter.db")
