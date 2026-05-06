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


# ── Tool registry ──────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "search_apollo",
        "description": "Search Apollo.io for leads by job title, industry, company size, and keywords. Returns a list of prospects.",
    },
    {
        "name": "enrich_lead",
        "description": "Enrich a lead's contact and company data using Apollo.io. Requires domain or LinkedIn URL.",
    },
    {
        "name": "find_email",
        "description": "Find email address for a person at a company using Hunter.io. Requires first_name, last_name, domain.",
    },
    {
        "name": "search_reddit_signals",
        "description": "Search Reddit for buying signals, pain points, or intent signals matching ICP keywords.",
    },
    {
        "name": "search_news_signals",
        "description": "Search NewsAPI for company news events (funding, hiring, expansion) that indicate buying intent.",
    },
    {
        "name": "score_lead",
        "description": "Score a lead against the ICP (0-100). Returns score and reasoning.",
    },
    {
        "name": "save_lead",
        "description": "Save a qualified lead to the PostgreSQL database.",
    },
    {
        "name": "draft_outreach",
        "description": "Draft a personalized outreach email for a lead based on their signal and profile.",
    },
]


def dispatch_tool(name: str, args: dict) -> str:
    """Route a tool call to the correct function."""
    tool_map = {
        "search_apollo": search_apollo,
        "enrich_lead": enrich_lead,
        "find_email": find_email,
        "search_reddit_signals": search_reddit_signals,
        "search_news_signals": search_news_signals,
        "score_lead": score_lead,
        "save_lead": save_lead,
        "draft_outreach": draft_outreach,
    }
    fn = tool_map.get(name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return fn(**args)
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}")
        return json.dumps({"error": str(e)})


# ── Tool implementations ────────────────────────────────────────────────────────

def search_apollo(
    titles: list[str] | None = None,
    industries: list[str] | None = None,
    min_employees: int = 10,
    max_employees: int = 500,
    keywords: list[str] | None = None,
    limit: int = 10,
) -> str:
    """Search Apollo.io for leads (US-based API)."""
    if not config.APOLLO_API_KEY:
        return json.dumps({"error": "APOLLO_API_KEY not configured"})

    payload: dict[str, Any] = {
        "page": 1,
        "per_page": min(limit, 25),
        "person_titles": titles or [],
        "organization_num_employees_ranges": [
            f"{min_employees},{max_employees}"
        ],
    }
    if industries:
        payload["organization_industry_tag_ids"] = industries
    if keywords:
        payload["q_keywords"] = " ".join(keywords)

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{config.APOLLO_BASE_URL}/mixed_people/search",
                headers={"X-Api-Key": config.APOLLO_API_KEY, "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            people = data.get("people", [])[:limit]
            results = [
                {
                    "name": p.get("name"),
                    "title": p.get("title"),
                    "company": p.get("organization", {}).get("name"),
                    "domain": p.get("organization", {}).get("primary_domain"),
                    "linkedin": p.get("linkedin_url"),
                    "industry": p.get("organization", {}).get("industry"),
                    "employees": p.get("organization", {}).get("num_employees"),
                }
                for p in people
            ]
            return json.dumps({"leads": results, "count": len(results)})
    except Exception as e:
        return json.dumps({"error": str(e)})


def enrich_lead(domain: str | None = None, linkedin_url: str | None = None) -> str:
    """Enrich lead data via Apollo.io."""
    if not config.APOLLO_API_KEY:
        return json.dumps({"error": "APOLLO_API_KEY not configured"})
    if not domain and not linkedin_url:
        return json.dumps({"error": "domain or linkedin_url required"})

    try:
        with httpx.Client(timeout=30) as client:
            params: dict = {"api_key": config.APOLLO_API_KEY}
            if domain:
                params["domain"] = domain
            if linkedin_url:
                params["linkedin_url"] = linkedin_url
            resp = client.get(
                f"{config.APOLLO_BASE_URL}/organizations/enrich",
                params=params,
            )
            resp.raise_for_status()
            org = resp.json().get("organization", {})
            return json.dumps({
                "company": org.get("name"),
                "domain": org.get("primary_domain"),
                "industry": org.get("industry"),
                "employees": org.get("num_employees"),
                "revenue": org.get("annual_revenue"),
                "location": org.get("city"),
                "country": org.get("country"),
                "linkedin": org.get("linkedin_url"),
                "technologies": org.get("current_technologies", [])[:10],
            })
    except Exception as e:
        return json.dumps({"error": str(e)})


def find_email(first_name: str, last_name: str, domain: str) -> str:
    """Find email via Hunter.io (US-based)."""
    if not config.HUNTER_API_KEY:
        return json.dumps({"error": "HUNTER_API_KEY not configured"})
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{config.HUNTER_BASE_URL}/email-finder",
                params={
                    "domain": domain,
                    "first_name": first_name,
                    "last_name": last_name,
                    "api_key": config.HUNTER_API_KEY,
                },
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return json.dumps({
                "email": data.get("email"),
                "confidence": data.get("score"),
                "verified": data.get("verification", {}).get("status"),
            })
    except Exception as e:
        return json.dumps({"error": str(e)})


def search_reddit_signals(keywords: list[str], subreddits: list[str] | None = None, limit: int = 10) -> str:
    """Search Reddit for buying signals via PRAW (US company)."""
    if not config.REDDIT_CLIENT_ID or not config.REDDIT_CLIENT_SECRET:
        return json.dumps({"error": "Reddit credentials not configured"})
    try:
        import praw
        reddit = praw.Reddit(
            client_id=config.REDDIT_CLIENT_ID,
            client_secret=config.REDDIT_CLIENT_SECRET,
            user_agent=config.REDDIT_USER_AGENT,
        )
        query = " OR ".join(keywords)
        results = []
        subreddits_str = "+".join(subreddits) if subreddits else "all"
        for post in reddit.subreddit(subreddits_str).search(query, limit=limit, sort="new"):
            results.append({
                "title": post.title,
                "subreddit": str(post.subreddit),
                "score": post.score,
                "url": f"https://reddit.com{post.permalink}",
                "created": datetime.fromtimestamp(post.created_utc, tz=timezone.utc).isoformat(),
                "summary": post.selftext[:300] if post.selftext else "",
            })
        return json.dumps({"signals": results, "count": len(results)})
    except Exception as e:
        return json.dumps({"error": str(e)})


def search_news_signals(query: str, days_back: int = 7) -> str:
    """Search NewsAPI for company trigger events (US company)."""
    if not config.NEWSAPI_KEY:
        return json.dumps({"error": "NEWSAPI_KEY not configured"})
    try:
        from datetime import timedelta
        from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{config.NEWSAPI_BASE_URL}/everything",
                params={
                    "q": query,
                    "from": from_date,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 10,
                    "apiKey": config.NEWSAPI_KEY,
                },
            )
            resp.raise_for_status()
            articles = resp.json().get("articles", [])
            results = [
                {
                    "title": a["title"],
                    "source": a["source"]["name"],
                    "published": a["publishedAt"],
                    "url": a["url"],
                    "description": a.get("description", "")[:200],
                }
                for a in articles[:10]
            ]
            return json.dumps({"articles": results, "count": len(results)})
    except Exception as e:
        return json.dumps({"error": str(e)})


