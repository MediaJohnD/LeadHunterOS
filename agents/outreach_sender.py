def __init__(self, db_pool):
    self.db_pool = db_pool

    # Gmail config
    self.gmail_address = os.environ.get("GMAIL_ADDRESS")
    self.gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    self.from_name = os.environ.get("GMAIL_FROM_NAME", "")

    # OutX config (LinkedIn)
    self.outx_key = os.environ.get("OUTX_API_KEY")
    self.outx_base = os.environ.get("OUTX_BASE_URL", "https://api.outx.ai/v1")

    # Redis for rate limiting
    self._redis: Optional[aioredis.Redis] = None

    log.info(
        "OutreachSender initialized",
        gmail=bool(self.gmail_address),
        outx=bool(self.outx_key),
    )

async def _get_redis(self) -> aioredis.Redis:
    """Lazy Redis connection."""
    if not self._redis:
        self._redis = aioredis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            encoding="utf-8",
            decode_responses=True,
        )
    return self._redis

async def send(self, lead_id: str, campaign_id: Optional[str] = None) -> dict:
    """
    Main send orchestration — loads lead from DB, sends via appropriate channel.

    Returns:
      {
        "sent": bool,
        "channel": str,
        "reason": str,
        "message_id": str (if sent)
      }
    """
    # Load lead from database
    lead = await self._load_lead(lead_id)
    if not lead:
        return {"sent": False, "channel": None, "reason": "lead_not_found"}

    # Load outreach message from database
    outreach = await self._load_pending_outreach(lead_id)
    if not outreach:
        return {"sent": False, "channel": None, "reason": "no_pending_outreach"}

    channel = outreach.get("channel") or lead.get("recommended_channel", "email")
    result = {"sent": False, "channel": channel, "reason": "not_attempted"}

    if channel in ("email", "both") and lead.get("email"):
        email_result = await self.send_email(
            to_email=lead["email"],
            to_name=lead.get("full_name", ""),
            subject=outreach.get("email_subject", ""),
            body=outreach.get("email_body", ""),
            lead_id=lead_id,
            campaign_id=campaign_id,
        )
        if email_result["sent"]:
            result = email_result
            result["channel"] = "email"

    if channel in ("linkedin", "both") and lead.get("linkedin_url"):
        li_result = await self.send_linkedin_dm(
            linkedin_url=lead["linkedin_url"],
            message=outreach.get("linkedin_note") or outreach.get("linkedin_inmail", ""),
            lead_id=lead_id,
            campaign_id=campaign_id,
        )
        if li_result["sent"]:
            result = li_result
            result["channel"] = "linkedin"

    # Update lead status if sent
    if result["sent"]:
        await self._mark_lead_contacted(lead_id, campaign_id)

    return result

async def send_email(
    self,
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
    lead_id: str,
    campaign_id: Optional[str] = None,
) -> dict:
    """
    Send a cold email via Gmail SMTP.
    Enforces daily limit.
    """
    if not self.gmail_address or not self.gmail_password:
        log.error("gmail_not_configured")
        return {"sent": False, "reason": "gmail_not_configured"}

    if not subject or not body:
        return {"sent": False, "reason": "missing_subject_or_body"}

    # Check daily email limit
    redis = await self._get_redis()
    daily_key = f"outreach:email:count:{date.today().isoformat()}"
    current_count = int(await redis.get(daily_key) or 0)

    if current_count >= DAILY_EMAIL_LIMIT:
        log.warning(
            "email_daily_limit_reached",
            limit=DAILY_EMAIL_LIMIT,
            count=current_count,
        )
        return {"sent": False, "reason": "daily_limit_reached"}

    try:
        # Build email
        msg = MIMEMultipart("alternative")
        msg["From"] = (
            f"{self.from_name} <{self.gmail_address}>"
            if self.from_name
            else self.gmail_address
        )
        msg["To"] = f"{to_name} <{to_email}>" if to_name else to_email
        msg["Subject"] = subject

        # Add unsubscribe header (good practice for cold email)
        msg["List-Unsubscribe"] = f"<mailto:{self.gmail_address}?subject=unsubscribe>"

        # Plain text version
        msg.attach(MIMEText(body, "plain"))

        # Send via Gmail SMTP
        await aiosmtplib.send(
            msg,
            hostname="smtp.gmail.com",
            port=587,
            start_tls=True,
            username=self.gmail_address,
            password=self.gmail_password,
            timeout=30,
        )

        # Increment daily counter (expire at end of day)
        pipe = redis.pipeline()
        pipe.incr(daily_key)
        pipe.expire(daily_key, 86400)  # 24 hours
        await pipe.execute()

        # Log to database
        message_id = await self._log_send(
            lead_id=lead_id,
            campaign_id=campaign_id,
            channel="email",
            recipient=to_email,
            subject=subject,
            body=body,
            status="sent",
        )

        log.info(
            "email_sent",
            to=to_email,
            subject=subject[:50],
            lead_id=lead_id,
            daily_count=current_count + 1,
        )

        return {"sent": True, "channel": "email", "message_id": str(message_id)}

    except aiosmtplib.SMTPException as e:
        log.error("smtp_error", error=str(e), to=to_email)
        await self._log_send(
            lead_id=lead_id,
            campaign_id=campaign_id,
            channel="email",
            recipient=to_email,
            subject=subject,
            body=body,
            status="failed",
            error=str(e),
        )
        return {"sent": False, "reason": f"smtp_error: {str(e)}"}

    except Exception as e:
        log.error("email_send_error", error=str(e), to=to_email)
        return {"sent": False, "reason": str(e)}

