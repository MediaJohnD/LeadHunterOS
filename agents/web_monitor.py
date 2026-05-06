Example: scrape_google_maps("SaaS company", "San Francisco, CA")

Install the scraper:
    git clone https://github.com/omkarcloud/google-maps-scraper
    cd google-maps-scraper && pip install -r requirements.txt
"""
import subprocess
import tempfile

log.info("google_maps_scrape_started", query=search_query, location=location)

output_file = tempfile.mktemp(suffix=".json")

try:
    result = subprocess.run(
        [
            "python",
            "google-maps-scraper/main.py",
            "--query", f"{search_query} {location}",
            "--max", str(max_results),
            "--output", output_file,
            "--format", "json",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        log.error("google_maps_scraper_failed", stderr=result.stderr[:500])
        return []

    with open(output_file) as f:
        businesses = json.load(f)

    leads = []
    async with db_pool.acquire() as conn:
        for biz in businesses:
            name = biz.get("name", "")
            phone = biz.get("phone", "")
            website = biz.get("website", "")
            address = biz.get("address", "")
            rating = biz.get("rating", 0)
            reviews = biz.get("reviews", 0)

            if not name:
                continue

            await conn.execute(
                """
                INSERT INTO leads (
                    company_name, phone, website, address, source, status,
                    raw_signal_data, created_at
                ) VALUES ($1, $2, $3, $4, 'google_maps', 'new', $5, NOW())
                ON CONFLICT DO NOTHING
                """,
                name, phone, website, address,
                json.dumps({"rating": rating, "reviews": reviews, "query": search_query}),
            )
            leads.append({"name": name, "website": website, "phone": phone})

    log.info("google_maps_scrape_complete", businesses=len(leads))
    return leads

except subprocess.TimeoutExpired:
    log.error("google_maps_scraper_timeout")
    return []
except FileNotFoundError:
    log.error(
        "google_maps_scraper_not_found",
        hint="Run: git clone https://github.com/omkarcloud/google-maps-scraper",
    )
    return []
finally:
    import os as _os
    if _os.path.exists(output_file):
        _os.remove(output_file)
