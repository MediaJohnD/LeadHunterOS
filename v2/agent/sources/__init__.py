"""LeadHunterOS v2 - sources package.

Zero-signup data sources (no API key required for core functionality):
  - jobspy_source   : Job listings via JobSpy (LinkedIn, Indeed, Google Jobs)
  - edgar_source    : SEC EDGAR Form D funding announcements
  - signals_source  : Buying signals (HN, Reddit, Google News, GitHub, ProductHunt, RemoteOK)
  - enrich_source   : Lead enrichment (email guess, MX verify, website scrape, RDAP)
"""

from .jobspy_source import search_jobs, search_jobs_by_icp
from .edgar_source import (
    search_funding_rounds,
    search_recent_form_d_georgia,
)
from .signals_source import (
    get_all_signals,
    search_hackernews,
    search_reddit,
    search_google_news,
    search_github_repos,
    search_producthunt_launches,
    search_remoteok_jobs,
)
from .enrich_source import (
    enrich_lead,
    enrich_leads_batch,
    generate_email_candidates,
    verify_mx,
    scrape_website_metadata,
)

__all__ = [
    # jobs
    "search_jobs",
    "search_jobs_by_icp",
    # funding
    "search_funding_rounds",
    "search_recent_form_d_georgia",
    # signals
    "get_all_signals",
    "search_hackernews",
    "search_reddit",
    "search_google_news",
    "search_github_repos",
    "search_producthunt_launches",
    "search_remoteok_jobs",
    # enrich
    "enrich_lead",
    "enrich_leads_batch",
    "generate_email_candidates",
    "verify_mx",
    "scrape_website_metadata",
]