def score_lead(
    company_name: str,
    industry: str | None = None,
    employee_count: int | None = None,
    title: str | None = None,
    signal_summary: str | None = None,
) -> str:
    """Score lead against ICP criteria (0-100)."""
    score = 0
    reasons = []

    # Industry match (30 points)
    icp_industries = [i.lower() for i in config.ICP_INDUSTRIES.split(",")] if hasattr(config, 'ICP_INDUSTRIES') else ["saas", "software", "fintech"]
    if industry and any(i in industry.lower() for i in icp_industries):
        score += 30
        reasons.append(f"Industry match: {industry}")

    # Company size (25 points)
    min_emp = getattr(config, 'ICP_COMPANY_SIZE_MIN', 10)
    max_emp = getattr(config, 'ICP_COMPANY_SIZE_MAX', 500)
    if employee_count and min_emp <= employee_count <= max_emp:
        score += 25
        reasons.append(f"Company size in range: {employee_count}")

    # Title/seniority (25 points)
    icp_titles = [t.lower() for t in (getattr(config, 'ICP_TITLES', 'VP Sales,CRO,Founder,CEO')).split(",")]
    if title and any(t in title.lower() for t in icp_titles):
        score += 25
        reasons.append(f"Title match: {title}")

    # Signal present (20 points)
    if signal_summary:
        score += 20
        reasons.append("Has buying signal")

    return json.dumps({
        "score": score,
        "qualified": score >= config.ICP_SCORE_THRESHOLD,
        "reasons": reasons,
    })


def save_lead(lead_data: dict) -> str:
    """Save lead to PostgreSQL database."""
    try:
        import psycopg2
        conn = psycopg2.connect(config.DATABASE_URL)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO leads (
                full_name, email, linkedin_url,
                company_name, company_domain, industry, employee_count,
                title, icp_score, icp_score_reason,
                signal_type, signal_summary, status
            ) VALUES (
                %(full_name)s, %(email)s, %(linkedin_url)s,
                %(company_name)s, %(company_domain)s, %(industry)s, %(employee_count)s,
                %(title)s, %(icp_score)s, %(icp_score_reason)s,
                %(signal_type)s, %(signal_summary)s, 'qualified'
            ) ON CONFLICT (email) DO UPDATE SET
                icp_score = EXCLUDED.icp_score,
                updated_at = NOW()
            RETURNING id
            """,
            {
                "full_name": lead_data.get("name"),
                "email": lead_data.get("email"),
                "linkedin_url": lead_data.get("linkedin"),
                "company_name": lead_data.get("company"),
                "company_domain": lead_data.get("domain"),
                "industry": lead_data.get("industry"),
                "employee_count": lead_data.get("employees"),
                "title": lead_data.get("title"),
                "icp_score": lead_data.get("score", 0),
                "icp_score_reason": lead_data.get("score_reason"),
                "signal_type": lead_data.get("signal_type"),
                "signal_summary": lead_data.get("signal_summary"),
            },
        )
        lead_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return json.dumps({"success": True, "lead_id": str(lead_id), "leads_saved": 1})
    except Exception as e:
        return json.dumps({"error": str(e), "leads_saved": 0})


def draft_outreach(lead_name: str, company: str, title: str, signal_summary: str) -> str:
    """Draft a personalized outreach email for a lead."""
    subject = f"Quick question about {company}'s growth"
    body = f"""Hi {lead_name.split()[0] if lead_name else 'there'},

I noticed {signal_summary} and thought it might be relevant to you as {title} at {company}.

We help companies like yours [VALUE PROP HERE]. Would it make sense to connect for 15 minutes?

Best,
[YOUR NAME]"""
    return json.dumps({
        "subject": subject,
        "body": body,
        "note": "Personalize the value prop before sending",
    })
