"""LeadHunterOS v2 - Centralized configuration.
Loads all env vars with sensible defaults.
Local LLM is always tried first; Claude is fallback only.
All external APIs must be US-based.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM settings ──────────────────────────────────────────────
# Local Ollama (primary)
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv(
    "OLLAMA_MODEL",
    "adrienbrault/nous-hermes2pro-llama3-8b:Q4_K_M"
)

# Claude (fallback only - Anthropic US)
ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-3-5-haiku-20241022")

# Prefer local; fall back to Claude if Ollama is unavailable
USE_LOCAL_FIRST: bool = True

# ── Database ───────────────────────────────────────────────────
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/leadhunteros"
)

# ── US-based data source APIs ─────────────────────────────────
# Apollo.io - lead enrichment (US company)
APOLLO_API_KEY: str | None = os.getenv("APOLLO_API_KEY")
APOLLO_BASE_URL: str = "https://api.apollo.io/v1"

# Hunter.io - email finder (US company)
HUNTER_API_KEY: str | None = os.getenv("HUNTER_API_KEY")
HUNTER_BASE_URL: str = "https://api.hunter.io/v2"

# NewsAPI - signal monitoring (US company)
NEWSAPI_KEY: str | None = os.getenv("NEWSAPI_KEY")
NEWSAPI_BASE_URL: str = "https://newsapi.org/v2"

# Reddit - PRAW (US company)
REDDIT_CLIENT_ID: str | None = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET: str | None = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT: str = os.getenv("REDDIT_USER_AGENT", "LeadHunterOS/2.0")

# ── Agent settings ────────────────────────────────────────────
AGENT_MAX_ITERATIONS: int = int(os.getenv("AGENT_MAX_ITERATIONS", "15"))
AGENT_LOOP_INTERVAL_MINUTES: int = int(os.getenv("AGENT_LOOP_INTERVAL_MINUTES", "60"))

# ICP scoring threshold (0-100)
ICP_SCORE_THRESHOLD: int = int(os.getenv("ICP_SCORE_THRESHOLD", "70"))

# ── Outreach settings ─────────────────────────────────────────
# SendGrid (US company) - for email outreach
SENDGRID_API_KEY: str | None = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL: str = os.getenv("FROM_EMAIL", "outreach@yourdomain.com")


def validate_config() -> list[str]:
    """Return list of missing required config keys."""
    required = {
        "DATABASE_URL": DATABASE_URL,
    }
    warnings = []
    if not APOLLO_API_KEY:
        warnings.append("APOLLO_API_KEY not set - enrichment disabled")
    if not HUNTER_API_KEY:
        warnings.append("HUNTER_API_KEY not set - email lookup disabled")
    if not ANTHROPIC_API_KEY:
        warnings.append("ANTHROPIC_API_KEY not set - Claude fallback disabled")
    if not NEWSAPI_KEY:
        warnings.append("NEWSAPI_KEY not set - news signals disabled")
    return warnings
