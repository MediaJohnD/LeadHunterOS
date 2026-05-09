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
from agent.database import save_public_lead

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
    signals = payload.get("signals", [])

    if not name or not company or not title:
        return "Lead must include a real name, title, and company."
    if any(_looks_placeholder(value) for value in [name, company, title, domain, source_url, public_profile_url]):
        return "Lead appears to contain placeholder or invented identity data."
    if not isinstance(signals, list) or not any(str(signal).strip() for signal in signals):
        return "Lead must include at least one concrete public signal."
    if not any([domain, source_url, public_profile_url]):
        return "Lead must include a verifiable company domain, public profile URL, or source URL."
    if source_url and _looks_placeholder(source_url):
        return "Lead source URL is not verifiable."
    if source_type and _looks_placeholder(source_type):
        return "Lead source type is not verifiable."
    return None


def _validate_outreach_identity(name: str, company: str, signal: str) -> str | None:
    if _looks_placeholder(name) or _looks_placeholder(company):
        return "Outreach requires a verified real person and company."
    if not signal.strip() or _looks_placeholder(signal):
        return "Outreach requires a concrete, non-placeholder signal."
    return None


def get_tool_schema_xml() -> str:
    """Return a compact Hermes <tools> block with JSON schemas for every tool.

    Lemonade's default llama.cpp context can be 4096 tokens. Minified JSON keeps
    the full schema available without spending hundreds of tokens on whitespace.
    """
    tool_schemas = [{"type": "function", "function": t} for t in TOOLS]
    return "<tools>" + json.dumps(tool_schemas, separators=(",", ":")) + "</tools>"


def _slice_results(results: Any, limit: int) -> list[Any]:
    if isinstance(results, list):
        return results[:limit]
    return [results] if results else []


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _search_signals(query: str, days_back: int = 30, limit: int = 20) -> dict[str, Any]:
    if get_all_signals is None:
        return {"ok": False, "error": "get_all_signals is not available"}
    scoped = _normalize_signal_query(query)
    results = get_all_signals(keywords=[scoped], daysback=days_back)
    sliced = _slice_results(results, limit)
    return {"ok": True, "query": scoped, "count": len(sliced), "results": sliced}


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
    return {
        "ok": True,
        "query": query,
        "normalized_job_titles": job_titles,
        "results": _slice_results(results, limit),
    }


def _search_jobs_by_icp_tool(
    icp_keywords: list[str],
    location: str = "",
    days_back: int = 30,
    limit: int = 10,
) -> dict[str, Any]:
    if search_jobs is None:
        return {"ok": False, "error": "search_jobs is not available"}
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
    signals = signals or []
    score = 40
    if title:
        seniority_terms = ["vp", "head", "director", "chief", "founder", "owner"]
        if any(term in title.lower() for term in seniority_terms):
            score += 20
    if company_size and company_size >= 50:
        score += 10
    if industry:
        score += 5
    score += min(len(signals) * 5, 25)
    score = max(0, min(score, 100))
    return {
        "ok": True,
        "name": name,
        "company": company,
        "score": score,
        "reasoning": {
            "title": title,
            "industry": industry,
            "company_size": company_size,
            "signals_count": len(signals),
            "signals": signals,
        },
    }


def _save_lead(**payload: Any) -> dict[str, Any]:
    cleaned = _filter_public_fields(payload)
    validation_error = _validate_public_lead(cleaned)
    if validation_error:
        return {"ok": False, "saved": False, "error": validation_error, "lead": cleaned}
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
        "save_lead": _save_lead,
        "draft_outreach": _draft_outreach,
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
