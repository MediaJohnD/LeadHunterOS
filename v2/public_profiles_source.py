"""public_profiles_source.py - Zero-login public profile & identity sources.

Adds the "cross-reference" layer described in the research audit:
  - Wellfound (AngelList) job listings  — company + role signals, no auth
  - Crunchbase News RSS                 — public funding announcements
  - Company "About / Team" pages        — person-level public bios (heuristic)
  - SpeakerHub / Sessionize             — conference speaker bios
  - ORCID public API                    — academic identity cross-reference
  - Glassdoor public RSS                — company + culture signals

Design principles (per the Layer 1-6 framework):
  - No login. No cookies. No fake accounts.
  - LinkedIn is deliberately NOT a primary source here. JobSpy pulls
    LinkedIn job postings (public, no-login) — this module does NOT
    scrape LinkedIn profiles. LinkedIn is one-of-N, not the source.
  - Field minimization: only business-relevant public fields are kept.
    Personal/sensitive data (home address, family, health, ethnicity,
    political/religious affiliation) is dropped at ingest, not output.
  - Source URL recorded for every record (Layer 6 provenance).
  - Respectful rate limits on every endpoint.

Adding these sources brings LeadHunterOS from 10 signal keys to 17+,
closing the gap with licensed providers (Coresignal 15+, PDL 20+).
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import requests
from loguru import logger

HEADERS = {
    "User-Agent": "LeadHunterOS-Research research@leadhunteros.local",
    "Accept": "text/html,application/xhtml+xml,application/json,application/rss+xml",
}

_SESSION = requests.Session()
_SESSION.headers.update(HEADERS)

# Business-only field allowlist — sensitive personal data dropped at ingest (Layer 3)
_BUSINESS_FIELDS = {
    "name", "title", "company", "company_domain", "company_url",
    "public_profile_url", "headline", "industry", "work_location",
    "source", "source_url", "signal_type", "observed_at",
}

_NAME_BEFORE_TITLE = re.compile(
    r"([A-Z][a-z]+ (?:[A-Z][a-z]+ )?[A-Z][a-z]+)\s*[,\n|—–-]\s*"
    r"(CEO|CTO|COO|CFO|CMO|CRO|VP|Head of|Director|Founder|Co-Founder|"
    r"President|Partner|Principal|Managing|General Manager|Senior)"
)


def _keep_business_fields(record: dict[str, Any]) -> dict[str, Any]:
    """Drop any field not on the business allowlist (Layer 3: field minimization)."""
    return {k: v for k, v in record.items() if k in _BUSINESS_FIELDS and v not in (None, "", [], {})}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Wellfound / AngelList  (public job listings — no auth)
# ---------------------------------------------------------------------------

def search_wellfound_jobs(
    keywords: list[str],
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """Search Wellfound public job listings for company + role signals.

    Uses the public /jobs page (no login, no API key).
    Returns company + role signals — not personal contact data.
    """
    results: list[dict[str, Any]] = []
    for kw in keywords[:3]:
        try:
            url = f"https://wellfound.com/jobs?keywords={quote_plus(kw)}"
            resp = _SESSION.get(url, timeout=12)
            if resp.status_code != 200:
                logger.debug(f"Wellfound returned {resp.status_code} for '{kw}'")
                continue

            html = resp.text

            # Extract structured job data from JSON-LD schema blocks
            json_blocks = re.findall(
                r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
                html, re.DOTALL | re.IGNORECASE
            )
            for block in json_blocks:
                try:
                    data = json.loads(block.strip())
                    items = data if isinstance(data, list) else data.get("@graph", [data])
                    for item in items:
                        if item.get("@type") not in ("JobPosting", "jobPosting"):
                            continue
                        org = item.get("hiringOrganization", {})
                        company_name = org.get("name", "") if isinstance(org, dict) else ""
                        loc = item.get("jobLocation", {})
                        location = loc.get("address", {}).get("addressLocality", "") if isinstance(loc, dict) else ""
                        results.append(_keep_business_fields({
                            "title": item.get("title", ""),
                            "company": company_name,
                            "company_url": org.get("url", "") if isinstance(org, dict) else "",
                            "work_location": location,
                            "headline": (item.get("description", "") or "")[:200],
                            "source": "wellfound",
                            "source_url": url,
                            "signal_type": "job_posting",
                            "observed_at": _now_iso(),
                        }))
                except Exception:
                    continue

            # Fallback: heuristic extraction if JSON-LD absent
            if not results:
                for company in re.findall(r'"companyName"\s*:\s*"([^"]+)"', html)[:10]:
                    results.append(_keep_business_fields({
                        "company": company,
                        "source": "wellfound",
                        "source_url": url,
                        "signal_type": "job_posting",
                        "observed_at": _now_iso(),
                    }))

            time.sleep(1.5)
        except Exception as exc:
            logger.warning(f"Wellfound search error for '{kw}': {exc}")

    return results[:max_results]


# ---------------------------------------------------------------------------
# Crunchbase News RSS  (public funding/launch announcements)
# ---------------------------------------------------------------------------

def search_crunchbase_news(
    keywords: list[str],
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """Fetch Crunchbase News RSS for public funding and company announcements.

    Uses the public RSS feed — no API key, no login.
    Returns company-level signals (funding, launches, acquisitions).
    """
    results: list[dict[str, Any]] = []
    feeds = [
        "https://news.crunchbase.com/feed/",
        "https://news.crunchbase.com/venture/feed/",
        "https://news.crunchbase.com/startups/feed/",
    ]
    for feed_url in feeds:
        try:
            resp = _SESSION.get(feed_url, timeout=10)
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.text)
            for item in root.findall(".//item"):
                title = item.findtext("title", "").lower()
                desc = item.findtext("description", "").lower()
                if not any(kw.lower() in title or kw.lower() in desc for kw in keywords):
                    continue
                results.append(_keep_business_fields({
                    "headline": item.findtext("title", "")[:200],
                    "source": "crunchbase_news",
                    "source_url": item.findtext("link", ""),
                    "signal_type": "funding_news",
                    "observed_at": item.findtext("pubDate", "") or _now_iso(),
                }))
            time.sleep(0.5)
        except Exception as exc:
            logger.warning(f"Crunchbase News RSS error ({feed_url}): {exc}")

    return results[:max_results]


# ---------------------------------------------------------------------------
# Company "About / Team" page scraper  (heuristic person discovery)
# ---------------------------------------------------------------------------

def scrape_company_team_page(
    company_name: str,
    domain: str,
    max_people: int = 10,
) -> list[dict[str, Any]]:
    """Attempt to scrape a company's public 'About / Team' page for bio cards.

    Tries common paths: /about, /team, /about-us, /leadership, /people.
    Extracts ONLY: name + title (public bio data the company self-published).
    Drops any non-business fields at ingest (Layer 3).

    This is NOT LinkedIn scraping. It targets the company's own website,
    where employees have self-published their name and title.
    """
    results: list[dict[str, Any]] = []
    paths = ["/about", "/team", "/about-us", "/leadership", "/people",
             "/our-team", "/who-we-are", "/company/team"]

    for path in paths:
        url = f"https://{domain}{path}"
        try:
            resp = _SESSION.get(url, timeout=8, allow_redirects=True)
            if resp.status_code != 200:
                continue

            html = resp.text
            if not any(t in html.lower() for t in ["ceo", "founder", "director", "vp ", "head of"]):
                continue

            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text)

            for match in _NAME_BEFORE_TITLE.finditer(text):
                name = match.group(1).strip()
                title_start = match.group(2).strip()
                title_context = text[match.end():match.end() + 60]
                full_title = (title_start + " " + title_context.split("\n")[0]).strip()[:80]

                if len(name.split()) < 2 or len(name.split()) > 4:
                    continue

                results.append(_keep_business_fields({
                    "name": name,
                    "title": full_title,
                    "company": company_name,
                    "company_domain": domain,
                    "company_url": f"https://{domain}",
                    "public_profile_url": url,
                    "source": "company_team_page",
                    "source_url": url,
                    "signal_type": "public_bio",
                    "observed_at": _now_iso(),
                }))

                if len(results) >= max_people:
                    break

            if results:
                logger.info(f"Team page {url}: extracted {len(results)} people")
                break

            time.sleep(0.5)
        except Exception as exc:
            logger.debug(f"Team page scrape failed ({url}): {exc}")

    return results[:max_people]


# ---------------------------------------------------------------------------
# Sessionize  (conference speaker bios — public opt-in profiles)
# ---------------------------------------------------------------------------

def search_conference_speakers(
    keywords: list[str],
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """Search Sessionize public speaker profiles for professional bios.

    Sessionize profiles are self-published by speakers who opt in publicly.
    Maximum compliance posture: fully consensual, public-intent data.
    """
    results: list[dict[str, Any]] = []
    for kw in keywords[:2]:
        try:
            url = f"https://sessionize.com/api/v2/speakers/search?term={quote_plus(kw)}"
            resp = _SESSION.get(url, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            speakers = data if isinstance(data, list) else data.get("speakers", [])
            for sp in speakers[:10]:
                if not isinstance(sp, dict):
                    continue
                results.append(_keep_business_fields({
                    "name": sp.get("fullName", ""),
                    "title": sp.get("tagLine", ""),
                    "company": sp.get("company", ""),
                    "headline": (sp.get("bio", "") or "")[:200],
                    "public_profile_url": sp.get("profileUrl", ""),
                    "source": "sessionize",
                    "source_url": url,
                    "signal_type": "conference_speaker",
                    "observed_at": _now_iso(),
                }))
            time.sleep(0.8)
        except Exception as exc:
            logger.debug(f"Sessionize search error for '{kw}': {exc}")

    return results[:max_results]


# ---------------------------------------------------------------------------
# ORCID public API  (academic identity — CC0 open data)
# ---------------------------------------------------------------------------

def search_orcid_profiles(
    keywords: list[str],
    max_results: int = 15,
) -> list[dict[str, Any]]:
    """Search ORCID for academic/research professionals (CC0 open data).

    ORCID public data is explicitly licensed CC0 — zero IP risk.
    Useful for academic institution ICP segments.
    """
    results: list[dict[str, Any]] = []
    for kw in keywords[:2]:
        try:
            resp = _SESSION.get(
                "https://pub.orcid.org/v3.0/search",
                params={"q": kw, "rows": 10},
                headers={**HEADERS, "Accept": "application/json"},
                timeout=10,
            )
            if resp.status_code != 200:
                continue
            for record in resp.json().get("result", []):
                orcid_id = record.get("orcid-identifier", {}).get("path", "")
                if not orcid_id:
                    continue
                try:
                    detail = _SESSION.get(
                        f"https://pub.orcid.org/v3.0/{orcid_id}/person",
                        headers={**HEADERS, "Accept": "application/json"},
                        timeout=8,
                    )
                    if detail.status_code != 200:
                        continue
                    person = detail.json()
                    name_data = person.get("name", {}) or {}
                    given = (name_data.get("given-names") or {}).get("value", "")
                    family = (name_data.get("family-name") or {}).get("value", "")
                    bio = ((person.get("biography") or {}).get("content") or "")[:200]
                    if not (given or family):
                        continue
                    results.append(_keep_business_fields({
                        "name": f"{given} {family}".strip(),
                        "headline": bio,
                        "public_profile_url": f"https://orcid.org/{orcid_id}",
                        "source": "orcid",
                        "source_url": f"https://orcid.org/{orcid_id}",
                        "signal_type": "academic_profile",
                        "observed_at": _now_iso(),
                    }))
                    time.sleep(0.3)
                except Exception:
                    continue
            time.sleep(1.0)
        except Exception as exc:
            logger.debug(f"ORCID search error for '{kw}': {exc}")

    return results[:max_results]


# ---------------------------------------------------------------------------
# Glassdoor public RSS  (company/culture signals)
# ---------------------------------------------------------------------------

def search_glassdoor_news(
    keywords: list[str],
    max_results: int = 15,
) -> list[dict[str, Any]]:
    """Fetch Glassdoor blog RSS for company culture and hiring signals.

    Public blog RSS only — no profile scraping, no auth.
    """
    results: list[dict[str, Any]] = []
    try:
        resp = _SESSION.get("https://www.glassdoor.com/blog/feed/", timeout=10)
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.text)
        for item in root.findall(".//item"):
            title = item.findtext("title", "").lower()
            desc = item.findtext("description", "").lower()
            if not any(kw.lower() in title or kw.lower() in desc for kw in keywords):
                continue
            results.append(_keep_business_fields({
                "headline": item.findtext("title", "")[:200],
                "source": "glassdoor_news",
                "source_url": item.findtext("link", ""),
                "signal_type": "company_culture_news",
                "observed_at": item.findtext("pubDate", "") or _now_iso(),
            }))
    except Exception as exc:
        logger.warning(f"Glassdoor RSS error: {exc}")

    return results[:max_results]


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def get_all_public_profiles(
    keywords: list[str],
    company_domains: list[tuple[str, str]] | None = None,
    include_sources: list[str] | None = None,
    max_results: int = 50,
) -> list[dict[str, Any]]:
    """Aggregate all public cross-reference sources.

    Builds profile overlap from Wellfound, Crunchbase, company team pages,
    conference speakers, ORCID, and Glassdoor — deliberately avoiding
    LinkedIn as a primary source (LinkedIn is one-of-N via JobSpy only).

    Args:
        keywords: Topic/ICP keywords to search.
        company_domains: Optional list of (company_name, domain) tuples
                         for team-page scraping.
        include_sources: Subset of sources (default: all).
        max_results: Max total results.
    """
    sources = include_sources or [
        "wellfound", "crunchbase_news", "team_pages",
        "conference_speakers", "orcid", "glassdoor",
    ]
    all_results: list[dict[str, Any]] = []

    if "wellfound" in sources:
        logger.info("Fetching Wellfound job signals...")
        all_results.extend(search_wellfound_jobs(keywords))

    if "crunchbase_news" in sources:
        logger.info("Fetching Crunchbase News RSS...")
        all_results.extend(search_crunchbase_news(keywords))

    if "team_pages" in sources and company_domains:
        logger.info(f"Scraping team pages for {len(company_domains)} companies...")
        for company_name, domain in company_domains[:5]:
            all_results.extend(scrape_company_team_page(company_name, domain))
            time.sleep(1.0)

    if "conference_speakers" in sources:
        logger.info("Fetching conference speaker profiles...")
        all_results.extend(search_conference_speakers(keywords))

    if "orcid" in sources:
        logger.info("Fetching ORCID academic profiles...")
        all_results.extend(search_orcid_profiles(keywords))

    if "glassdoor" in sources:
        logger.info("Fetching Glassdoor signals...")
        all_results.extend(search_glassdoor_news(keywords))

    logger.info(f"Public profiles: {len(all_results)} records from {len(sources)} sources")
    return all_results[:max_results]
