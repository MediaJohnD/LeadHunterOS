"""signals_source.py - Buying-signal monitoring. Zero cost. No API key required.

Sources covered (all free / public):
  - Hacker News  (Algolia API)  - HN job posts, Show HN, Ask HN
  - Reddit       (JSON API)     - subreddit keyword search
  - Google News  (RSS)          - company/keyword news
  - GitHub       (REST API)     - repo/topic trending signals
  - ProductHunt  (RSS)          - new product launches
  - RemoteOK     (JSON API)     - job posts with tech stack signals
  - Crunchbase News (RSS)       - public funding announcements

All endpoints are US-hosted public APIs. No signup needed.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import requests
from loguru import logger

HEADERS = {
    "User-Agent": "LeadHunterOS research@leadhunteros.local",
    "Accept": "application/json",
}
_SESSION = requests.Session()
_SESSION.headers.update(HEADERS)


# ---------------------------------------------------------------------------
# Hacker News (Algolia API)
# ---------------------------------------------------------------------------

def search_hackernews(
    keywords: list[str],
    daysback: int = 30,
    max_results: int = 30,
) -> list[dict]:
    """Search HN posts/comments for buying signals."""
    results: list[dict] = []
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=daysback)).timestamp())
    for kw in keywords:
        try:
            url = (
                f"https://hn.algolia.com/api/v1/search"
                f"?query={quote_plus(kw)}&numericFilters=created_at_i>{cutoff}"
                f"&hitsPerPage=20&tags=story"
            )
            resp = _SESSION.get(url, timeout=10)
            if resp.status_code != 200:
                continue
            for hit in resp.json().get("hits", []):
                results.append({
                    "source": "hackernews",
                    "signal_type": "hn_post",
                    "keyword": kw,
                    "title": hit.get("title", ""),
                    "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                    "author": hit.get("author", ""),
                    "score": hit.get("points", 0),
                    "comments": hit.get("num_comments", 0),
                    "published_at": hit.get("created_at", ""),
                })
            time.sleep(0.3)
        except Exception as exc:
            logger.warning(f"HN search error for '{kw}': {exc}")
    return results[:max_results]


def search_hn_whoishiring(
    keywords: list[str],
    max_results: int = 20,
) -> list[dict]:
    """Search the monthly 'Who is Hiring' HN thread for tech stack signals."""
    results: list[dict] = []
    try:
        url = "https://hn.algolia.com/api/v1/search?tags=story&query=who+is+hiring&hitsPerPage=5"
        resp = _SESSION.get(url, timeout=10)
        if resp.status_code != 200:
            return []
        hits = resp.json().get("hits", [])
        # grab top 2 most-recent hiring threads
        thread_ids = [h["objectID"] for h in hits[:2]]
        for thread_id in thread_ids:
            comments_url = (
                f"https://hn.algolia.com/api/v1/search"
                f"?tags=comment,story_{thread_id}&hitsPerPage=100"
            )
            cresp = _SESSION.get(comments_url, timeout=10)
            if cresp.status_code != 200:
                continue
            for c in cresp.json().get("hits", []):
                text = (c.get("comment_text") or "").lower()
                matched = [kw for kw in keywords if kw.lower() in text]
                if matched:
                    results.append({
                        "source": "hackernews_hiring",
                        "signal_type": "hn_hiring_comment",
                        "keyword": ", ".join(matched),
                        "title": "HN Who Is Hiring comment",
                        "url": f"https://news.ycombinator.com/item?id={c.get('objectID')}",
                        "author": c.get("author", ""),
                        "score": 0,
                        "comments": 0,
                        "published_at": c.get("created_at", ""),
                    })
            time.sleep(0.3)
    except Exception as exc:
        logger.warning(f"HN hiring search error: {exc}")
    return results[:max_results]


# ---------------------------------------------------------------------------
# Reddit (public JSON API)
# ---------------------------------------------------------------------------

REDDIT_SUBREDDITS = [
    "entrepreneur", "startups", "sales", "marketing", "saas",
    "smallbusiness", "forhire", "hiring", "leadgeneration", "digitalmarketing",
]


def search_reddit(
    keywords: list[str],
    subreddits: list[str] | None = None,
    daysback: int = 14,
    max_results: int = 30,
) -> list[dict]:
    """Search Reddit for buying signals via the public JSON search API."""
    subs = subreddits or REDDIT_SUBREDDITS
    results: list[dict] = []
    for kw in keywords:
        for sub in subs:
            try:
                url = (
                    f"https://www.reddit.com/r/{sub}/search.json"
                    f"?q={quote_plus(kw)}&restrict_sr=1&sort=new&limit=10"
                )
                resp = _SESSION.get(url, timeout=10)
                if resp.status_code != 200:
                    continue
                posts = resp.json().get("data", {}).get("children", [])
                cutoff = datetime.now(timezone.utc) - timedelta(days=daysback)
                for post in posts:
                    d = post.get("data", {})
                    created = datetime.utcfromtimestamp(d.get("created_utc", 0))
                    if created < cutoff.replace(tzinfo=None):
                        continue
                    results.append({
                        "source": "reddit",
                        "signal_type": "reddit_post",
                        "keyword": kw,
                        "title": d.get("title", ""),
                        "url": f"https://reddit.com{d.get('permalink', '')}",
                        "author": d.get("author", ""),
                        "score": d.get("score", 0),
                        "comments": d.get("num_comments", 0),
                        "subreddit": sub,
                        "published_at": created.isoformat(),
                    })
                time.sleep(0.5)
            except Exception as exc:
                logger.warning(f"Reddit search error r/{sub} '{kw}': {exc}")
    return results[:max_results]


# ---------------------------------------------------------------------------
# Google News (RSS)
# ---------------------------------------------------------------------------

def search_google_news(
    keywords: list[str],
    daysback: int = 7,
    max_results: int = 30,
) -> list[dict]:
    """Fetch Google News RSS feed items for keyword-based buying signals."""
    results: list[dict] = []
    for kw in keywords:
        try:
            url = f"https://news.google.com/rss/search?q={quote_plus(kw)}&hl=en-US&gl=US&ceid=US:en"
            resp = _SESSION.get(url, timeout=10)
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.text)
            ns = {}
            items = root.findall(".//item")
            cutoff = datetime.now(timezone.utc) - timedelta(days=daysback)
            for item in items:
                pub_text = item.findtext("pubDate", "")
                try:
                    from email.utils import parsedate_to_datetime
                    pub_dt = parsedate_to_datetime(pub_text)
                    if pub_dt.tzinfo is None:
                        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    pub_dt = datetime.now(timezone.utc)
                if pub_dt < cutoff:
                    continue
                results.append({
                    "source": "google_news",
                    "signal_type": "news_article",
                    "keyword": kw,
                    "title": item.findtext("title", ""),
                    "url": item.findtext("link", ""),
                    "author": item.findtext("source", ""),
                    "score": 0,
                    "comments": 0,
                    "published_at": pub_dt.isoformat(),
                })
            time.sleep(0.3)
        except Exception as exc:
            logger.warning(f"Google News RSS error for '{kw}': {exc}")
    return results[:max_results]


# ---------------------------------------------------------------------------
# GitHub (REST API)
# ---------------------------------------------------------------------------

def search_github_repos(
    keywords: list[str],
    max_results: int = 20,
) -> list[dict]:
    """Search GitHub repos as tech-adoption buying signals."""
    results: list[dict] = []
    for kw in keywords:
        try:
            url = (
                f"https://api.github.com/search/repositories"
                f"?q={quote_plus(kw)}&sort=updated&order=desc&per_page=10"
            )
            resp = requests.get(
                url,
                headers={"User-Agent": "LeadHunterOS", "Accept": "application/vnd.github+json"},
                timeout=10,
            )
            if resp.status_code != 200:
                continue
            for repo in resp.json().get("items", []):
                results.append({
                    "source": "github",
                    "signal_type": "github_repo",
                    "keyword": kw,
                    "title": repo.get("full_name", ""),
                    "url": repo.get("html_url", ""),
                    "author": repo.get("owner", {}).get("login", ""),
                    "score": repo.get("stargazers_count", 0),
                    "comments": repo.get("open_issues_count", 0),
                    "description": repo.get("description", ""),
                    "published_at": repo.get("updated_at", ""),
                })
            time.sleep(1)  # GitHub unauthenticated rate limit
        except Exception as exc:
            logger.warning(f"GitHub search error for '{kw}': {exc}")
    return results[:max_results]


# ---------------------------------------------------------------------------
# ProductHunt (RSS)
# ---------------------------------------------------------------------------

def search_producthunt_launches(
    keywords: list[str],
    max_results: int = 20,
) -> list[dict]:
    """Fetch recent ProductHunt launches as ICP/competitor signal."""
    results: list[dict] = []
    try:
        url = "https://www.producthunt.com/feed"
        resp = _SESSION.get(url, timeout=10)
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.text)
        items = root.findall(".//item")
        for item in items:
            title = item.findtext("title", "").lower()
            desc = item.findtext("description", "").lower()
            matched = [kw for kw in keywords if kw.lower() in title or kw.lower() in desc]
            if not matched:
                continue
            results.append({
                "source": "producthunt",
                "signal_type": "product_launch",
                "keyword": ", ".join(matched),
                "title": item.findtext("title", ""),
                "url": item.findtext("link", ""),
                "author": "",
                "score": 0,
                "comments": 0,
                "published_at": item.findtext("pubDate", ""),
            })
    except Exception as exc:
        logger.warning(f"ProductHunt RSS error: {exc}")
    return results[:max_results]


# ---------------------------------------------------------------------------
# RemoteOK (JSON API)
# ---------------------------------------------------------------------------

def search_remoteok_jobs(
    keywords: list[str],
    max_results: int = 20,
) -> list[dict]:
    """Search RemoteOK job listings for tech-stack / role buying signals."""
    results: list[dict] = []
    try:
        resp = _SESSION.get("https://remoteok.com/api", timeout=15)
        if resp.status_code != 200:
            return []
        jobs = resp.json()
        if isinstance(jobs, list) and jobs and isinstance(jobs[0], dict) and "legal" in jobs[0]:
            jobs = jobs[1:]  # skip the first legal notice object
        for job in jobs:
            if not isinstance(job, dict):
                continue
            text = " ".join([
                job.get("position", ""),
                job.get("company", ""),
                ", ".join(job.get("tags", [])),
                job.get("description", ""),
            ]).lower()
            matched = [kw for kw in keywords if kw.lower() in text]
            if not matched:
                continue
            results.append({
                "source": "remoteok",
                "signal_type": "job_posting",
                "keyword": ", ".join(matched),
                "title": job.get("position", ""),
                "url": job.get("url", ""),
                "author": job.get("company", ""),
                "score": 0,
                "comments": 0,
                "published_at": job.get("date", ""),
                "company": job.get("company", ""),
                "location": job.get("location", "Remote"),
                "salary": job.get("salary", ""),
            })
    except Exception as exc:
        logger.warning(f"RemoteOK error: {exc}")
    return results[:max_results]


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def get_all_signals(
    keywords: list[str],
    daysback: int = 14,
    include_sources: list[str] | None = None,
) -> list[dict]:
    """Aggregate buying signals from all zero-signup sources."""
    sources = include_sources or ["hackernews", "reddit", "googlenews", "github", "producthunt", "remoteok"]
    all_results: list[dict] = []

    if "hackernews" in sources:
        logger.info("Fetching HN signals...")
        all_results.extend(search_hackernews(keywords, daysback=daysback))
        all_results.extend(search_hn_whoishiring(keywords))
    if "reddit" in sources:
        logger.info("Fetching Reddit signals...")
        all_results.extend(search_reddit(keywords, daysback=daysback))
    if "googlenews" in sources:
        logger.info("Fetching Google News signals...")
        all_results.extend(search_google_news(keywords, daysback=daysback))
    if "github" in sources:
        logger.info("Fetching GitHub signals...")
        all_results.extend(search_github_repos(keywords))
    if "producthunt" in sources:
        logger.info("Fetching ProductHunt signals...")
        all_results.extend(search_producthunt_launches(keywords))
    if "remoteok" in sources:
        logger.info("Fetching RemoteOK job signals...")
        all_results.extend(search_remoteok_jobs(keywords))

    logger.info(f"Signals total: {len(all_results)} items from {len(sources)} sources")
    return all_results
