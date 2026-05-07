"""enrich_source.py - Zero-cost lead enrichment. No API key required for core features.

Capabilities (all free / open-source):
  - Email pattern guessing  (first.last@domain, flast@domain, etc.)
  - MX record verification  (dnspython - confirms domain accepts email)
  - SMTP RCPT-TO verify     (optional - checks if mailbox exists)
  - Website metadata scrape (title, description, tech stack hints via headers)
  - LinkedIn public profile URL builder (search URL pattern - no scraping)
  - Clearbit Logo API       (free, no auth - just returns logo URL)
  - Hunter.io domain search (free tier 25/mo) - OPTIONAL
  - whois / RDAP lookup     (public IANA RDAP endpoints, no key)

Design: Try each enrichment step. Failures are silently skipped.
        Returns a merged dict that the agent adds to the lead record.
"""

from __future__ import annotations

import re
import socket
import time
from typing import Any
from urllib.parse import urlparse, quote_plus

import requests
from loguru import logger

# optional - dnspython for MX lookup
try:
    import dns.resolver
    _DNS_AVAILABLE = True
except ImportError:
    _DNS_AVAILABLE = False
    logger.warning("dnspython not installed - MX verification disabled. pip install dnspython")

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "LeadHunterOS research@leadhunteros.local",
    "Accept": "text/html,application/xhtml+xml,application/json",
})


# ---------------------------------------------------------------------------
# Email pattern generation
# ---------------------------------------------------------------------------

EMAIL_PATTERNS = [
    "{first}.{last}@{domain}",
    "{first}{last}@{domain}",
    "{f}{last}@{domain}",
    "{first}@{domain}",
    "{last}@{domain}",
    "{first}_{last}@{domain}",
    "{f}.{last}@{domain}",
]


def generate_email_candidates(
    first_name: str,
    last_name: str,
    domain: str,
) -> list[str]:
    """Generate likely email address candidates for a person."""
    first = first_name.lower().strip()
    last = last_name.lower().strip()
    f = first[0] if first else ""
    domain = domain.lower().strip().lstrip("www.").lstrip("https://").lstrip("http://")
    candidates = []
    for pattern in EMAIL_PATTERNS:
        try:
            email = pattern.format(first=first, last=last, f=f, domain=domain)
            if re.match(r"^[\w.+-]+@[\w.-]+\.[a-z]{2,}$", email):
                candidates.append(email)
        except Exception:
            pass
    return list(dict.fromkeys(candidates))  # dedupe while preserving order


# ---------------------------------------------------------------------------
# MX verification  (requires dnspython)
# ---------------------------------------------------------------------------

def verify_mx(domain: str) -> bool:
    """Return True if the domain has a valid MX record."""
    if not _DNS_AVAILABLE:
        return True  # assume valid if we can't check
    try:
        domain = domain.lower().strip()
        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
        return len(answers) > 0
    except Exception:
        return False


def smtp_verify_email(email: str, timeout: int = 5) -> bool | None:
    """Attempt RCPT-TO SMTP verification. Returns True/False/None (None=inconclusive).

    Note: Many mail servers return 250 regardless (catch-all) or block port 25.
    Use as a weak signal only.
    """
    try:
        domain = email.split("@")[1]
        mx_records = dns.resolver.resolve(domain, "MX", lifetime=5) if _DNS_AVAILABLE else []
        if not mx_records:
            return None
        mx_host = str(sorted(mx_records, key=lambda r: r.preference)[0].exchange).rstrip(".")
        with socket.create_connection((mx_host, 25), timeout=timeout) as sock:
            banner = sock.recv(1024).decode(errors="ignore")
            if not banner.startswith("220"):
                return None
            sock.sendall(b"EHLO leadhunteros.local\r\n")
            sock.recv(1024)
            sock.sendall(b"MAIL FROM:<research@leadhunteros.local>\r\n")
            sock.recv(1024)
            sock.sendall(f"RCPT TO:<{email}>\r\n".encode())
            rcpt_resp = sock.recv(1024).decode(errors="ignore")
            sock.sendall(b"QUIT\r\n")
        return rcpt_resp.startswith("250")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Website metadata scrape
# ---------------------------------------------------------------------------

def scrape_website_metadata(domain: str) -> dict:
    """Scrape basic metadata from a company website."""
    result = {"website_title": "", "website_description": "", "tech_hints": [], "website_status": None}
    for scheme in ("https", "http"):
        try:
            url = f"{scheme}://{domain}"
            resp = _SESSION.get(url, timeout=8, allow_redirects=True)
            result["website_status"] = resp.status_code
            # tech hints from headers
            server = resp.headers.get("Server", "")
            powered = resp.headers.get("X-Powered-By", "")
            if server:
                result["tech_hints"].append(f"Server:{server}")
            if powered:
                result["tech_hints"].append(f"PoweredBy:{powered}")
            # parse title / meta description from HTML
            html = resp.text[:20000]  # only read first 20KB
            title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
            if title_match:
                result["website_title"] = title_match.group(1).strip()
            desc_match = re.search(
                r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
                html, re.IGNORECASE
            )
            if desc_match:
                result["website_description"] = desc_match.group(1).strip()
            # tech stack hints from HTML body
            tech_patterns = {
                "Salesforce": r"salesforce",
                "HubSpot": r"hubspot",
                "Segment": r"segment\.com",
                "Google Analytics": r"google-analytics|gtag",
                "Intercom": r"intercom",
                "Drift": r"drift\.com",
                "React": r"react\.js|reactjs",
                "Next.js": r"next\.js|_next",
                "WordPress": r"wp-content|wordpress",
            }
            for tech, pattern in tech_patterns.items():
                if re.search(pattern, html, re.IGNORECASE):
                    result["tech_hints"].append(tech)
            break
        except Exception as exc:
            logger.debug(f"Website scrape failed ({scheme}://{domain}): {exc}")
    result["tech_hints"] = list(set(result["tech_hints"]))
    return result


