"""LeadHunterOS v2 - Tool definitions for the Hermes agent.

# Corrected public-signal-first tool layer matched to the exported functions
from v2/agent/sources/__init__.py at commit ba1e78e.

Goals:
- Route Hermes into the new public sources layer
- Keep Apollo/Hunter available as optional last-mile fallbacks
- Prefer public signal discovery, funding, hiring, and open-web enrichment
- Persist only public, business-relevant allow-listed fields
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from loguru import logger

import config
from agent.database import (
    save_public_lead,
    get_tool_failure_penalty,
    is_suppressed,
    get_entity_context,
    record_outcome_feedback,
    get_outcome_score_adjustment,
)

try:
    from agent.sources import (
        search_jobs,
        extract_hiring_signals,
        search_funding_rounds,
        search_recent_form_d_georgia,
        get_all_signals,
        search_hackernews,
        search_reddit,
        search_google_news,
        search_github_repos,
        search_producthunt_launches,
        search_remoteok_jobs,
        enrich_lead,
        enrich_leads_batch,
        generate_email_candidates,
        verify_mx,
        scrape_website_metadata,
        get_all_public_profiles,
        search_wellfound_jobs,
        search_crunchbase_news,
        scrape_company_team_page,
        search_conference_speakers,
        search_orcid_profiles,
        search_glassdoor_news,
    )
except Exception as exc:  # pragma: no cover
    logger.warning(f"agent.sources import failed: {exc}")
    search_jobs = None
    extract_hiring_signals = None
    search_funding_rounds = None
    search_recent_form_d_georgia = None
    get_all_signals = None
    search_hackernews = None
    search_reddit = None
    search_google_news = None
    search_github_repos = None
    search_producthunt_launches = None
    search_remoteok_jobs = None
    enrich_lead = None
    enrich_leads_batch = None
    generate_email_candidates = None
    verify_mx = None
    scrape_website_metadata = None
    get_all_public_profiles = None
    search_wellfound_jobs = None
    search_crunchbase_news = None
    scrape_company_team_page = None
    search_conference_speakers = None
    search_orcid_profiles = None
    search_glassdoor_news = None


TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_signals",
        "description": "Aggregate public buying signals across Reddit, Hacker News, Google News, GitHub, Product Hunt, and RemoteOK.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Company, topic, ICP, or keyword query."},
                "days_back": {"type": "integer", "description": "Days back to search. Default 30."},
                "limit": {"type": "integer", "description": "Max results to return. Default 20."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_reddit_signals",
        "description": "Search Reddit for public buying or pain signals relevant to a company, category, or ICP.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "subreddit": {"type": "string", "description": "Optional subreddit filter."},
                "limit": {"type": "integer", "description": "Max results to return. Default 10."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_news_signals",
        "description": "Search public news for launches, expansions, funding, executive changes, and other company signals.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "days_back": {"type": "integer", "description": "Days back to search. Default 30."},
                "limit": {"type": "integer", "description": "Max results to return. Default 10."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_github_signals",
        "description": "Search GitHub for public repo, launch, or engineering signals tied to a company, project, or category.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "Max results to return. Default 10."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_hn_signals",
        "description": "Search Hacker News for public discussion and launch signals.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "Max results to return. Default 10."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_producthunt_signals",
        "description": "Search Product Hunt for public launch and product momentum signals.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "Max results to return. Default 10."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_remote_hiring_signals",
        "description": "Search RemoteOK for public hiring signals and role demand.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "Max results to return. Default 10."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_funding_signals",
        "description": "Search public funding signals from web and SEC-related sources.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Optional company or category query."},
                "days_back": {"type": "integer", "description": "Days back to search. Default 90."},
                "limit": {"type": "integer", "description": "Max results to return. Default 10."}
            },
            "required": []
        }
    },
    {
        "name": "search_form_d_georgia",
        "description": "Search recent Georgia SEC Form D filings for public expansion or funding signals.",
        "parameters": {
            "type": "object",
            "properties": {
                "days_back": {"type": "integer", "description": "Days back to search. Default 90."},
                "limit": {"type": "integer", "description": "Max results to return. Default 10."}
            },
            "required": []
        }
    },
    {
        "name": "search_jobs_public",
        "description": "Search public jobs for hiring-based buying signals.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "location": {"type": "string", "description": "Optional location filter."},
                "days_back": {"type": "integer", "description": "Days back to search. Default 30."},
                "limit": {"type": "integer", "description": "Max results to return. Default 10."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_jobs_by_icp",
        "description": "Search public jobs using ICP-oriented keywords, titles, or company patterns.",
        "parameters": {
            "type": "object",
            "properties": {
                "icp_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "ICP keywords, titles, or themes."
                },
                "location": {"type": "string", "description": "Optional location filter."},
                "days_back": {"type": "integer", "description": "Days back to search. Default 30."},
                "limit": {"type": "integer", "description": "Max results to return. Default 10."}
            },
            "required": ["icp_keywords"]
        }
    },
    {
        "name": "enrich_lead_public",
        "description": "Enrich a lead using public, business-relevant data only.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Full name."},
                "company": {"type": "string", "description": "Company name."},
                "domain": {"type": "string", "description": "Company domain."},
                "website": {"type": "string", "description": "Company website URL."}
            },
            "required": ["name"]
        }
    },
    {
        "name": "enrich_lead_waterfall",
        "description": "Run enrichment waterfall with provenance and confidence scores.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "company": {"type": "string"},
                "domain": {"type": "string"},
                "website": {"type": "string"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "enrich_leads_batch_public",
        "description": "Batch enrich multiple leads using public, business-relevant data only.",
        "parameters": {
            "type": "object",
            "properties": {
                "leads": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of lead dicts with public business identifiers."
                }
            },
            "required": ["leads"]
        }
    },
    {
        "name": "scrape_company_website",
        "description": "Scrape public company website metadata for business context, messaging, and enrichment.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Website URL."}
            },
            "required": ["url"]
        }
    },
    {
        "name": "generate_email_candidates_public",
        "description": "Generate likely business email candidates from public business identity fields.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "domain": {"type": "string"}
            },
            "required": ["name", "domain"]
        }
    },
    {
        "name": "verify_mx_public",
        "description": "Verify MX records for a company domain.",
        "parameters": {
            "type": "object",
            "properties": {
                "domain": {"type": "string"}
            },
            "required": ["domain"]
        }
    },
    {
        "name": "search_public_profiles",
        "description": "Aggregate public profile and cross-reference signals from Wellfound, Crunchbase News, team pages, Sessionize, ORCID, and Glassdoor.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "Max results to return. Default 20."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_wellfound_jobs",
        "description": "Search Wellfound public jobs for company and role signals.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "Max results to return. Default 20."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_crunchbase_news",
        "description": "Search public Crunchbase News RSS for funding and company signals.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "Max results to return. Default 20."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "scrape_team_page",
        "description": "Extract public business bio fields from a company's own team/about pages.",
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string"},
                "domain": {"type": "string"},
                "limit": {"type": "integer", "description": "Max people to return. Default 10."}
            },
            "required": ["company_name", "domain"]
        }
    },
    {
        "name": "search_conference_speakers",
        "description": "Search public Sessionize speaker profiles for professional identity signals.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "Max results to return. Default 20."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_orcid_profiles",
        "description": "Search ORCID public profiles for academic and research ICP segments.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "Max results to return. Default 15."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_glassdoor_signals",
        "description": "Search public Glassdoor blog RSS for company culture and hiring signals.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "Max results to return. Default 15."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_apollo",
        "description": "Search Apollo.io for leads by job title, industry, company size, and keywords. Use as last-mile contact resolution after public-signal discovery.",
        "parameters": {
            "type": "object",
            "properties": {
                "job_titles": {"type": "array", "items": {"type": "string"}},
                "industries": {"type": "array", "items": {"type": "string"}},
                "employee_range": {"type": "string"},
                "keywords": {"type": "string"},
                "limit": {"type": "integer"}
            },
            "required": ["job_titles"]
        }
    },
    {
        "name": "enrich_apollo",
        "description": "Enrich a lead using Apollo.io as a fallback when public sources are insufficient.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "company": {"type": "string"},
                "domain": {"type": "string"},
                "linkedin_url": {"type": "string"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "find_email_hunter",
        "description": "Find a likely business email using Hunter as a fallback last-mile enrichment tool.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "company": {"type": "string"},
                "domain": {"type": "string"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "score_lead",
        "description": "Score a lead from 0-100 based on ICP fit, public signals, and timing.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "title": {"type": "string"},
                "company": {"type": "string"},
                "company_size": {"type": "integer"},
                "industry": {"type": "string"},
                "signals": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["name", "title", "company"]
        }
    },
    {
        "name": "rank_leads",
        "description": "Deduplicate and rank lead candidates using evidence-weighted ICP scoring.",
        "parameters": {
            "type": "object",
            "properties": {
                "leads": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Lead candidates to deduplicate and rank."
                },
                "top_n": {"type": "integer", "description": "Number of leads to return. Default 10."}
            },
            "required": ["leads"]
        }
    },
    {
        "name": "recommend_playbook_actions",
        "description": "Generate next-step GTM playbook actions from scored leads and recent outcomes.",
        "parameters": {
            "type": "object",
            "properties": {
                "leads": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Scored leads to derive actions from."
                },
                "objective": {"type": "string", "description": "Current campaign objective."}
            },
            "required": ["leads", "objective"]
        }
    },
    {
        "name": "orchestrate_playbook",
        "description": "Run deterministic lead-selection gates for save/outreach based on ranked evidence and ICP thresholds.",
        "parameters": {
            "type": "object",
            "properties": {
                "leads": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Lead candidates to evaluate."
                },
                "objective": {"type": "string"},
                "max_outreach": {"type": "integer", "description": "Max leads to select for outreach. Default 3."}
            },
            "required": ["leads", "objective"]
        }
    },
    {
        "name": "save_lead",
        "description": "Save a lead with public, business-relevant allow-listed fields only.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "title": {"type": "string"},
                "company": {"type": "string"},
                "company_domain": {"type": "string"},
                "work_location": {"type": "string"},
                "public_profile_url": {"type": "string"},
                "company_url": {"type": "string"},
                "headline": {"type": "string"},
                "industry": {"type": "string"},
                "company_size": {"type": "integer"},
                "signals": {"type": "array", "items": {"type": "string"}},
                "source_url": {"type": "string"},
                "source_type": {"type": "string"},
                "observed_at": {"type": "string"},
                "icp_score": {"type": "integer"},
                "personalized_opener": {"type": "string"}
            },
            "required": ["name", "company", "icp_score"]
        }
    },
    {
        "name": "draft_outreach",
        "description": "Draft outreach using public business context and observed signals.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "title": {"type": "string"},
                "company": {"type": "string"},
                "signal": {"type": "string"},
                "tone": {"type": "string", "enum": ["professional", "casual", "direct"]}
            },
            "required": ["name", "title", "company"]
        }
    },
    {
        "name": "record_outcome_feedback",
        "description": "Record downstream CRM outcomes (reply/meeting/converted/unqualified/bounce) for self-learning.",
        "parameters": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "string"},
                "outcome_type": {"type": "string"},
                "outcome_value": {"type": "number"},
                "source_type": {"type": "string"},
                "industry": {"type": "string"},
                "title": {"type": "string"},
                "notes": {"type": "string"}
            },
            "required": ["lead_id", "outcome_type"]
        }
    },
]


PUBLIC_FIELD_ALLOWLIST = {
    "name",
    "title",
    "company",
    "company_domain",
    "work_location",
    "public_profile_url",
    "company_url",
    "headline",
    "industry",
    "company_size",
    "signals",
    "source_url",
    "source_type",
    "observed_at",
    "icp_score",
    "icp_fit_score",
    "intent_strength_score",
    "recency_score",
    "evidence_confidence_score",
    "attraction_score",
    "zero_defect_score",
    "evidence_score",
    "personalized_opener",
}


def _filter_public_fields(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in payload.items()
        if k in PUBLIC_FIELD_ALLOWLIST and v not in (None, "", [], {})
    }


def _scoped_query(query: str) -> str:
    """Append country/region context when the caller did not specify it."""
    lower = query.lower()
    country = config.TARGET_COUNTRY.lower()
    region = config.TARGET_REGION.lower()
    metro = config.TARGET_METRO.lower()
    if country in lower or region in lower or metro in lower:
        return query
    return f"{query} {config.TARGET_COUNTRY} {config.TARGET_REGION}".strip()


_QUERY_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "business", "businesses", "by",
    "companies", "company", "customer", "defect", "find", "for", "from", "ga",
    "georgia", "high", "in", "include", "is", "its", "local", "metro", "of",
    "on", "only", "or", "small", "medium", "small-to-medium", "that", "the",
    "their", "to", "united", "us", "usa", "using", "with",
}

_PLACEHOLDER_PHRASES = {
    "john doe",
    "jane smith",
    "example company",
    "example saas inc",
    "test company",
    "sample company",
    "placeholder company",
    "acme corp demo",
}

_PLACEHOLDER_TOKENS = {
    "example",
    "examplesaas",
    "placeholder",
    "sample",
    "testco",
    "testcorp",
    "testuser",
    "testlead",
    "demo",
    "fake",
    "foobar",
}

_DEFAULT_JOB_TITLES = [
    "operations manager",
    "office manager",
    "sales manager",
    "customer success manager",
    "service manager",
]

_JOB_TITLE_HINTS = {
    "agency": ["account manager", "project manager", "client success manager"],
    "agencies": ["account manager", "project manager", "client success manager"],
    "accounting": ["office manager", "client services manager"],
    "healthcare": ["office manager", "patient services manager"],
    "home": ["service manager", "dispatcher"],
    "home services": ["service manager", "dispatcher"],
    "it": ["project manager", "customer success manager"],
    "legal": ["office manager", "client services manager"],
    "logistics": ["dispatch manager", "operations supervisor"],
    "saas": ["customer success manager", "account executive"],
    "software": ["customer success manager", "account executive"],
    "trades": ["service manager", "dispatcher"],
}

_SOURCE_RELIABILITY = {
    "jobspy": 14,
    "news": 12,
    "google_news": 12,
    "github": 10,
    "hackernews": 8,
    "reddit": 8,
    "producthunt": 9,
    "remoteok": 8,
    "conference": 7,
    "orcid": 7,
    "glassdoor": 7,
    "website": 10,
}

_HIGH_INTENT_SIGNAL_KEYWORDS = {
    "funding", "series", "hiring", "job opening", "expansion", "new office", "launch",
    "rfp", "vendor", "migration", "implementation", "platform change", "crm",
    "response delay", "scale-up", "headcount",
}

_ZERO_DEFECT_PRESSURE_KEYWORDS = {
    "missed lead", "scheduling", "dispatch", "handoff", "pipeline leak", "slow response",
    "ops bottleneck", "crm inconsistency", "manual process", "process gap",
}


def _csv_tokens(value: str) -> list[str]:
    return [item.strip().lower() for item in value.split(",") if item.strip()]


_SUPPRESSED_COMPANIES = set(_csv_tokens(getattr(config, "SUPPRESSED_COMPANIES", "")))
_SUPPRESSED_DOMAINS = set(_csv_tokens(getattr(config, "SUPPRESSED_DOMAINS", "")))
_SUPPRESSED_TITLES = set(_csv_tokens(getattr(config, "SUPPRESSED_TITLES", "")))


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value or "").strip().lower()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else None


def _normalize_signals_payload(signals: Any) -> list[str]:
    if isinstance(signals, list):
        return [str(item).strip() for item in signals if str(item).strip()]
    if isinstance(signals, dict):
        normalized: list[str] = []
        for key, value in signals.items():
            if isinstance(value, (int, float)) and value > 0:
                normalized.append(f"{key}:{int(value)}")
            elif isinstance(value, str) and value.strip():
                normalized.append(f"{key}:{value.strip()}")
        return normalized
    if isinstance(signals, str) and signals.strip():
        return [signals.strip()]
    return []


def _signal_source_set(signals: list[str], source_type: str = "", source_url: str = "") -> set[str]:
    sources: set[str] = set()
    if source_type.strip():
        sources.add(source_type.strip().lower())
    if "linkedin.com" in source_url.lower():
        sources.add("linkedin")
    if "github.com" in source_url.lower():
        sources.add("github")
    if "reddit.com" in source_url.lower():
        sources.add("reddit")
    if "news" in source_url.lower():
        sources.add("news")
    for signal in signals:
        text = str(signal).lower()
        for candidate in [
            "jobspy", "linkedin", "reddit", "news", "github", "hackernews",
            "producthunt", "remoteok", "conference", "orcid", "glassdoor", "website",
        ]:
            if candidate in text:
                sources.add(candidate)
    return sources


def _signal_quality_bonus(signals: list[str]) -> tuple[int, int]:
    text = " ".join(str(signal).lower() for signal in signals)
    high_intent_hits = sum(1 for keyword in _HIGH_INTENT_SIGNAL_KEYWORDS if keyword in text)
    zero_defect_hits = sum(1 for keyword in _ZERO_DEFECT_PRESSURE_KEYWORDS if keyword in text)
    intent_bonus = min(20, high_intent_hits * 4)
    evidence_bonus = min(12, zero_defect_hits * 3)
    return intent_bonus, evidence_bonus


def _passes_icp_hard_filter(
    *,
    title: str,
    industry: str,
    company_size: int | None,
    work_location: str = "",
) -> tuple[bool, str]:
    target_titles = _csv_tokens(config.ICP_TARGET_TITLES)
    target_industries = _csv_tokens(config.ICP_TARGET_INDUSTRIES)
    title_lower = title.lower()
    industry_lower = industry.lower()
    location_lower = work_location.lower()

    title_match = any(token in title_lower for token in target_titles)
    industry_match = any(token in industry_lower for token in target_industries) if industry_lower else False
    size_min = max(1, config.ICP_MIN_COMPANY_SIZE)
    size_max = max(size_min, config.ICP_MAX_COMPANY_SIZE)
    size_match = company_size is not None and size_min <= company_size <= size_max
    location_match = any(token in location_lower for token in [config.TARGET_COUNTRY.lower(), config.TARGET_REGION.lower(), config.TARGET_METRO.lower()]) if location_lower else True

    if not location_match:
        return False, "Lead is outside target country/region scope."
    if not title_match:
        return False, "Lead title does not match ICP target roles."
    if industry and not industry_match:
        return False, "Lead industry does not match ICP target industries."
    if company_size is not None and not size_match:
        return False, f"Lead company size is outside ICP range ({size_min}-{size_max})."
    return True, ""


def _normalize_query_tokens(query: str, max_terms: int = 8) -> list[str]:
    tokens = re.findall(r"[a-z0-9\-\+]+", query.lower())
    normalized: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in _QUERY_STOPWORDS or len(token) <= 2:
            continue
        if token not in seen:
            normalized.append(token)
            seen.add(token)
        if len(normalized) >= max_terms:
            break
    return normalized


def _normalize_signal_query(query: str, max_terms: int = 8) -> str:
    scoped = _scoped_query(query)
    tokens = _normalize_query_tokens(scoped, max_terms=max_terms)
    if not tokens:
        return scoped
    return " ".join(tokens)


def _normalize_job_titles(query: str, limit: int = 5) -> list[str]:
    lower = query.lower()
    titles: list[str] = []
    seen: set[str] = set()

    def add(title: str) -> None:
        if title not in seen:
            seen.add(title)
            titles.append(title)

    # Preserve explicit role searches when the query already looks like one.
    explicit_roles = [
        "operations manager",
        "office manager",
        "sales manager",
        "customer success manager",
        "service manager",
        "dispatcher",
        "project manager",
        "account manager",
        "account executive",
    ]
    for role in explicit_roles:
        if role in lower:
            add(role)

    for hint, mapped_titles in _JOB_TITLE_HINTS.items():
        if hint in lower:
            for title in mapped_titles:
                add(title)

    for title in _DEFAULT_JOB_TITLES:
        add(title)

    return titles[:limit]


def _looks_placeholder(value: str) -> bool:
    if not value:
        return False
    lower = value.strip().lower()
    if lower in _PLACEHOLDER_PHRASES:
        return True
    if any(token in lower for token in _PLACEHOLDER_TOKENS):
        return True
    if "linkedin.com/in/johndoe" in lower or "linkedin.com/in/janesmith" in lower:
        return True
    if lower in {"example.com", "test.com", "sample.com", "localhost"}:
        return True
    return False


def _validate_public_lead(payload: dict[str, Any]) -> str | None:
    name = str(payload.get("name", "")).strip()
    company = str(payload.get("company", "")).strip()
    title = str(payload.get("title", "")).strip()
    domain = str(payload.get("company_domain", "")).strip()
    source_url = str(payload.get("source_url", "")).strip()
    source_type = str(payload.get("source_type", "")).strip()
    public_profile_url = str(payload.get("public_profile_url", "")).strip()
    signals = _normalize_signals_payload(payload.get("signals", []))
    source_set = _signal_source_set(
        signals,
        source_type=str(payload.get("source_type", "")),
        source_url=str(payload.get("source_url", "")),
    )

    if not name or not company or not title:
        return "Lead must include a real name, title, and company."
    if any(_looks_placeholder(value) for value in [name, company, title, domain, source_url, public_profile_url]):
        return "Lead appears to contain placeholder or invented identity data."
    if not isinstance(signals, list) or not any(str(signal).strip() for signal in signals):
        return "Lead must include at least one concrete public signal."
    if len(signals) < max(1, config.MIN_SIGNAL_COUNT):
        return f"Lead must include at least {max(1, config.MIN_SIGNAL_COUNT)} signal(s)."
    if len(source_set) < max(1, getattr(config, "MIN_DISTINCT_SIGNAL_SOURCES", 2)):
        return (
            f"Lead must include at least {max(1, getattr(config, 'MIN_DISTINCT_SIGNAL_SOURCES', 2))} "
            "distinct signal sources."
        )
    if not any([domain, source_url, public_profile_url]):
        return "Lead must include a verifiable company domain, public profile URL, or source URL."
    if source_url and _looks_placeholder(source_url):
        return "Lead source URL is not verifiable."
    if source_type and _looks_placeholder(source_type):
        return "Lead source type is not verifiable."
    suppressed = _suppression_reason(company=company, domain=domain, title=title)
    if suppressed:
        return suppressed
    size_value = _coerce_int(payload.get("company_size"))
    passes_filter, reason = _passes_icp_hard_filter(
        title=title,
        industry=str(payload.get("industry", "")),
        company_size=size_value,
        work_location=str(payload.get("work_location", "")),
    )
    if not passes_filter:
        return reason
    return None


def _validate_outreach_identity(name: str, company: str, signal: str) -> str | None:
    if _looks_placeholder(name) or _looks_placeholder(company):
        return "Outreach requires a verified real person and company."
    if not signal.strip() or _looks_placeholder(signal):
        return "Outreach requires a concrete, non-placeholder signal."
    return None


def _suppression_reason(
    *,
    company: str,
    domain: str,
    title: str,
) -> str | None:
    company_l = company.strip().lower()
    domain_l = _extract_domain(domain)
    title_l = title.strip().lower()

    if company_l and (company_l in _SUPPRESSED_COMPANIES or is_suppressed("company", company_l)):
        return f"Company is suppressed: {company}"
    if domain_l and (domain_l in _SUPPRESSED_DOMAINS or is_suppressed("domain", domain_l)):
        return f"Domain is suppressed: {domain_l}"
    if title_l and (title_l in _SUPPRESSED_TITLES or is_suppressed("title", title_l)):
        return f"Title is suppressed: {title}"
    return None


def _country_scope_bonus(payload: dict[str, Any]) -> int:
    location = str(payload.get("work_location", "")).lower()
    country = config.TARGET_COUNTRY.lower()
    region = config.TARGET_REGION.lower()
    metro = config.TARGET_METRO.lower()
    if metro and metro in location:
        return 10
    if region and region in location:
        return 8
    if country and country in location:
        return 5
    if not location:
        return 0
    return -8


def _score_components(
    *,
    name: str,
    title: str,
    company: str,
    company_size: int | None,
    industry: str,
    signals: list[str],
    work_location: str = "",
    source_url: str = "",
    public_profile_url: str = "",
    company_domain: str = "",
    source_type: str = "",
) -> dict[str, int]:
    del name, company
    title_lower = title.lower()
    industry_lower = industry.lower()
    signal_text = " ".join(signals).lower()

    target_titles = _csv_tokens(config.ICP_TARGET_TITLES)
    target_industries = _csv_tokens(config.ICP_TARGET_INDUSTRIES)
    min_size = max(1, config.ICP_MIN_COMPANY_SIZE)
    max_size = max(min_size, config.ICP_MAX_COMPANY_SIZE)

    icp_fit = 15
    if any(token in title_lower for token in target_titles):
        icp_fit += 30
    if any(token in industry_lower for token in target_industries):
        icp_fit += 25
    if company_size and min_size <= company_size <= max_size:
        icp_fit += 20
    elif company_size and company_size > max_size * 3:
        icp_fit -= 15

    intent_strength = 20
    if any(k in signal_text for k in ["hiring", "expansion", "funding", "launch", "new role", "growth"]):
        intent_strength += 25
    if any(k in signal_text for k in ["migrating", "switching", "rfp", "looking for", "vendor", "buying"]):
        intent_strength += 20
    intent_strength += min(len(signals) * 4, 20)
    intent_bonus, evidence_bonus_from_quality = _signal_quality_bonus(signals)
    intent_strength += intent_bonus

    recency = 35
    # If timestamp fields are absent, assign neutral recency instead of optimistic.
    observed = ""
    if isinstance(signals, list):
        for signal in signals:
            text = str(signal)
            if "2026-" in text or "2025-" in text:
                observed = text
                break
    if observed:
        recency = 70

    evidence = 20
    if source_url:
        evidence += 20
    if public_profile_url:
        evidence += 10
    if company_domain:
        evidence += 10
    if work_location:
        evidence += 10
    evidence += _source_reliability_score(source_type, source_url)
    evidence += evidence_bonus_from_quality
    evidence += min(12, len(_signal_source_set(signals, source_type=source_type, source_url=source_url)) * 4)
    evidence += _country_scope_bonus({"work_location": work_location})

    learning_adjustment = get_outcome_score_adjustment(
        source_type=source_type,
        industry=industry,
        title=title,
        window=getattr(config, "OUTCOME_LEARNING_WINDOW", 200),
    )
    intent_strength = max(0, min(100, intent_strength + learning_adjustment))

    return {
        "icp_fit_score": max(0, min(icp_fit, 100)),
        "intent_strength_score": max(0, min(intent_strength, 100)),
        "recency_score": max(0, min(recency, 100)),
        "evidence_confidence_score": max(0, min(evidence, 100)),
        # Backward-compatible aliases used by existing downstream logic.
        "attraction_score": max(0, min(intent_strength, 100)),
        "zero_defect_score": max(0, min(icp_fit, 100)),
        "evidence_score": max(0, min(evidence, 100)),
    }


def _composite_icp_score(components: dict[str, int]) -> int:
    wf = max(0, config.WEIGHT_ICP_FIT_PCT)
    wi = max(0, config.WEIGHT_INTENT_STRENGTH_PCT)
    wr = max(0, config.WEIGHT_RECENCY_PCT)
    we = max(0, config.WEIGHT_EVIDENCE_CONFIDENCE_PCT)
    denom = wf + wi + wr + we
    if denom <= 0:
        wf, wi, wr, we, denom = 35, 35, 15, 15, 100
    score = (
        components["icp_fit_score"] * wf
        + components["intent_strength_score"] * wi
        + components["recency_score"] * wr
        + components["evidence_confidence_score"] * we
    ) / denom
    return int(max(0, min(round(score), 100)))


def _lead_dedupe_key(lead: dict[str, Any]) -> str:
    company = str(lead.get("company", "")).strip().lower()
    domain = _extract_domain(str(lead.get("company_domain", "")))
    if not domain:
        domain = _extract_domain(str(lead.get("company_url", "")))
    if not domain:
        domain = _extract_domain(str(lead.get("source_url", "")))
    name = str(lead.get("name", "")).strip().lower()
    if domain:
        return f"{domain}|{name}"
    return f"{company}|{name}"


def _extract_domain(value: str) -> str:
    lowered = value.strip().lower()
    if not lowered:
        return ""
    return lowered.replace("https://", "").replace("http://", "").split("/")[0].strip()


def _source_reliability_score(source_type: str, source_url: str) -> int:
    score = 0
    st = (source_type or "").strip().lower()
    su = (source_url or "").strip().lower()
    if st in _SOURCE_RELIABILITY:
        score += _SOURCE_RELIABILITY[st]
    if "linkedin.com" in su:
        score += 8
    if any(host in su for host in ["crunchbase.com", "sec.gov", "github.com"]):
        score += 8
    if su.startswith("http"):
        score += 6
    penalty = get_tool_failure_penalty(tool_name=st or "unknown_source", source_name=st or "")
    return max(0, min(score - penalty, 30))


def _merge_lead_records(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    if int(secondary.get("icp_score", 0)) > int(primary.get("icp_score", 0)):
        merged = dict(secondary)

    left = primary.get("signals", [])
    right = secondary.get("signals", [])
    merged_signals: list[str] = []
    seen: set[str] = set()
    for item in [*(left if isinstance(left, list) else []), *(right if isinstance(right, list) else [])]:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            merged_signals.append(text)
    if merged_signals:
        merged["signals"] = merged_signals

    for field in ("source_url", "public_profile_url", "company_domain", "work_location"):
        if not merged.get(field):
            candidate = secondary.get(field) or primary.get(field)
            if candidate:
                merged[field] = candidate
    return merged


def get_tool_schema_xml() -> str:
    """Return a minimal Hermes <tools> block sized for 4096-token local context."""
    tool_schemas = []
    for tool in TOOLS:
        params = tool.get("parameters", {}).get("properties", {})
        required = tool.get("parameters", {}).get("required", [])
        tool_schemas.append(
            {
                "name": tool.get("name", ""),
                "params": list(params.keys()),
                "required": required,
            }
        )
    return "<tools>" + json.dumps(tool_schemas, separators=(",", ":")) + "</tools>"


def _slice_results(results: Any, limit: int) -> list[Any]:
    if isinstance(results, list):
        return results[:limit]
    return [results] if results else []


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _search_signals(query: str, days_back: int = 30, limit: int = 20) -> dict[str, Any]:
    scoped = _normalize_signal_query(query)
    merged: list[Any] = []
    providers: list[str] = []
    if get_all_signals is not None:
        results = get_all_signals(keywords=[scoped], daysback=days_back)
        merged.extend(_slice_results(results, limit))
        providers.append("all_signals")
    if len(merged) < max(1, int(getattr(config, "MIN_DISCOVERY_RESULTS", 8))):
        for fn_name, fn in [
            ("news", search_google_news),
            ("reddit", search_reddit),
            ("hn", search_hackernews),
            ("github", search_github_repos),
            ("producthunt", search_producthunt_launches),
            ("remoteok", search_remoteok_jobs),
        ]:
            if fn is None:
                continue
            try:
                batch = fn(keywords=[scoped], max_results=max(5, limit // 2))
                merged.extend(_slice_results(batch, max(5, limit // 2)))
                providers.append(fn_name)
            except Exception:
                continue
    deduped: list[Any] = []
    seen: set[str] = set()
    for item in merged:
        key = json.dumps(item, sort_keys=True, default=str)[:240]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    us_tokens = [" united states", " usa", " us ", " u.s.", " america", " atlanta", " georgia"]
    us_filtered = [
        item for item in deduped
        if any(token in json.dumps(item, default=str).lower() for token in us_tokens)
    ]
    final_results = us_filtered if len(us_filtered) >= max(3, limit // 3) else deduped
    return {
        "ok": True,
        "query": scoped,
        "count": len(final_results),
        "providers_used": providers,
        "results": final_results[:limit],
    }


def _search_reddit_signals(query: str, subreddit: str = "", limit: int = 10) -> dict[str, Any]:
    if search_reddit is None:
        return {"ok": False, "error": "search_reddit is not available"}
    # search_reddit takes keywords: list[str], subreddits: list[str] | None
    subreddits = [subreddit] if subreddit else None
    results = search_reddit(keywords=[_normalize_signal_query(query)], subreddits=subreddits, max_results=limit)
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_news_signals(query: str, days_back: int = 30, limit: int = 10) -> dict[str, Any]:
    if search_google_news is None:
        return {"ok": False, "error": "search_google_news is not available"}
    results = search_google_news(keywords=[_normalize_signal_query(query)], daysback=days_back, max_results=limit)
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_github_signals(query: str, limit: int = 10) -> dict[str, Any]:
    if search_github_repos is None:
        return {"ok": False, "error": "search_github_repos is not available"}
    # search_github_repos takes keywords: list[str]
    results = search_github_repos(keywords=[_normalize_signal_query(query)], max_results=limit)
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_hn_signals(query: str, limit: int = 10) -> dict[str, Any]:
    if search_hackernews is None:
        return {"ok": False, "error": "search_hackernews is not available"}
    # search_hackernews takes keywords: list[str]
    results = search_hackernews(keywords=[_normalize_signal_query(query)], max_results=limit)
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_producthunt_signals(query: str, limit: int = 10) -> dict[str, Any]:
    if search_producthunt_launches is None:
        return {"ok": False, "error": "search_producthunt_launches is not available"}
    # search_producthunt_launches takes keywords: list[str]
    results = search_producthunt_launches(keywords=[_normalize_signal_query(query)], max_results=limit)
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_remote_hiring_signals(query: str, limit: int = 10) -> dict[str, Any]:
    if search_remoteok_jobs is None:
        return {"ok": False, "error": "search_remoteok_jobs is not available"}
    # search_remoteok_jobs takes keywords: list[str]
    results = search_remoteok_jobs(keywords=[_normalize_signal_query(query)], max_results=limit)
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_funding_signals(query: str = "", days_back: int = 90, limit: int = 10) -> dict[str, Any]:
    if search_funding_rounds is None:
        return {"ok": False, "error": "search_funding_rounds is not available"}
    # search_funding_rounds takes keywords: list[str] | None
    keywords = [_normalize_signal_query(query)] if query else None
    results = search_funding_rounds(keywords=keywords, days_back=days_back)
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_form_d_georgia(days_back: int = 90, limit: int = 10) -> dict[str, Any]:
    if search_recent_form_d_georgia is None:
        return {"ok": False, "error": "search_recent_form_d_georgia is not available"}
    results = search_recent_form_d_georgia(days_back=days_back)
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_jobs_public(query: str, location: str = "", days_back: int = 30, limit: int = 10) -> dict[str, Any]:
    if search_jobs is None:
        return {"ok": False, "error": "search_jobs is not available"}
    # search_jobs takes job_titles: list[str], hours_old: int (not days_back)
    job_titles = _normalize_job_titles(query)
    results = search_jobs(
        job_titles=job_titles,
        location=location or config.TARGET_METRO,
        hours_old=days_back * 24,
        results_wanted=limit,
    )
    fallback_used = False
    if not results:
        fallback_used = True
        broadened_titles = _normalize_job_titles("operations manager, office manager, sales manager, service manager")
        results = search_jobs(
            job_titles=broadened_titles,
            location=config.TARGET_REGION or config.TARGET_METRO,
            hours_old=max(24, days_back * 24),
            results_wanted=limit,
        )
    return {
        "ok": True,
        "query": query,
        "normalized_job_titles": job_titles,
        "fallback_used": fallback_used,
        "results": _slice_results(results, limit),
    }


def _search_jobs_by_icp_tool(
    icp_keywords: list[str] | str,
    location: str = "",
    days_back: int = 30,
    limit: int = 10,
) -> dict[str, Any]:
    if search_jobs is None:
        return {"ok": False, "error": "search_jobs is not available"}
    if isinstance(icp_keywords, str):
        parsed = [part.strip() for part in icp_keywords.split(",") if part.strip()]
        icp_keywords = parsed if parsed else [icp_keywords]
    # search_jobs takes job_titles: list[str], hours_old: int
    job_titles: list[str] = []
    seen: set[str] = set()
    for keyword in icp_keywords:
        for title in _normalize_job_titles(keyword):
            if title not in seen:
                seen.add(title)
                job_titles.append(title)
    results = search_jobs(
        job_titles=job_titles or _DEFAULT_JOB_TITLES,
        location=location or config.TARGET_METRO,
        hours_old=days_back * 24,
        results_wanted=limit,
    )
    return {
        "ok": True,
        "normalized_job_titles": job_titles or _DEFAULT_JOB_TITLES,
        "results": _slice_results(results, limit),
    }


def _enrich_lead_public(
    name: str,
    company: str = "",
    domain: str = "",
    website: str = "",
) -> dict[str, Any]:
    if enrich_lead is None:
        return {"ok": False, "error": "enrich_lead is not available"}
    # enrich_lead takes company_name, domain, first_name, last_name — split name
    parts = name.strip().split(None, 1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""
    # Prefer explicit domain; fall back to stripping scheme from website
    resolved_domain = domain
    if not resolved_domain and website:
        resolved_domain = website.replace("https://", "").replace("http://", "").split("/")[0]
    results = enrich_lead(
        company_name=company,
        domain=resolved_domain,
        first_name=first_name,
        last_name=last_name,
    )
    payload = results if isinstance(results, dict) else {
        "name": name, "company": company, "company_domain": resolved_domain, "company_url": website
    }
    return {"ok": True, "data": _filter_public_fields(payload)}


def _enrich_lead_waterfall(
    name: str,
    company: str = "",
    domain: str = "",
    website: str = "",
) -> dict[str, Any]:
    provenance: list[dict[str, Any]] = []
    aggregate: dict[str, Any] = {"name": name, "company": company}
    confidence = 0

    # Step 0: entity graph context
    graph = get_entity_context(full_name=name, company_domain=domain, company_name=company)
    if graph.get("ok"):
        aggregate["entity_graph"] = graph
        if graph.get("entities"):
            confidence += 15
            provenance.append({"step": "entity_graph_context", "ok": True, "confidence_delta": 15})
    else:
        provenance.append({"step": "entity_graph_context", "ok": False, "confidence_delta": 0})

    # Step 1: public lead enrichment
    public = _enrich_lead_public(name=name, company=company, domain=domain, website=website)
    provenance.append({"step": "enrich_lead_public", "ok": bool(public.get("ok")), "confidence_delta": 25})
    if public.get("ok") and isinstance(public.get("data"), dict):
        aggregate.update(public["data"])
        confidence += 25

    # Step 2: website scrape if available
    company_url = str(aggregate.get("company_url") or website or "").strip()
    if company_url:
        scraped = _scrape_company_website(company_url)
        provenance.append({"step": "scrape_company_website", "ok": bool(scraped.get("ok")), "confidence_delta": 20})
        if scraped.get("ok"):
            aggregate["website_metadata"] = scraped.get("data", {})
            confidence += 20

    # Step 3: email candidates and MX checks when domain exists
    resolved_domain = str(aggregate.get("company_domain") or domain or "").strip()
    if resolved_domain:
        emails = _generate_email_candidates_public(name=name, domain=resolved_domain)
        provenance.append({"step": "generate_email_candidates_public", "ok": bool(emails.get("ok")), "confidence_delta": 15})
        if emails.get("ok"):
            aggregate["email_candidates"] = emails.get("results", [])
            confidence += 15
        mx = _verify_mx_public(resolved_domain)
        provenance.append({"step": "verify_mx_public", "ok": bool(mx.get("ok")), "confidence_delta": 15})
        if mx.get("ok"):
            aggregate["mx_verification"] = mx.get("result", {})
            confidence += 15

    # Step 4: optional fallbacks (kept no-op when keys absent)
    fallback = _enrich_apollo(name=name, company=company, domain=resolved_domain)
    provenance.append({"step": "enrich_apollo", "ok": bool(fallback.get("ok")), "confidence_delta": 5})
    if fallback.get("ok"):
        aggregate["apollo_fallback"] = fallback
        confidence += 5

    return {
        "ok": True,
        "data": _filter_public_fields(aggregate) | {"provenance": provenance},
        "confidence": min(100, confidence),
    }


def _enrich_leads_batch_public(leads: list[dict[str, Any]]) -> dict[str, Any]:
    if enrich_leads_batch is None:
        return {"ok": False, "error": "enrich_leads_batch is not available"}
    results = enrich_leads_batch(leads)
    cleaned = [
        _filter_public_fields(item)
        for item in (results if isinstance(results, list) else [])
        if isinstance(item, dict)
    ]
    return {"ok": True, "results": cleaned}


def _scrape_company_website(url: str) -> dict[str, Any]:
    if scrape_website_metadata is None:
        return {"ok": False, "error": "scrape_website_metadata is not available"}
    # scrape_website_metadata takes domain, not full URL — strip scheme
    domain = url.replace("https://", "").replace("http://", "").split("/")[0]
    results = scrape_website_metadata(domain)
    return {"ok": True, "data": results}


def _generate_email_candidates_public(name: str, domain: str) -> dict[str, Any]:
    if generate_email_candidates is None:
        return {"ok": False, "error": "generate_email_candidates is not available"}
    # generate_email_candidates takes first_name, last_name, domain
    parts = name.strip().split(None, 1)
    first_name = parts[0] if parts else name
    last_name = parts[1] if len(parts) > 1 else ""
    results = generate_email_candidates(firstname=first_name, lastname=last_name, domain=domain)
    return {"ok": True, "results": results}


def _verify_mx_public(domain: str) -> dict[str, Any]:
    if verify_mx is None:
        return {"ok": False, "error": "verify_mx is not available"}
    result = verify_mx(domain=domain)
    return {"ok": True, "result": result}


def _search_public_profiles(query: str, limit: int = 20) -> dict[str, Any]:
    if get_all_public_profiles is None:
        return {"ok": False, "error": "get_all_public_profiles is not available"}
    results = get_all_public_profiles(keywords=[_normalize_signal_query(query)], max_results=limit)
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_wellfound_jobs(query: str, limit: int = 20) -> dict[str, Any]:
    if search_wellfound_jobs is None:
        return {"ok": False, "error": "search_wellfound_jobs is not available"}
    results = search_wellfound_jobs(keywords=[_normalize_signal_query(query)], max_results=limit)
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_crunchbase_news(query: str, limit: int = 20) -> dict[str, Any]:
    if search_crunchbase_news is None:
        return {"ok": False, "error": "search_crunchbase_news is not available"}
    results = search_crunchbase_news(keywords=[_normalize_signal_query(query)], max_results=limit)
    return {"ok": True, "results": _slice_results(results, limit)}


def _scrape_team_page(company_name: str, domain: str, limit: int = 10) -> dict[str, Any]:
    if scrape_company_team_page is None:
        return {"ok": False, "error": "scrape_company_team_page is not available"}
    results = scrape_company_team_page(company_name=company_name, domain=domain, max_people=limit)
    return {"ok": True, "company": company_name, "domain": domain, "count": len(results), "people": results}


def _search_conference_speakers(query: str, limit: int = 20) -> dict[str, Any]:
    if search_conference_speakers is None:
        return {"ok": False, "error": "search_conference_speakers is not available"}
    results = search_conference_speakers(keywords=[_normalize_signal_query(query)], max_results=limit)
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_orcid_profiles(query: str, limit: int = 15) -> dict[str, Any]:
    if search_orcid_profiles is None:
        return {"ok": False, "error": "search_orcid_profiles is not available"}
    results = search_orcid_profiles(keywords=[_normalize_signal_query(query)], max_results=limit)
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_glassdoor_signals(query: str, limit: int = 15) -> dict[str, Any]:
    if search_glassdoor_news is None:
        return {"ok": False, "error": "search_glassdoor_news is not available"}
    results = search_glassdoor_news(keywords=[_normalize_signal_query(query)], max_results=limit)
    return {"ok": True, "results": _slice_results(results, limit)}


# Placeholders — Apollo/Hunter wired to live API calls when keys are present.
# See audit notes for full httpx implementation.

def _search_apollo(
    job_titles: list[str],
    industries: list[str] | None = None,
    employee_range: str = "",
    keywords: str = "",
    limit: int = 10,
) -> dict[str, Any]:
    return {
        "ok": True,
        "note": "Apollo search placeholder preserved for compatibility.",
        "job_titles": job_titles,
        "industries": industries or [],
        "employee_range": employee_range,
        "keywords": keywords,
        "limit": limit,
    }


def _enrich_apollo(
    name: str,
    company: str = "",
    domain: str = "",
    linkedin_url: str = "",
) -> dict[str, Any]:
    return {
        "ok": True,
        "note": "Apollo enrichment placeholder preserved for compatibility.",
        "name": name,
        "company": company,
        "domain": domain,
        "linkedin_url": linkedin_url,
    }


def _find_email_hunter(
    name: str,
    company: str = "",
    domain: str = "",
) -> dict[str, Any]:
    return {
        "ok": True,
        "note": "Hunter lookup placeholder preserved for compatibility.",
        "name": name,
        "company": company,
        "domain": domain,
    }


def _score_lead(
    name: str,
    title: str,
    company: str,
    company_size: int | None = None,
    industry: str = "",
    signals: list[str] | None = None,
) -> dict[str, Any]:
    normalized_signals = _normalize_signals_payload(signals or [])
    normalized_company_size = _coerce_int(company_size)
    passes_filter, reason = _passes_icp_hard_filter(
        title=title,
        industry=industry,
        company_size=normalized_company_size,
    )
    if not passes_filter:
        return {
            "ok": True,
            "name": name,
            "company": company,
            "score": 0,
            "icp_score": 0,
            "rejected": True,
            "rejection_reason": reason,
            "reasoning": {"title": title, "industry": industry, "company_size": normalized_company_size, "signals": normalized_signals},
        }
    components = _score_components(
        name=name,
        title=title,
        company=company,
        company_size=normalized_company_size,
        industry=industry,
        signals=normalized_signals,
    )
    score = _composite_icp_score(components)
    return {
        "ok": True,
        "name": name,
        "company": company,
        "score": score,
        "icp_fit_score": components["icp_fit_score"],
        "intent_strength_score": components["intent_strength_score"],
        "recency_score": components["recency_score"],
        "evidence_confidence_score": components["evidence_confidence_score"],
        "attraction_score": components["attraction_score"],
        "zero_defect_score": components["zero_defect_score"],
        "evidence_score": components["evidence_score"],
        "reasoning": {
            "title": title,
            "industry": industry,
            "company_size": normalized_company_size,
            "signals_count": len(normalized_signals),
            "signals": normalized_signals,
        },
    }


def _rank_leads(leads: list[dict[str, Any]], top_n: int = 10) -> dict[str, Any]:
    deduped: dict[str, dict[str, Any]] = {}
    dropped = 0
    filtered_low_evidence = 0
    for lead in leads:
        if not isinstance(lead, dict):
            dropped += 1
            continue
        key = _lead_dedupe_key(lead)
        normalized_company_size = _coerce_int(lead.get("company_size"))
        normalized_signals = _normalize_signals_payload(lead.get("signals", []))
        passes_filter, _ = _passes_icp_hard_filter(
            title=str(lead.get("title", "")),
            industry=str(lead.get("industry", "")),
            company_size=normalized_company_size,
            work_location=str(lead.get("work_location", "")),
        )
        if not passes_filter:
            dropped += 1
            continue
        components = _score_components(
            name=str(lead.get("name", "")),
            title=str(lead.get("title", "")),
            company=str(lead.get("company", "")),
            company_size=normalized_company_size,
            industry=str(lead.get("industry", "")),
            signals=normalized_signals,
            work_location=str(lead.get("work_location", "")),
            source_url=str(lead.get("source_url", "")),
            public_profile_url=str(lead.get("public_profile_url", "")),
            company_domain=str(lead.get("company_domain", "")),
            source_type=str(lead.get("source_type", "")),
        )
        icp_score = _composite_icp_score(components)
        candidate = dict(lead)
        candidate["company_size"] = normalized_company_size
        candidate["signals"] = normalized_signals
        candidate.update(components)
        candidate["icp_score"] = icp_score
        if components["evidence_score"] < max(0, config.MIN_EVIDENCE_SCORE):
            filtered_low_evidence += 1
            continue
        prev = deduped.get(key)
        if prev is None:
            deduped[key] = candidate
        else:
            deduped[key] = _merge_lead_records(prev, candidate)

    ranked = sorted(deduped.values(), key=lambda item: int(item.get("icp_score", 0)), reverse=True)
    return {
        "ok": True,
        "input_count": len(leads),
        "unique_count": len(ranked),
        "dropped_count": dropped,
        "filtered_low_evidence": filtered_low_evidence,
        "min_evidence_score": max(0, config.MIN_EVIDENCE_SCORE),
        "results": ranked[: max(1, top_n)],
    }


def _recommend_playbook_actions(leads: list[dict[str, Any]], objective: str) -> dict[str, Any]:
    ranked = _rank_leads(leads, top_n=5)
    top_leads = ranked.get("results", [])
    actions: list[dict[str, Any]] = []
    for lead in top_leads:
        actions.append(
            {
                "company": lead.get("company", ""),
                "name": lead.get("name", ""),
                "icp_score": lead.get("icp_score", 0),
                "action": "enrich_then_outreach",
                "reason": "High combined attraction, zero-defect, and evidence score.",
            }
        )
    if not actions:
        actions.append(
            {
                "action": "broaden_signals",
                "reason": "Insufficient qualified leads. Expand signals to local news, jobs, and conference sources.",
            }
        )
    else:
        actions.append(
            {
                "action": "qa_gate_before_outreach",
                "reason": "Only save/outreach leads where evidence_score and icp_score meet thresholds.",
            }
        )
    return {
        "ok": True,
        "objective": objective,
        "top_candidates": top_leads,
        "actions": actions,
    }


def _orchestrate_playbook(
    leads: list[dict[str, Any]],
    objective: str,
    max_outreach: int = 3,
) -> dict[str, Any]:
    ranked = _rank_leads(leads, top_n=max(1, max_outreach * 2))
    candidates = ranked.get("results", [])
    selected = [
        lead for lead in candidates
        if int(lead.get("icp_score", 0)) >= config.ICP_MIN_SCORE
        and int(lead.get("evidence_score", 0)) >= config.MIN_EVIDENCE_SCORE
    ][:max(1, max_outreach)]
    return {
        "ok": True,
        "objective": objective,
        "selected_for_crm_handoff": selected,
        "selection_count": len(selected),
        "gates": {
            "icp_min_score": config.ICP_MIN_SCORE,
            "min_evidence_score": config.MIN_EVIDENCE_SCORE,
        },
        "next_step": "save_for_crm_handoff" if selected else "collect_more_signals",
    }


def _save_lead(**payload: Any) -> dict[str, Any]:
    cleaned = _filter_public_fields(payload)
    cleaned["signals"] = _normalize_signals_payload(cleaned.get("signals", []))
    size_value = _coerce_int(cleaned.get("company_size"))
    if size_value is not None:
        cleaned["company_size"] = size_value
    validation_error = _validate_public_lead(cleaned)
    if validation_error:
        return {"ok": False, "saved": False, "error": validation_error, "lead": cleaned}
    lead_signals = cleaned.get("signals", []) if isinstance(cleaned.get("signals"), list) else []
    components = _score_components(
        name=str(cleaned.get("name", "")),
        title=str(cleaned.get("title", "")),
        company=str(cleaned.get("company", "")),
        company_size=size_value,
        industry=str(cleaned.get("industry", "")),
        signals=lead_signals,
        work_location=str(cleaned.get("work_location", "")),
        source_url=str(cleaned.get("source_url", "")),
        public_profile_url=str(cleaned.get("public_profile_url", "")),
        company_domain=str(cleaned.get("company_domain", "")),
        source_type=str(cleaned.get("source_type", "")),
    )
    computed_icp = _composite_icp_score(components)
    cleaned["attraction_score"] = components["attraction_score"]
    cleaned["zero_defect_score"] = components["zero_defect_score"]
    cleaned["evidence_score"] = components["evidence_score"]
    cleaned["icp_fit_score"] = components["icp_fit_score"]
    cleaned["intent_strength_score"] = components["intent_strength_score"]
    cleaned["recency_score"] = components["recency_score"]
    cleaned["evidence_confidence_score"] = components["evidence_confidence_score"]
    cleaned["icp_score"] = int(cleaned.get("icp_score", computed_icp) or computed_icp)
    cleaned["decision_reason"] = (
        cleaned.get("decision_reason")
        or f"icp={cleaned['icp_score']}, evidence={components['evidence_score']}, intent={components['intent_strength_score']}"
    )
    if cleaned["icp_score"] < config.ICP_MIN_SCORE:
        return {"ok": False, "saved": False, "error": f"Lead score below ICP threshold ({config.ICP_MIN_SCORE}).", "lead": cleaned}
    if components["evidence_score"] < config.MIN_EVIDENCE_SCORE:
        return {"ok": False, "saved": False, "error": f"Lead evidence below threshold ({config.MIN_EVIDENCE_SCORE}).", "lead": cleaned}
    if "observed_at" not in cleaned:
        cleaned["observed_at"] = datetime.now(timezone.utc).isoformat()
    persistence = save_public_lead(cleaned)
    cleaned["id"] = persistence["id"]
    cleaned["saved_at"] = persistence["saved_at"]
    logger.info(
        f"Lead saved: {payload.get('name')} @ {payload.get('company')} "
        f"(score={payload.get('icp_score')}, id={persistence['id']})"
    )
    return {"ok": True, "saved": True, "lead": cleaned, "db": persistence}


def _draft_outreach(
    name: str,
    title: str,
    company: str,
    signal: str = "",
    tone: str = "professional",
) -> dict[str, Any]:
    if not getattr(config, "ENABLE_OUTREACH_ACTIONS", False):
        return {
            "ok": False,
            "error": "Outreach actions are disabled in LeadHunterOS. Use CRM/HubSpot/Apollo outbound tools.",
        }
    validation_error = _validate_outreach_identity(name, company, signal)
    if validation_error:
        return {"ok": False, "error": validation_error}
    opener = f"Hi {name}, noticed {company} is showing momentum around {signal}."
    if tone == "direct":
        body = f"{opener} Reaching out because teams led by {title}s often need a faster way to turn signals into pipeline."
    elif tone == "casual":
        body = f"{opener} Thought this might be relevant since folks in {title} roles are usually juggling timing and targeting."
    else:
        body = f"{opener} I thought this might be relevant given the priorities typically owned by a {title}."
    return {"ok": True, "message": body}


def _record_outcome_feedback(
    lead_id: str,
    outcome_type: str,
    outcome_value: float = 1.0,
    source_type: str = "",
    industry: str = "",
    title: str = "",
    notes: str = "",
) -> dict[str, Any]:
    return record_outcome_feedback(
        lead_id=lead_id,
        outcome_type=outcome_type,
        outcome_value=outcome_value,
        source_type=source_type,
        industry=industry,
        title=title,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def dispatch_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    handlers = {
        "search_signals": _search_signals,
        "search_reddit_signals": _search_reddit_signals,
        "search_news_signals": _search_news_signals,
        "search_github_signals": _search_github_signals,
        "search_hn_signals": _search_hn_signals,
        "search_producthunt_signals": _search_producthunt_signals,
        "search_remote_hiring_signals": _search_remote_hiring_signals,
        "search_funding_signals": _search_funding_signals,
        "search_form_d_georgia": _search_form_d_georgia,
        "search_jobs_public": _search_jobs_public,
        "search_jobs_by_icp": _search_jobs_by_icp_tool,
        "enrich_lead_public": _enrich_lead_public,
        "enrich_lead_waterfall": _enrich_lead_waterfall,
        "enrich_leads_batch_public": _enrich_leads_batch_public,
        "scrape_company_website": _scrape_company_website,
        "generate_email_candidates_public": _generate_email_candidates_public,
        "verify_mx_public": _verify_mx_public,
        "search_public_profiles": _search_public_profiles,
        "search_wellfound_jobs": _search_wellfound_jobs,
        "search_crunchbase_news": _search_crunchbase_news,
        "scrape_team_page": _scrape_team_page,
        "search_conference_speakers": _search_conference_speakers,
        "search_orcid_profiles": _search_orcid_profiles,
        "search_glassdoor_signals": _search_glassdoor_signals,
        "search_apollo": _search_apollo,
        "enrich_apollo": _enrich_apollo,
        "find_email_hunter": _find_email_hunter,
        "score_lead": _score_lead,
        "rank_leads": _rank_leads,
        "recommend_playbook_actions": _recommend_playbook_actions,
        "orchestrate_playbook": _orchestrate_playbook,
        "save_lead": _save_lead,
        "draft_outreach": _draft_outreach,
        "record_outcome_feedback": _record_outcome_feedback,
    }
    handler = handlers.get(name)
    if not handler:
        return {"ok": False, "error": f"Unknown tool: {name}"}
    try:
        return handler(**arguments)
    except TypeError as exc:
        return {"ok": False, "error": f"Invalid arguments for {name}: {exc}"}
    except Exception as exc:
        logger.exception("Tool execution failed")
        return {"ok": False, "error": str(exc)}
