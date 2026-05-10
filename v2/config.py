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


def _bool(key: str, default: bool) -> bool:
    """Safe bool parser for env flags."""
    val = os.getenv(key, "").strip().lower()
    if not val:
        return default
    if val in {"1", "true", "yes", "on"}:
        return True
    if val in {"0", "false", "no", "off"}:
        return False
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
LOCAL_LLM_TIMEOUT_SECONDS: int = _int("LOCAL_LLM_TIMEOUT_SECONDS", 300)
CLOUD_LLM_TIMEOUT_SECONDS: int = _int("CLOUD_LLM_TIMEOUT_SECONDS", 120)
ENABLE_CLOUD_FALLBACKS: bool = _bool("ENABLE_CLOUD_FALLBACKS", False)
ROUTER_RETRYABLE_ATTEMPTS: int = _int("ROUTER_RETRYABLE_ATTEMPTS", 2)
ROUTER_RETRY_BACKOFF_MS: int = _int("ROUTER_RETRY_BACKOFF_MS", 300)

# -- AGENT SETTINGS -----------------------------------------------------------
AGENT_LOOP_INTERVAL_MINUTES: int = _int("AGENT_LOOP_INTERVAL_MINUTES", 60)
AGENT_MAX_ITERATIONS: int = _int("AGENT_MAX_ITERATIONS", 15)

# -- LEAD SEARCH SETTINGS -----------------------------------------------------
LEAD_SEARCH_QUERY: str = os.getenv(
    "LEAD_SEARCH_QUERY",
    "US SMB companies with hiring, expansion, technology-change, or funding signals",
)
LEAD_MAX_RESULTS: int = _int("LEAD_MAX_RESULTS", 50)
LEAD_OUTPUT_FORMAT: str = os.getenv("LEAD_OUTPUT_FORMAT", "json")
EXPORT_LEADS_TO_CSV: bool = _bool("EXPORT_LEADS_TO_CSV", True)
LEADS_CSV_PATH: str = os.getenv("LEADS_CSV_PATH", "./leads_latest.csv")
ICP_MIN_SCORE: int = _int("ICP_MIN_SCORE", 70)
MIN_EVIDENCE_SCORE: int = _int("MIN_EVIDENCE_SCORE", 45)
MIN_SIGNAL_COUNT: int = _int("MIN_SIGNAL_COUNT", 1)

# Weighted scoring controls for Attraction/Zero-defect/Evidence composite
WEIGHT_ATTRACTION_PCT: int = _int("WEIGHT_ATTRACTION_PCT", 40)
WEIGHT_ZERO_DEFECT_PCT: int = _int("WEIGHT_ZERO_DEFECT_PCT", 35)
WEIGHT_EVIDENCE_PCT: int = _int("WEIGHT_EVIDENCE_PCT", 25)

# Competitor-style ICP scoring weights (must sum to ~100; auto-normalized)
WEIGHT_ICP_FIT_PCT: int = _int("WEIGHT_ICP_FIT_PCT", 35)
WEIGHT_INTENT_STRENGTH_PCT: int = _int("WEIGHT_INTENT_STRENGTH_PCT", 35)
WEIGHT_RECENCY_PCT: int = _int("WEIGHT_RECENCY_PCT", 15)
WEIGHT_EVIDENCE_CONFIDENCE_PCT: int = _int("WEIGHT_EVIDENCE_CONFIDENCE_PCT", 15)

# ICP target profile controls
ICP_MIN_COMPANY_SIZE: int = _int("ICP_MIN_COMPANY_SIZE", 5)
ICP_MAX_COMPANY_SIZE: int = _int("ICP_MAX_COMPANY_SIZE", 250)
ICP_TARGET_TITLES: str = os.getenv(
    "ICP_TARGET_TITLES",
    "owner,founder,president,ceo,coo,operations manager,general manager,sales manager,customer success manager",
)
ICP_TARGET_INDUSTRIES: str = os.getenv(
    "ICP_TARGET_INDUSTRIES",
    "home services,legal,accounting,it services,logistics,healthcare support,agency,agencies,saas,software",
)
TARGET_METRO: str = os.getenv("TARGET_METRO", "United States")
TARGET_REGION: str = os.getenv("TARGET_REGION", "United States")
TARGET_COUNTRY: str = os.getenv("TARGET_COUNTRY", "United States")
TARGET_COUNTRY_CODE: str = os.getenv("TARGET_COUNTRY_CODE", "US")

# -- DATABASE SETTINGS --------------------------------------------------------
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./leadhunter.db")

# -- OPTIONAL PAID API KEYS ---------------------------------------------------
# Core public-signal tools work without these. Set only when using paid fallbacks.
APOLLO_API_KEY: str = os.getenv("APOLLO_API_KEY", "")
HUNTER_API_KEY: str = os.getenv("HUNTER_API_KEY", "")
NEWSAPI_KEY: str = os.getenv("NEWSAPI_KEY", "")

# -- JOBSPY SETTINGS ----------------------------------------------------------
# Default excludes zip_recruiter because it frequently returns 403.
JOBSPY_SITES: str = os.getenv("JOBSPY_SITES", "linkedin,indeed,google")

# -- OPERATOR CONTROLS --------------------------------------------------------
SUPPRESSED_COMPANIES: str = os.getenv("SUPPRESSED_COMPANIES", "")
SUPPRESSED_DOMAINS: str = os.getenv("SUPPRESSED_DOMAINS", "")
SUPPRESSED_TITLES: str = os.getenv("SUPPRESSED_TITLES", "")
ENABLE_OUTREACH_ACTIONS: bool = _bool("ENABLE_OUTREACH_ACTIONS", False)

# -- ENTITY GRAPH + LEARNING --------------------------------------------------
ENTITY_MATCH_MIN_CONFIDENCE: float = _float("ENTITY_MATCH_MIN_CONFIDENCE", 0.6)
AUTO_REPAIR_NO_PROGRESS_LIMIT: int = _int("AUTO_REPAIR_NO_PROGRESS_LIMIT", 2)
AUTO_REPAIR_REPEAT_TOOL_LIMIT: int = _int("AUTO_REPAIR_REPEAT_TOOL_LIMIT", 3)
OUTCOME_LEARNING_ENABLED: bool = _bool("OUTCOME_LEARNING_ENABLED", True)
OUTCOME_LEARNING_WINDOW: int = _int("OUTCOME_LEARNING_WINDOW", 200)
OUTCOME_BONUS_MAX: int = _int("OUTCOME_BONUS_MAX", 15)
MIN_DISCOVERY_RESULTS: int = _int("MIN_DISCOVERY_RESULTS", 8)
MIN_DISTINCT_SIGNAL_SOURCES: int = _int("MIN_DISTINCT_SIGNAL_SOURCES", 2)

# -- OBSERVABILITY + REPLAY ---------------------------------------------------
TELEMETRY_ENABLED: bool = _bool("TELEMETRY_ENABLED", True)
TELEMETRY_REDACT: bool = _bool("TELEMETRY_REDACT", True)
TELEMETRY_SAMPLE_RATE: float = _float("TELEMETRY_SAMPLE_RATE", 1.0)
TRAJECTORY_ENABLED: bool = _bool("TRAJECTORY_ENABLED", True)
