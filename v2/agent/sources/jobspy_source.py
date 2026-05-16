"""jobspy_source.py - Job board scraping via JobSpy (GitHub: speedyapply/JobSpy)

Scrapes LinkedIn, Indeed, Google Jobs, ZipRecruiter with NO login, NO API key.
Job postings = hiring signal = company is growing = buying signal.

Install: pip install jobspy
GitHub: https://github.com/speedyapply/JobSpy
"""

from __future__ import annotations

from typing import Any

from loguru import logger

import config

# Buying signal keywords that indicate active media/ad spend
MEDIA_KEYWORDS = [
    "media planner", "media buyer", "programmatic", "paid media",
    "media strategy", "dv360", "trade desk", "display advertising",
    "social media advertising", "performance marketing", "digital advertising",
    "demand side", "DSP", "ad operations", "paid social", "paid search",
]


def search_jobs(
    job_titles: list[str],
    location: str = "Atlanta, GA",
    hours_old: int = 168,  # 7 days
    results_wanted: int = 50,
) -> list[dict[str, Any]]:
    """Search jobs across LinkedIn, Indeed, Google, ZipRecruiter.

    No API key required. No login required.
    Returns structured job/company data usable as leads.
    """
    try:
        from jobspy import scrape_jobs
    except ImportError:
        logger.warning("jobspy not installed. Run: pip install jobspy")
        return []

    leads = []
    search_term = " OR ".join(f'"{t}"' for t in job_titles[:5])
    site_names = [site.strip() for site in config.JOBSPY_SITES.split(",") if site.strip()]
    if not site_names:
        site_names = ["linkedin", "indeed", "google"]

    total_jobs = 0
    for site_name in site_names:
        try:
            logger.info(f"JobSpy searching: {search_term} in {location} via {site_name}")
            jobs = scrape_jobs(
                site_name=[site_name],
                search_term=search_term,
                location=location,
                results_wanted=results_wanted,
                hours_old=hours_old,
                country_indeed="USA",
            )
        except Exception as e:
            logger.warning(f"JobSpy search failed for {site_name}: {e}")
            continue

        if jobs is None or len(jobs) == 0:
            logger.info(f"JobSpy returned no rows for {site_name}")
            continue

        total_jobs += len(jobs)
        for _, row in jobs.iterrows():
            title = str(row.get("title", "") or "")
            company = str(row.get("company", "") or "")
            loc = str(row.get("location", "") or "")
            job_url = str(row.get("job_url", "") or "")
            description = str(row.get("description", "") or "")
            date_posted = str(row.get("date_posted", "") or "")
            site = str(row.get("site", "") or site_name)
            min_amount = row.get("min_amount", None)
            max_amount = row.get("max_amount", None)

            if not company or not title:
                continue

            desc_lower = description.lower()
            keyword_hits = [kw for kw in MEDIA_KEYWORDS if kw in desc_lower]
            buying_signal_score = min(len(keyword_hits) * 15, 60)

            lead = {
                "company": company,
                "job_title": title,
                "location": loc,
                "job_url": job_url,
                "job_source": site,
                "date_posted": date_posted,
                "buying_signal_score": buying_signal_score,
                "buying_signal_keywords": keyword_hits,
                "salary_range": f"${min_amount}-${max_amount}" if min_amount and max_amount else "",
                "description_snippet": description[:300] if description else "",
                "source": "jobspy",
            }
            leads.append(lead)

    if total_jobs == 0:
        logger.warning("JobSpy returned no results across all configured sites")
        return []
    logger.info(f"JobSpy found {total_jobs} job postings across {site_names}")

    # Deduplicate by company name
    seen = set()
    unique = []
    for lead in leads:
        key = lead["company"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(lead)

    logger.info(f"JobSpy returning {len(unique)} unique companies")
    return unique


def search_jobs_by_icp(
    icp_keywords: list[str],
    location: str = "United States",
    hours_old: int = 720,
    results_wanted: int = 50,
) -> list[dict[str, Any]]:
    """Search jobs with ICP keywords and return deduplicated company signals."""
    return search_jobs(
        job_titles=icp_keywords,
        location=location,
        hours_old=hours_old,
        results_wanted=results_wanted,
    )


def extract_hiring_signals(jobs: list[dict]) -> list[dict]:
    """Identify companies with strong hiring signals (multiple open roles).

    A company posting 3+ roles simultaneously = strong growth signal.
    """
    from collections import Counter
    company_counts = Counter(j["company"] for j in jobs)
    signals = []
    for company, count in company_counts.most_common(20):
        if count >= 2:
            company_jobs = [j for j in jobs if j["company"] == company]
            signals.append({
                "company": company,
                "open_roles": count,
                "roles": [j["job_title"] for j in company_jobs],
                "location": company_jobs[0]["location"],
                "hiring_signal_strength": "HIGH" if count >= 5 else "MEDIUM" if count >= 3 else "LOW",
                "source": "jobspy_hiring_signal",
            })
    return signals
