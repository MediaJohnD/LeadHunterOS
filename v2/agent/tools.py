"""LeadHunterOS v2 - Tool definitions for the Hermes agent.

All tools use US-based APIs only:
  - Apollo.io (lead search & enrichment)
  - Hunter.io (email finder)
  - NewsAPI (news signals)
  - Reddit via PRAW (social signals)
  - PostgreSQL (local database writes)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx
from loguru import logger

import config


# ---------------------------------------------------------------------------
# Tool registry - each tool MUST have name, description, and parameters
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "name": "search_apollo",
        "description": "Search Apollo.io for leads by job title, industry, company size, and keywords. Returns a list of matching contacts.",
        "parameters": {
            "type": "object",
            "properties": {
                "job_titles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Job titles to search for, e.g. ['VP of Sales', 'CRO', 'Head of Revenue']"
                },
                "industries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Industries to filter by, e.g. ['SaaS', 'Software']"
                },
                "employee_range": {
                    "type": "string",
                    "description": "Company size range, e.g. '10,500'"
                },
                "keywords": {
                    "type": "string",
                    "description": "Additional search keywords"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 10)"
                }
            },
            "required": ["job_titles"]
        }
    },
    {
        "name": "enrich_apollo",
        "description": "Enrich a lead's contact and company data using Apollo.io. Returns email, phone, LinkedIn, company details.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Full name of the person"
                },
                "company": {
                    "type": "string",
                    "description": "Company name"
                },
                "domain": {
                    "type": "string",
                    "description": "Company domain, e.g. acme.com"
                },
                "linkedin_url": {
                    "type": "string",
                    "description": "LinkedIn profile URL if known"
                }
            },
            "required": ["name"]
        }
    },
    {
        "name": "find_email_hunter",
        "description": "Find a verified email address for a person at a company using Hunter.io.",
        "parameters": {
            "type": "object",
            "properties": {
                "first_name": {
                    "type": "string",
                    "description": "Person's first name"
                },
                "last_name": {
                    "type": "string",
                    "description": "Person's last name"
                },
                "domain": {
                    "type": "string",
                    "description": "Company domain, e.g. acme.com"
                }
            },
            "required": ["first_name", "last_name", "domain"]
        }
    },
    {
        "name": "search_news",
        "description": "Search recent news for a company or topic using NewsAPI. Returns headlines and summaries as buying signals.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query, e.g. company name or topic"
                },
                "days_back": {
                    "type": "integer",
                    "description": "How many days back to search (default 30)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_reddit",
        "description": "Search Reddit for discussions about a company, product, or pain point. Returns relevant posts and comments as buying signals.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "subreddit": {
                    "type": "string",
                    "description": "Specific subreddit to search (optional), e.g. 'sales', 'startups'"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 10)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "score_lead",
        "description": "Score a lead against the ICP (Ideal Customer Profile) from 0-100. Returns a score and reasoning.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Lead's full name"
                },
                "title": {
                    "type": "string",
                    "description": "Job title"
                },
                "company": {
                    "type": "string",
                    "description": "Company name"
                },
                "company_size": {
                    "type": "integer",
                    "description": "Number of employees"
                },
                "industry": {
                    "type": "string",
                    "description": "Industry vertical"
                },
                "signals": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Buying signals identified (news, reddit, hiring, etc.)"
                }
            },
            "required": ["name", "title", "company"]
        }
    },
    {
        "name": "save_lead",
        "description": "Save a qualified lead to the local PostgreSQL database.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Full name"},
                "title": {"type": "string", "description": "Job title"},
                "company": {"type": "string", "description": "Company name"},
                "email": {"type": "string", "description": "Email address"},
                "linkedin_url": {"type": "string", "description": "LinkedIn URL"},
                "icp_score": {"type": "integer", "description": "ICP score 0-100"},
                "signal": {"type": "string", "description": "Primary buying signal"},
                "personalized_opener": {"type": "string", "description": "Personalized outreach opener"}
            },
            "required": ["name", "company", "icp_score"]
        }
    },
    {
        "name": "draft_outreach",
        "description": "Draft a personalized cold outreach message for a lead based on their profile and buying signals.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Lead's first name"},
                "title": {"type": "string", "description": "Job title"},
                "company": {"type": "string", "description": "Company name"},
                "signal": {"type": "string", "description": "Key buying signal to reference"},
                "tone": {
                    "type": "string",
                    "enum": ["professional", "casual", "direct"],
                    "description": "Tone of the message (default: professional)"
                }
            },
            "required": ["name", "title", "company"]
        }
    }
]

# Build a lookup dict for fast dispatch
_TOOL_MAP: dict[str, dict] = {t["name"]: t for t in TOOLS}


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

def dispatch_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Route a tool call to the correct implementation."""
    handlers = {
        "search_apollo": _search_apollo,
        "enrich_apollo": _enrich_apollo,
        "find_email_hunter": _find_email_hunter,
        "search_news": _search_news,
        "search_reddit": _search_reddit,
        "score_lead": _score_lead,
        "save_lead": _save_lead,
        "draft_outreach": _draft_outreach,
    }
    handler = handlers.get(name)
    if not handler:
        return {"error": f"Unknown tool: {name}"}
    try:
        return handler(**arguments)
    except Exception as e:
        logger.warning(f"Tool {name} failed: {e}")
        return {"error": str(e), "tool": name}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _search_apollo(
    job_titles: list[str],
    industries: list[str] | None = None,
    employee_range: str = "10,500",
    keywords: str = "",
    limit: int = 10,
) -> dict:
    if not config.APOLLO_API_KEY:
        return {"error": "APOLLO_API_KEY not set", "leads": []}
    try:
        payload = {
            "api_key": config.APOLLO_API_KEY,
            "person_titles": job_titles,
            "organization_num_employees_ranges": [employee_range],
            "page": 1,
            "per_page": limit,
        }
        if industries:
            payload["organization_industry_tag_ids"] = industries
        if keywords:
            payload["q_keywords"] = keywords
        r = httpx.post(
            "https://api.apollo.io/v1/mixed_people/search",
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        leads = [
            {
                "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
                "title": p.get("title", ""),
                "company": p.get("organization", {}).get("name", ""),
                "linkedin_url": p.get("linkedin_url", ""),
                "location": p.get("city", ""),
            }
            for p in data.get("people", [])
        ]
        return {"leads": leads, "total": len(leads)}
    except Exception as e:
        return {"error": str(e), "leads": []}


def _enrich_apollo(
    name: str,
    company: str = "",
    domain: str = "",
    linkedin_url: str = "",
) -> dict:
    if not config.APOLLO_API_KEY:
        return {"error": "APOLLO_API_KEY not set"}
    try:
        payload = {"api_key": config.APOLLO_API_KEY}
        parts = name.split()
        if len(parts) >= 2:
            payload["first_name"] = parts[0]
            payload["last_name"] = " ".join(parts[1:])
        if company:
            payload["organization_name"] = company
        if domain:
            payload["domain"] = domain
        if linkedin_url:
            payload["linkedin_url"] = linkedin_url
        r = httpx.post(
            "https://api.apollo.io/v1/people/match",
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
        p = r.json().get("person", {})
        return {
            "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
            "email": p.get("email", ""),
            "title": p.get("title", ""),
            "company": p.get("organization", {}).get("name", ""),
            "company_size": p.get("organization", {}).get("estimated_num_employees", 0),
            "linkedin_url": p.get("linkedin_url", ""),
            "city": p.get("city", ""),
        }
    except Exception as e:
        return {"error": str(e)}


def _find_email_hunter(first_name: str, last_name: str, domain: str) -> dict:
    if not config.HUNTER_API_KEY:
        return {"error": "HUNTER_API_KEY not set"}
    try:
        r = httpx.get(
            "https://api.hunter.io/v2/email-finder",
            params={
                "domain": domain,
                "first_name": first_name,
                "last_name": last_name,
                "api_key": config.HUNTER_API_KEY,
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json().get("data", {})
        return {
            "email": data.get("email", ""),
            "confidence": data.get("score", 0),
            "verified": data.get("verification", {}).get("status") == "valid",
        }
    except Exception as e:
        return {"error": str(e)}


def _search_news(query: str, days_back: int = 30) -> dict:
    if not config.NEWSAPI_KEY:
        return {"error": "NEWSAPI_KEY not set", "articles": []}
    try:
        from datetime import timedelta
        from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
        r = httpx.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "from": from_date,
                "sortBy": "relevancy",
                "pageSize": 5,
                "apiKey": config.NEWSAPI_KEY,
            },
            timeout=10,
        )
        r.raise_for_status()
        articles = [
            {
                "title": a.get("title", ""),
                "description": a.get("description", ""),
                "published": a.get("publishedAt", ""),
                "source": a.get("source", {}).get("name", ""),
            }
            for a in r.json().get("articles", [])
        ]
        return {"articles": articles, "query": query}
    except Exception as e:
        return {"error": str(e), "articles": []}


def _search_reddit(query: str, subreddit: str = "", limit: int = 10) -> dict:
    try:
        import praw
        reddit = praw.Reddit(
            client_id=config.REDDIT_CLIENT_ID,
            client_secret=config.REDDIT_CLIENT_SECRET,
            user_agent="LeadHunterOS/2.0",
        )
        target = reddit.subreddit(subreddit or "all")
        posts = [
            {
                "title": post.title,
                "score": post.score,
                "url": post.url,
                "selftext": post.selftext[:300],
                "subreddit": str(post.subreddit),
            }
            for post in target.search(query, limit=limit)
        ]
        return {"posts": posts, "query": query}
    except Exception as e:
        return {"error": str(e), "posts": []}


def _score_lead(
    name: str,
    title: str,
    company: str,
    company_size: int = 0,
    industry: str = "",
    signals: list[str] | None = None,
) -> dict:
    """Simple rule-based ICP scoring. Agent supplements with LLM reasoning."""
    score = 50  # base
    reasons = []

    # Title signals
    senior_titles = ["vp", "vice president", "head of", "director", "cro", "cso", "founder", "ceo", "coo"]
    if any(t in title.lower() for t in senior_titles):
        score += 20
        reasons.append(f"Senior title: {title}")

    # Company size
    if 10 <= company_size <= 500:
        score += 15
        reasons.append(f"Ideal company size: {company_size} employees")
    elif company_size > 500:
        score -= 10
        reasons.append("Company may be too large")

    # Buying signals
    if signals:
        score += min(len(signals) * 5, 15)
        reasons.extend([f"Signal: {s}" for s in signals[:3]])

    score = max(0, min(100, score))
    return {"score": score, "name": name, "company": company, "reasons": reasons}


def _save_lead(
    name: str,
    company: str,
    icp_score: int,
    title: str = "",
    email: str = "",
    linkedin_url: str = "",
    signal: str = "",
    personalized_opener: str = "",
) -> dict:
    """Save lead to DB if configured, otherwise log it."""
    lead = {
        "name": name,
        "title": title,
        "company": company,
        "email": email,
        "linkedin_url": linkedin_url,
        "icp_score": icp_score,
        "signal": signal,
        "personalized_opener": personalized_opener,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info(f"Lead saved: {name} @ {company} (score={icp_score})")
    # TODO: insert into PostgreSQL when DB is configured
    return {"status": "saved", "lead": lead}


def _draft_outreach(
    name: str,
    title: str,
    company: str,
    signal: str = "",
    tone: str = "professional",
) -> dict:
    """Generates outreach template. LLM will personalize further."""
    opener = (
        f"Hi {name.split()[0]}, I noticed {company} recently {signal or 'has been growing'}. "
        f"Given your role as {title}, I thought our solution could be timely."
    )
    return {
        "opener": opener,
        "name": name,
        "company": company,
        "tone": tone,
    }
