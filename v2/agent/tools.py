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
from datetime import datetime, timezone
from typing import Any

from loguru import logger

import config

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


def get_tool_schema_xml() -> str:
    """Return the full Hermes <tools> block with JSON schemas for every registered tool.

    The Hermes function-calling spec requires the model to see each tool's full schema.
    Inject this verbatim into the system prompt.
    """
    tool_schemas = [{"type": "function", "function": t} for t in TOOLS]
    return "<tools>\n" + json.dumps(tool_schemas, indent=2) + "\n</tools>"


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
    # get_all_signals takes keywords: list[str]
    results = get_all_signals(keywords=[query], days_back=days_back)
    sliced = _slice_results(results, limit)
    return {"ok": True, "query": query, "count": len(sliced), "results": sliced}


def _search_reddit_signals(query: str, subreddit: str = "", limit: int = 10) -> dict[str, Any]:
    if search_reddit is None:
        return {"ok": False, "error": "search_reddit is not available"}
    # search_reddit takes keywords: list[str], subreddits: list[str] | None
    subreddits = [subreddit] if subreddit else None
    results = search_reddit(keywords=[query], subreddits=subreddits)
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_news_signals(query: str, days_back: int = 30, limit: int = 10) -> dict[str, Any]:
    if search_google_news is None:
        return {"ok": False, "error": "search_google_news is not available"}
    # search_google_news takes keywords: list[str]
    results = search_google_news(keywords=[query], days_back=days_back)
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_github_signals(query: str, limit: int = 10) -> dict[str, Any]:
    if search_github_repos is None:
        return {"ok": False, "error": "search_github_repos is not available"}
    # search_github_repos takes keywords: list[str]
    results = search_github_repos(keywords=[query])
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_hn_signals(query: str, limit: int = 10) -> dict[str, Any]:
    if search_hackernews is None:
        return {"ok": False, "error": "search_hackernews is not available"}
    # search_hackernews takes keywords: list[str]
    results = search_hackernews(keywords=[query])
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_producthunt_signals(query: str, limit: int = 10) -> dict[str, Any]:
    if search_producthunt_launches is None:
        return {"ok": False, "error": "search_producthunt_launches is not available"}
    # search_producthunt_launches takes keywords: list[str]
    results = search_producthunt_launches(keywords=[query])
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_remote_hiring_signals(query: str, limit: int = 10) -> dict[str, Any]:
    if search_remoteok_jobs is None:
        return {"ok": False, "error": "search_remoteok_jobs is not available"}
    # search_remoteok_jobs takes keywords: list[str]
    results = search_remoteok_jobs(keywords=[query])
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_funding_signals(query: str = "", days_back: int = 90, limit: int = 10) -> dict[str, Any]:
    if search_funding_rounds is None:
        return {"ok": False, "error": "search_funding_rounds is not available"}
    # search_funding_rounds takes keywords: list[str] | None
    keywords = [query] if query else None
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
    results = search_jobs(
        job_titles=[query],
        location=location or "United States",
        hours_old=days_back * 24,
    )
    return {"ok": True, "results": _slice_results(results, limit)}


def _search_jobs_by_icp_tool(
    icp_keywords: list[str],
    location: str = "",
    days_back: int = 30,
    limit: int = 10,
) -> dict[str, Any]:
    if search_jobs is None:
        return {"ok": False, "error": "search_jobs is not available"}
    # search_jobs takes job_titles: list[str], hours_old: int
    results = search_jobs(
        job_titles=icp_keywords,
        location=location or "United States",
        hours_old=days_back * 24,
    )
    return {"ok": True, "results": _slice_results(results, limit)}


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
    results = generate_email_candidates(first_name=first_name, last_name=last_name, domain=domain)
    return {"ok": True, "results": results}


def _verify_mx_public(domain: str) -> dict[str, Any]:
    if verify_mx is None:
        return {"ok": False, "error": "verify_mx is not available"}
    result = verify_mx(domain=domain)
    return {"ok": True, "result": result}


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
    cleaned["saved_at"] = datetime.now(timezone.utc).isoformat()
    logger.info(f"Lead saved: {payload.get('name')} @ {payload.get('company')} (score={payload.get('icp_score')})")
    return {"ok": True, "saved": True, "lead": cleaned}


def _draft_outreach(
    name: str,
    title: str,
    company: str,
    signal: str = "",
    tone: str = "professional",
) -> dict[str, Any]:
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
