"""edgar_source.py - SEC EDGAR Form D funding data. Zero cost. No API key.

SEC EDGAR is a US government database. Form D filings appear within days
of a funding round closing. Better than Crunchbase (which costs $49-99/mo
and has 24-48hr delay). This is FREE and often faster.

Endpoints used:
  - EDGAR full-text search: https://efts.sec.gov/LATEST/search-index?q=...&dateRange=custom
  - EDGAR company search: https://www.sec.gov/cgi-bin/browse-edgar
  - EDGAR submissions: https://data.sec.gov/submissions/CIK{cik}.json

No API key. No signup. US government public data.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

import requests
from loguru import logger

EDGAR_BASE = "https://efts.sec.gov"
EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"
EDGAR_DATA = "https://data.sec.gov"
HEADERS = {
    "User-Agent": "LeadHunterOS research@leadhunteros.local",  # EDGAR requires User-Agent
    "Accept": "application/json",
}


def search_funding_rounds(
    keywords: list[str] | None = None,
    state: str = "GA",
    days_back: int = 90,
    funding_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Search SEC EDGAR Form D filings for recent funding rounds.

    Form D = companies that raised private capital (VC, angel, Series A/B/C).
    Filed within days of closing. Real-time funding intelligence.

    Args:
        keywords: Company name keywords to filter (e.g. ['fintech', 'payments'])
        state: US state code (GA = Georgia/Atlanta)
        days_back: How many days back to search
        funding_types: Filter by type ('Equity', 'Convertible Securities', etc.)
    """
    results = []

    date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    date_to = datetime.now().strftime("%Y-%m-%d")

    # Search EDGAR full-text search for Form D filings
    search_terms = keywords or ["technology", "software", "fintech"]

    for term in search_terms[:3]:  # Limit to avoid rate limiting
        try:
            params = {
                "q": f'"{term}"',
                "dateRange": "custom",
                "startdt": date_from,
                "enddt": date_to,
                "forms": "D",  # Form D = private offering/funding round
            }
            if state:
                params["locationCode"] = state

            resp = requests.get(
                "https://efts.sec.gov/LATEST/search-index",
                params=params,
                headers=HEADERS,
                timeout=15,
            )

            if resp.status_code != 200:
                logger.warning(f"EDGAR search returned {resp.status_code}")
                continue

            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])
            logger.info(f"EDGAR Form D '{term}' in {state}: {len(hits)} filings")

            for hit in hits[:20]:
                src = hit.get("_source", {})
                entity_name = src.get("entity_name", "")
                filed_at = src.get("file_date", "")
                form_type = src.get("form_type", "")
                cik = src.get("entity_id", "")

                if not entity_name:
                    continue

                result = {
                    "company": entity_name,
                    "cik": cik,
                    "form_type": form_type,
                    "filed_date": filed_at,
                    "state": state,
                    "search_term": term,
                    "edgar_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=D",
                    "source": "sec_edgar_form_d",
                    "buying_signal": "Recent funding round - new budget likely available",
                }

                # Try to get more detail
                detail = _get_form_d_detail(cik)
                if detail:
                    result.update(detail)

                results.append(result)

            time.sleep(0.5)  # Be respectful to SEC servers

        except Exception as e:
            logger.warning(f"EDGAR search error for '{term}': {e}")
            continue

    # Deduplicate by company
    seen = set()
    unique = []
    for r in results:
        key = r["company"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(r)

    logger.info(f"EDGAR returning {len(unique)} unique funded companies")
    return unique


def _get_form_d_detail(cik: str) -> dict | None:
    """Fetch additional company detail from EDGAR submissions API."""
    if not cik:
        return None
    try:
        cik_padded = str(cik).zfill(10)
        url = f"{EDGAR_DATA}/submissions/CIK{cik_padded}.json"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return {
            "sic_description": data.get("sicDescription", ""),
            "business_address": data.get("addresses", {}).get("business", {}).get("city", ""),
            "state_of_incorporation": data.get("stateOfIncorporation", ""),
            "fiscal_year_end": data.get("fiscalYearEnd", ""),
        }
    except Exception:
        return None


def search_recent_form_d_georgia(days_back: int = 30) -> list[dict]:
    """Convenience: Get all recent Form D filings from Georgia companies."""
    return search_funding_rounds(
        keywords=["technology", "software", "fintech", "payments", "data"],
        state="GA",
        days_back=days_back,
    )
