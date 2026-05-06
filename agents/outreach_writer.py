"""
LeadHunterOS - Outreach Writer Agent
Uses Claude Sonnet 4.5 to generate hyper-personalized outreach messages.
Generates LinkedIn DMs and email openers based on signal context and lead data.

Better than Gojiberry: Uses actual signal context (what they said/did) in messages.
Better than Unify: More conversational, less templated, higher reply rates.
"""

import logging
import os
from pydantic import BaseModel
from typing import Optional
import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


class OutreachMessage(BaseModel):
    linkedin_dm: Optional[str] = None   # Max 300 chars for connection request
    linkedin_followup: Optional[str] = None  # Follow-up DM
    email_subject: Optional[str] = None
    email_body: Optional[str] = None
    channel_recommended: str = "linkedin"

class OutreachInput(BaseModel):
    # Lead info
    name: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    industry: Optional[str] = None
    # Signal context
    signal_source: str = "reddit"  # reddit/twitter/linkedin/web
    signal_text: str = ""           # What they said/posted
    icp_score: int = 70
    urgency: str = "medium"
    fit_reason: str = ""
    # Sender context
    sender_name: Optional[str] = None
    sender_company: Optional[str] = None
    sender_value_prop: Optional[str] = None


SYSTEM_PROMPT = """
You are an expert B2B sales copywriter for LeadHunterOS.
Write hyper-personalized outreach that references EXACTLY what the prospect said or did.

RULES:
1. LinkedIn DM: Max 300 chars. Reference their specific post/activity. One clear CTA.
2. Email subject: 4-7 words, specific, not generic. No "Quick question" or "Following up".
3. Email body: 3-4 short paragraphs. Lead with THEIR problem, not your solution.
4. NEVER use: "I came across your profile", "I hope this finds you well", "synergy", "leverage"
5. Sound human, not like a bot. Mention the specific context.
6. Always end with a soft CTA: "Worth a quick chat?" or "Does this match what you're seeing?"

Return JSON only. No markdown."""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def write_outreach(input_data: OutreachInput) -> OutreachMessage:
    """
    Generate personalized outreach using Claude Sonnet.
    Includes both LinkedIn DM and email variants.
    """
    prompt = f"""Write personalized outreach for this lead:

LEAD:
- Name: {input_data.name or 'the prospect'}
- Title: {input_data.title or 'Unknown'}
- Company: {input_data.company or 'Unknown'}
- Industry: {input_data.industry or 'Unknown'}

WHAT THEY DID (use this as your hook):
- Source: {input_data.signal_source}
- Their post/activity: "{input_data.signal_text[:400]}"

ICP FIT CONTEXT:
- Score: {input_data.icp_score}/100
- Why they're a fit: {input_data.fit_reason}
- Urgency: {input_data.urgency}

OUR OFFERING:
- Sender: {input_data.sender_name or 'LeadHunterOS user'}
- Company: {input_data.sender_company or 'our company'}
- Value prop: {input_data.sender_value_prop or 'AI-powered lead intelligence and outreach automation'}

Return this exact JSON:
{{
  "linkedin_dm": "<300 char max - reference their SPECIFIC post/activity>",
  "linkedin_followup": "<follow up DM to send 3 days later if no reply>",
  "email_subject": "<4-7 words, specific to their situation>",
  "email_body": "<3-4 paragraphs, lead with their problem>",
  "channel_recommended": "<linkedin|email|both>"
}}"""

    response = client.messages.create(
        model=os.environ.get("CLAUDE_SONNET_MODEL", "claude-sonnet-4-5-20241022"),
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )

    import json
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    
    data = json.loads(raw)
    msg = OutreachMessage(**data)
    
    logger.info(
        f"Generated outreach for {input_data.name or 'lead'} @ {input_data.company or 'Unknown'} "
        f"via {msg.channel_recommended}"
    )
    return msg


def write_outreach_sync(input_dict: dict) -> dict:
    """Sync wrapper for n8n HTTP Request nodes."""
    import asyncio
    input_data = OutreachInput(**input_dict)
    loop = asyncio.new_event_loop()
    try:
        msg = loop.run_until_complete(write_outreach(input_data))
        return msg.model_dump()
    finally:
        loop.close()
