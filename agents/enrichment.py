def __init__(self, db_pool):
    self.db_pool = db_pool
    self.apollo_key = os.environ.get("APOLLO_API_KEY")
    self.hunter_key = os.environ.get("HUNTER_API_KEY")
    self.pdl_key = os.environ.get("PDL_API_KEY")
    self.clearbit_key = os.environ.get("CLEARBIT_API_KEY")

    self.apollo_base = os.environ.get("APOLLO_BASE_URL", "https://api.apollo.io/v1")
    self.pdl_base = os.environ.get("PDL_BASE_URL", "https://api.peopledatalabs.com/v5")

    log.info(
        "EnrichmentAgent initialized",
        apollo=bool(self.apollo_key),
        hunter=bool(self.hunter_key),
        pdl=bool(self.pdl_key),
        clearbit=bool(self.clearbit_key),
    )

async def enrich(
    self,
    lead_id: Optional[str] = None,
    email: Optional[str] = None,
    linkedin_url: Optional[str] = None,
    company_domain: Optional[str] = None,
    name: Optional[str] = None,
    twitter_handle: Optional[str] = None,
) -> dict:
    """
    Main enrichment entry point.
    Returns merged enrichment data from all available sources.
    """
    enriched = {
        "lead_id": lead_id,
        "email": email,
        "linkedin_url": linkedin_url,
        "company_domain": company_domain,
        "name": name,
        "sources_used": [],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:

        # 1. Apollo.io — best for email + company data (free tier)
        if self.apollo_key and (email or linkedin_url or name):
            apollo_data = await self._enrich_apollo(
                client, email=email, linkedin_url=linkedin_url, name=name
            )
            if apollo_data:
                enriched = self._merge(enriched, apollo_data)
                enriched["sources_used"].append("apollo")
                log.info("apollo_enrichment_success", lead_id=lead_id)

        # 2. Hunter.io — find email by name + domain
        if (
            self.hunter_key
            and not enriched.get("email")
            and enriched.get("company_domain")
            and enriched.get("name")
        ):
            hunter_email = await self._find_email_hunter(
                client,
                name=enriched["name"],
                domain=enriched["company_domain"],
            )
            if hunter_email:
                enriched["email"] = hunter_email
                enriched["sources_used"].append("hunter")
                log.info("hunter_email_found", email=hunter_email, lead_id=lead_id)

        # 3. People Data Labs — deep enrichment (paid, $0.04/record)
        # Only use if Apollo didn't give us enough
        if (
            self.pdl_key
            and not self._is_sufficient(enriched)
            and (email or linkedin_url)
        ):
            pdl_data = await self._enrich_pdl(
                client, email=email, linkedin_url=linkedin_url
            )
            if pdl_data:
                enriched = self._merge(enriched, pdl_data)
                enriched["sources_used"].append("pdl")
                log.info("pdl_enrichment_success", lead_id=lead_id)

        # 4. Clearbit — company enrichment fallback (free for some endpoints)
        if (
            self.clearbit_key
            and not enriched.get("company_name")
            and enriched.get("company_domain")
        ):
            clearbit_data = await self._enrich_clearbit_company(
                client, domain=enriched["company_domain"]
            )
            if clearbit_data:
                enriched = self._merge(enriched, clearbit_data)
                enriched["sources_used"].append("clearbit")
                log.info("clearbit_enrichment_success", lead_id=lead_id)

    # Persist enrichment to database
    if lead_id:
        await self._update_lead(lead_id, enriched)

    log.info(
        "enrichment_complete",
        lead_id=lead_id,
        sources=enriched["sources_used"],
        has_email=bool(enriched.get("email")),
    )

    return enriched

# -------------------------------------------------------------------------
# Apollo.io enrichment
# -------------------------------------------------------------------------
@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
async def _enrich_apollo(
    self,
    client: httpx.AsyncClient,
    email: Optional[str] = None,
    linkedin_url: Optional[str] = None,
    name: Optional[str] = None,
) -> Optional[dict]:
    """
    Enrich via Apollo.io People API.
    Docs: https://apolloio.github.io/apollo-api-docs/
    """
    payload = {"api_key": self.apollo_key}

    if email:
        payload["email"] = email
    if linkedin_url:
        payload["linkedin_url"] = linkedin_url
    if name:
        first, *last = name.split(" ")
        payload["first_name"] = first
        payload["last_name"] = " ".join(last) if last else ""

    try:
        response = await client.post(
            f"{self.apollo_base}/people/match",
            json=payload,
        )

        if response.status_code == 429:
            log.warning("apollo_rate_limited")
            return None

        if response.status_code not in (200, 201):
            log.warning("apollo_error", status=response.status_code)
            return None

        data = response.json()
        person = data.get("person") or {}

        if not person:
            return None

        org = person.get("organization") or {}

        return {
            "email": person.get("email"),
            "first_name": person.get("first_name"),
            "last_name": person.get("last_name"),
            "full_name": f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
            "title": person.get("title"),
            "linkedin_url": person.get("linkedin_url"),
            "company_name": org.get("name"),
            "company_domain": org.get("primary_domain"),
            "company_size": org.get("estimated_num_employees"),
            "company_industry": org.get("industry"),
            "company_linkedin": org.get("linkedin_url"),
            "company_city": org.get("city"),
            "company_country": org.get("country"),
            "seniority": person.get("seniority"),
            "departments": person.get("departments", []),
        }

    except httpx.TimeoutException:
        log.error("apollo_timeout")
        return None

# -------------------------------------------------------------------------
# Hunter.io email finder
# -------------------------------------------------------------------------
@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
async def _find_email_hunter(
    self,
    client: httpx.AsyncClient,
    name: str,
    domain: str,
) -> Optional[str]:
    """
    Find professional email via Hunter.io Email Finder.
    25 free searches/mo on free tier.
    """
    first, *last = name.split(" ")
    params = {
        "api_key": self.hunter_key,
        "domain": domain,
        "first_name": first,
        "last_name": " ".join(last) if last else "",
    }

    try:
        response = await client.get(
            "https://api.hunter.io/v2/email-finder",
            params=params,
        )

        if response.status_code != 200:
            return None

        data = response.json()
        email_data = data.get("data") or {}
        email = email_data.get("email")
        confidence = email_data.get("score", 0)

        # Only trust emails with >70 confidence
        return email if confidence >= 70 else None

    except httpx.TimeoutException:
        log.error("hunter_timeout")
        return None

# -------------------------------------------------------------------------
# People Data Labs enrichment
# -------------------------------------------------------------------------
@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
async def _enrich_pdl(
    self,
    client: httpx.AsyncClient,
    email: Optional[str] = None,
    linkedin_url: Optional[str] = None,
) -> Optional[dict]:
    """
    Deep enrichment via People Data Labs Person API.
    Cost: ~$0.04 per successful match.
    Docs: https://docs.peopledatalabs.com/
    """
    params = {"api_key": self.pdl_key, "pretty": "true"}

    if email:
        params["email"] = email
    if linkedin_url:
        params["profile"] = linkedin_url

    try:
        response = await client.get(
            f"{self.pdl_base}/person/enrich",
            params=params,
        )

        if response.status_code == 404:
            return None  # No match (not billed for 404s)

        if response.status_code != 200:
            log.warning("pdl_error", status=response.status_code)
            return None

        data = response.json()

        if data.get("status") != 200:
            return None

        p = data.get("data") or {}

        # Extract company (first/current experience)
        experience = p.get("experience") or [{}]
        current_job = experience[0] if experience else {}
        company = current_job.get("company") or {}

        return {
            "email": (p.get("emails") or [{}])[0].get("address") if p.get("emails") else None,
            "first_name": p.get("first_name"),
            "last_name": p.get("last_name"),
            "full_name": p.get("full_name"),
            "title": current_job.get("title", {}).get("name"),
            "linkedin_url": (p.get("profiles") or [{}])[0].get("url") if p.get("profiles") else None,
            "company_name": company.get("name"),
            "company_domain": company.get("website"),
            "company_size": company.get("size"),
            "company_industry": company.get("industry"),
            "location_city": p.get("location_locality"),
            "location_country": p.get("location_country"),
            "skills": p.get("skills", [])[:10],
            "education": [
                e.get("school", {}).get("name")
                for e in (p.get("education") or [])
                if e.get("school")
            ][:3],
        }

    except httpx.TimeoutException:
        log.error("pdl_timeout")
        return None

# -------------------------------------------------------------------------
# Clearbit company enrichment (free for some endpoints)
# -------------------------------------------------------------------------
async def _enrich_clearbit_company(
    self,
    client: httpx.AsyncClient,
    domain: str,
) -> Optional[dict]:
    """
    Enrich company data via Clearbit.
    The /companies/find endpoint is free for basic data.
    """
    try:
        response = await client.get(
            "https://company.clearbit.com/v2/companies/find",
            params={"domain": domain},
            headers={"Authorization": f"Bearer {self.clearbit_key}"},
        )

        if response.status_code != 200:
            return None

        c = response.json()

        return {
            "company_name": c.get("name"),
            "company_domain": c.get("domain"),
            "company_size": c.get("metrics", {}).get("employees"),
            "company_industry": c.get("category", {}).get("industry"),
            "company_description": c.get("description", "")[:500],
            "company_linkedin": c.get("linkedin", {}).get("handle"),
            "company_twitter": c.get("twitter", {}).get("handle"),
            "company_city": c.get("geo", {}).get("city"),
            "company_country": c.get("geo", {}).get("country"),
            "company_founded": c.get("foundedYear"),
            "company_funding": c.get("metrics", {}).get("raised"),
            "company_tags": c.get("tags", [])[:5],
        }

    except httpx.TimeoutException:
        log.error("clearbit_timeout")
        return None

# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------
def _merge(self, base: dict, update: dict) -> dict:
    """
    Merge enrichment data — don't overwrite non-null values.
    Later sources fill in gaps, not override earlier findings.
    """
    result = dict(base)
    for key, value in update.items():
        if value is not None and value != "" and value != []:
            if not result.get(key):
                result[key] = value
    return result

def _is_sufficient(self, data: dict) -> bool:
    """
    Check if we have enough data to proceed to scoring.
    Minimum viable enrichment: email OR linkedin + title + company.
    """
    has_contact = bool(data.get("email") or data.get("linkedin_url"))
    has_identity = bool(data.get("title") and data.get("company_name"))
    return has_contact and has_identity

async def _update_lead(self, lead_id: str, enriched: dict) -> None:
    """Persist enriched data back to the leads table."""
    async with self.db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE leads SET
                email = COALESCE($2, email),
                linkedin_url = COALESCE($3, linkedin_url),
                full_name = COALESCE($4, full_name),
                title = COALESCE($5, title),
                company_name = COALESCE($6, company_name),
                company_domain = COALESCE($7, company_domain),
                company_size = COALESCE($8, company_size),
                company_industry = COALESCE($9, company_industry),
                enrichment_data = $10,
                enrichment_sources = $11,
                status = CASE WHEN status = 'new' THEN 'enriched' ELSE status END,
                enriched_at = NOW()
            WHERE id = $1
            """,
            lead_id,
            enriched.get("email"),
            enriched.get("linkedin_url"),
            enriched.get("full_name") or enriched.get("name"),
            enriched.get("title"),
            enriched.get("company_name"),
            enriched.get("company_domain"),
            str(enriched.get("company_size") or ""),
            enriched.get("company_industry"),
            json.dumps(enriched),
            json.dumps(enriched.get("sources_used", [])),
        )