# ---------------------------------------------------------------------------
# Clearbit Logo (free, no auth)
# ---------------------------------------------------------------------------

def get_company_logo_url(domain: str) -> str:
    """Return Clearbit logo URL (free, no API key)."""
    return f"https://logo.clearbit.com/{domain}"


# ---------------------------------------------------------------------------
# RDAP / WHOIS  (public IANA endpoint)
# ---------------------------------------------------------------------------

def get_domain_rdap(domain: str) -> dict:
    """Fetch public RDAP info for a domain (registrar, dates, nameservers)."""
    try:
        resp = requests.get(f"https://rdap.org/domain/{domain}", timeout=8)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        events = {e.get("eventAction"): e.get("eventDate") for e in data.get("events", [])}
        return {
            "rdap_registered": events.get("registration", ""),
            "rdap_expiry": events.get("expiration", ""),
            "rdap_updated": events.get("last changed", ""),
            "rdap_registrar": next(
                (e.get("vcardArray", [[]])[1] for e in data.get("entities", [])
                 if "registrar" in e.get("roles", [])), ""
            ),
        }
    except Exception as exc:
        logger.debug(f"RDAP lookup failed for {domain}: {exc}")
        return {}


# ---------------------------------------------------------------------------
# LinkedIn search URL builder  (no scraping - just generates search links)
# ---------------------------------------------------------------------------

def build_linkedin_search_url(company_name: str, title: str = "") -> str:
    """Build a LinkedIn people-search URL for the given company/title."""
    q = f"{company_name} {title}".strip()
    return f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(q)}&origin=GLOBAL_SEARCH_HEADER"


# ---------------------------------------------------------------------------
# Full enrich pipeline
# ---------------------------------------------------------------------------

def enrich_lead(
    company_name: str,
    domain: str,
    first_name: str = "",
    last_name: str = "",
    title: str = "",
    run_smtp: bool = False,
) -> dict:
    """Run the full zero-signup enrichment pipeline for a lead.

    Returns a dict that merges into the lead record.
    """
    result: dict[str, Any] = {
        "company": company_name,
        "domain": domain,
        "first_name": first_name,
        "last_name": last_name,
        "title": title,
        "email_candidates": [],
        "mx_valid": None,
        "logo_url": "",
        "linkedin_search_url": "",
    }

    # Email candidates
    if first_name and last_name and domain:
        result["email_candidates"] = generate_email_candidates(first_name, last_name, domain)
        logger.debug(f"Generated {len(result['email_candidates'])} email candidates for {first_name} {last_name}")

    # MX check
    if domain:
        result["mx_valid"] = verify_mx(domain)

    # SMTP verify top candidate (opt-in only)
    if run_smtp and result["email_candidates"] and result["mx_valid"]:
        top_email = result["email_candidates"][0]
        result["smtp_verified"] = smtp_verify_email(top_email)
        result["email"] = top_email if result["smtp_verified"] else ""
    elif result["email_candidates"]:
        result["email"] = result["email_candidates"][0]  # best-guess top pattern

    # Website metadata
    if domain:
        meta = scrape_website_metadata(domain)
        result.update(meta)

    # RDAP
    if domain:
        rdap = get_domain_rdap(domain)
        result.update(rdap)

    # Logo URL (free Clearbit)
    if domain:
        result["logo_url"] = get_company_logo_url(domain)

    # LinkedIn search URL
    result["linkedin_search_url"] = build_linkedin_search_url(company_name, title)

    time.sleep(0.2)
    return result


def enrich_leads_batch(
    leads: list[dict],
    run_smtp: bool = False,
) -> list[dict]:
    """Enrich a list of lead dicts in-place. Returns enriched list."""
    enriched = []
    for i, lead in enumerate(leads):
        logger.info(f"Enriching lead {i+1}/{len(leads)}: {lead.get('company', '')}")
        enrichment = enrich_lead(
            company_name=lead.get("company", ""),
            domain=lead.get("domain", ""),
            first_name=lead.get("first_name", ""),
            last_name=lead.get("last_name", ""),
            title=lead.get("title", ""),
            run_smtp=run_smtp,
        )
        merged = {**lead, **enrichment}
        enriched.append(merged)
    return enriched
