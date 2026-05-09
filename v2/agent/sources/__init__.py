"""LeadHunterOS v2 - sources package.

Zero-signup data sources (no API key required for core functionality).

LinkedIn is deliberately NOT a primary source - it is one-of-N via JobSpy
(no-login job data only), never for profile scraping.

Source inventory - 17 signal keys across 5 modules:
  jobspy_source        : LinkedIn job data (no-login), Indeed, Google Jobs, ZipRecruiter
  edgar_source         : SEC EDGAR Form D funding filings (US government public data)
  signals_source       : HN, Reddit, Google News, GitHub, ProductHunt, RemoteOK
  enrich_source        : Email patterns, MX verify, website metadata, RDAP, Clearbit
  public_profiles_source : Wellfound, Crunchbase News, company Team pages,
                           Sessionize speakers, ORCID CC0, Glassdoor news

Layer compliance:
  Layer 1: 17 signal keys, LinkedIn one-of-N not the source
  Layer 2: No login, no cookies, no fake accounts on any source
  Layer 3: PUBLIC_FIELD_ALLOWLIST in tools.py drops sensitive fields at save
  Layer 4: Opt-out / DSAR - see ACCEPTABLE_USE.md (stub provided)
  Layer 5: Use-case restrictions - see ACCEPTABLE_USE.md
  Layer 6: source_url + observed_at recorded on every record
"""

from .jobspy_source import search_jobs, search_jobs_by_icp, extract_hiring_signals
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
from public_profiles_source import (
    get_all_public_profiles,
    search_wellfound_jobs,
    search_crunchbase_news,
    scrape_company_team_page,
    search_conference_speakers,
    search_orcid_profiles,
    search_glassdoor_news,
)

__all__ = [
    # jobs / hiring signals
    "search_jobs",
    "search_jobs_by_icp",
    "extract_hiring_signals",
    # funding signals
    "search_funding_rounds",
    "search_recent_form_d_georgia",
    # aggregated + per-source signals
    "get_all_signals",
    "search_hackernews",
    "search_reddit",
    "search_google_news",
    "search_github_repos",
    "search_producthunt_launches",
    "search_remoteok_jobs",
    # enrichment
    "enrich_lead",
    "enrich_leads_batch",
    "generate_email_candidates",
    "verify_mx",
    "scrape_website_metadata",
    # public cross-reference profiles (Layer 1 diversity)
    "get_all_public_profiles",
    "search_wellfound_jobs",
    "search_crunchbase_news",
    "scrape_company_team_page",
    "search_conference_speakers",
    "search_orcid_profiles",
    "search_glassdoor_news",
]