@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=10))
async def send_linkedin_dm(
    self,
    linkedin_url: str,
    message: str,
    lead_id: str,
    campaign_id: Optional[str] = None,
) -> dict:
    """
    Send LinkedIn connection request with note via OutX API.
    OutX free tier supports basic LinkedIn automation.
    Docs: https://docs.outx.ai
    """
    if not self.outx_key:
        log.error("outx_not_configured")
        return {"sent": False, "reason": "outx_not_configured"}

    if not message:
        return {"sent": False, "reason": "missing_message"}

    # LinkedIn connection notes have 300 char limit
    if len(message) > 300:
        message = message[:297] + "..."

    # Check daily LinkedIn limit
    redis = await self._get_redis()
    daily_key = f"outreach:linkedin:count:{date.today().isoformat()}"
    current_count = int(await redis.get(daily_key) or 0)

    if current_count >= DAILY_LINKEDIN_LIMIT:
        log.warning(
            "linkedin_daily_limit_reached",
            limit=DAILY_LINKEDIN_LIMIT,
            count=current_count,
        )
        return {"sent": False, "reason": "daily_limit_reached"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.outx_base}/connections/send",
                headers={
                    "Authorization": f"Bearer {self.outx_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "profile_url": linkedin_url,
                    "message": message,
                    "track": True,  # OutX tracking for open rates
                },
            )

        if response.status_code == 429:
            log.warning("outx_rate_limited")
            return {"sent": False, "reason": "outx_rate_limited"}

        if response.status_code not in (200, 201, 202):
            log.error(
                "outx_error",
                status=response.status_code,
                body=response.text[:300],
            )
            return {
                "sent": False,
                "reason": f"outx_error_{response.status_code}",
            }

        # Increment daily counter
        pipe = redis.pipeline()
        pipe.incr(daily_key)
        pipe.expire(daily_key, 86400)
        await pipe.execute()

        # Log to database
        message_id = await self._log_send(
            lead_id=lead_id,
            campaign_id=campaign_id,
            channel="linkedin",
            recipient=linkedin_url,
            subject=None,
            body=message,
            status="sent",
        )

        log.info(
            "linkedin_dm_sent",
            profile=linkedin_url[:60],
            lead_id=lead_id,
            daily_count=current_count + 1,
        )

        return {"sent": True, "channel": "linkedin", "message_id": str(message_id)}

    except httpx.TimeoutException:
        log.error("outx_timeout", linkedin_url=linkedin_url)
        return {"sent": False, "reason": "outx_timeout"}

# -------------------------------------------------------------------------
# Database helpers
# -------------------------------------------------------------------------
async def _load_lead(self, lead_id: str) -> Optional[dict]:
    """Load a lead record from the database."""
    async with self.db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM leads WHERE id = $1", lead_id
        )
        return dict(row) if row else None

async def _load_pending_outreach(self, lead_id: str) -> Optional[dict]:
    """Load the latest pending outreach message for a lead."""
    async with self.db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM outreach_messages
            WHERE lead_id = $1 AND status = 'pending'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            lead_id,
        )
        if not row:
            return None
        return dict(row)

async def _mark_lead_contacted(
    self, lead_id: str, campaign_id: Optional[str]
) -> None:
    """Update lead status to 'contacted'."""
    async with self.db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE leads
            SET status = 'contacted',
                last_contacted_at = NOW(),
                campaign_id = COALESCE($2, campaign_id)
            WHERE id = $1
            """,
            lead_id,
            campaign_id,
        )

async def _log_send(
    self,
    lead_id: str,
    campaign_id: Optional[str],
    channel: str,
    recipient: str,
    subject: Optional[str],
    body: str,
    status: str,
    error: Optional[str] = None,
) -> str:
    """Log a send attempt to the database. Returns the record ID."""
    async with self.db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO outreach_sends (
                lead_id, campaign_id, channel, recipient,
                subject, body, status, error, sent_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            RETURNING id
            """,
            lead_id,
            campaign_id,
            channel,
            recipient,
            subject,
            body[:5000],
            status,
            error,
        )
        return str(row["id"])
