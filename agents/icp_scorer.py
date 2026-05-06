"""
LeadHunterOS - ICP Scorer Agent
Uses Claude Haiku 3.5 to score leads against your Ideal Customer Profile.
Returns structured JSON: score (0-100), fit_reason, urgency, recommended_channel.

Score thresholds:
  70-100: Immediate outreach
  41-69:  Nurture queue
  0-40:   Discard
"""

import json
import logging
import os
from typing import Optional
from pydantic import BaseModel
import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Initialize Anthropic client
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# ICP configuration from environment
ICP_CONFIG = {
    "job_titles": os.environ.get("ICP_JOB_TITLES", "CEO,VP of Sales,Founder,Head of Growth").split(","),
    "industries": os.environ.get("ICP_INDUSTRIES", "SaaS,B2B Software,Technology").split(","),
    "company_size_min": int(os.environ.get("ICP_COMPANY_SIZE_MIN", 10)),
    "company_size_max": int(os.environ.get("ICP_COMPANY_SIZE_MAX", 500)),
    "score_threshold_immediate": int(os.environ.get("ICP_SCORE_THRESHOLD_IMMEDIATE", 70)),
    "score_threshold_nurture": int(os.environ.get("ICP_SCORE_THRESHOLD_NURTURE", 41)),
}

# Pydantic models for structured output
class ICPScore(BaseModel):
    score: int  # 0-100
    fit_reason: str  # Human-readable explanation
    urgency: str  # low / medium / high
    recommended_channel: str  # linkedin / email / both
    disqualify_reason: Optional[str] = None  # If score < 41

class LeadInput(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[int] = None
    signal_source: Optional[str] = None  # reddit/twitter/linkedin/web
    signal_text: Optional[str] = None  # The actual post/comment/activity
    linkedin_url: Optional[str] = None
    email: Optional[str] = None
    location: Optional[str] = None

# System prompt with ICP context (cached for cost reduction)
SYSTEM_PROMPT = f"""You are a B2B sales intelligence AI for LeadHunterOS.
Your job is to score leads against the Ideal Customer Profile (ICP) below.

ICP DEFINITION:
- Target Job Titles: {', '.join(ICP_CONFIG['job_titles'])}
- Target Industries: {', '.join(ICP_CONFIG['industries'])}
- Company Size: {ICP_CONFIG['company_size_min']}-{ICP_CONFIG['company_size_max']} employees
- Intent Signals: pain points, switching tools, evaluating solutions, rapid growth, hiring

SCORING RULES:
- Score 70-100: Strong ICP fit + active buying intent signal
- Score 41-69: Partial ICP fit or weak signal (nurture)
- Score 0-40: Poor fit or no intent signal (discard)

URGENCY:
- high: actively looking/evaluating now (mentions "looking for", "switching", "demo", "pricing")
- medium: growth signals, recent job change, funding
- low: general discussion, no clear near-term need

CHANNEL:
- linkedin: LinkedIn URL available and they are active there
- email: email available but not LinkedIn
- both: both channels available

Always respond with ONLY valid JSON. No markdown, no explanation outside the JSON."""

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
async def score_lead(lead: LeadInput) -> ICPScore:
    """
    Score a lead against the ICP using Claude Haiku 3.5.
    Uses prompt caching to reduce costs by ~90% on repeated calls.
    """
    lead_context = f"""
Score this lead:

PERSON:
- Name: {lead.name or 'Unknown'}
- Title: {lead.title or 'Unknown'}
- Company: {lead.company or 'Unknown'}
- Industry: {lead.industry or 'Unknown'}
- Company Size: {lead.company_size or 'Unknown'} employees
- Location: {lead.location or 'Unknown'}

SIGNAL:
- Source: {lead.signal_source or 'Unknown'}
- Activity: {lead.signal_text or 'No signal text'}

CONTACT:
- LinkedIn: {'Available' if lead.linkedin_url else 'Not available'}
- Email: {'Available' if lead.email else 'Not available'}

Return JSON in this exact format:
{{
  "score": <integer 0-100>,
  "fit_reason": "<brief explanation of why this score>",
  "urgency": "<low|medium|high>",
  "recommended_channel": "<linkedin|email|both>",
  "disqualify_reason": "<only if score < 41, else null>"
}}"""

    try:
        response = client.messages.create(
            model=os.environ.get("CLAUDE_HAIKU_MODEL", "claude-haiku-3-5-20241022"),
            max_tokens=256,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"}  # Cache system prompt
                }
            ],
            messages=[
                {"role": "user", "content": lead_context}
            ]
        )

        raw_json = response.content[0].text.strip()
        # Handle potential markdown code blocks
        if raw_json.startswith("```"):
            raw_json = raw_json.split("```")[1]
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]
        
        data = json.loads(raw_json)
        score = ICPScore(**data)
        
        logger.info(
            f"Scored lead: {lead.name or 'Unknown'} @ {lead.company or 'Unknown'} "
            f"-> {score.score}/100 ({score.urgency} urgency, {score.recommended_channel})"
        )
        return score

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response as JSON: {e}")
        # Return a low score on parse failure rather than crashing
        return ICPScore(
            score=0,
            fit_reason="Failed to parse AI response",
            urgency="low",
            recommended_channel="email",
            disqualify_reason="AI scoring error"
        )
    except Exception as e:
        logger.error(f"ICP scoring error: {e}")
        raise

def get_lead_action(score: ICPScore) -> str:
    """Determine what action to take based on score."""
    if score.score >= ICP_CONFIG["score_threshold_immediate"]:
        return "immediate_outreach"
    elif score.score >= ICP_CONFIG["score_threshold_nurture"]:
        return "nurture_queue"
    else:
        return "discard"

# Sync wrapper for n8n webhook calls
def score_lead_sync(lead_data: dict) -> dict:
    """Synchronous wrapper for use in n8n HTTP Request nodes."""
    import asyncio
    lead = LeadInput(**lead_data)
    loop = asyncio.new_event_loop()
    try:
        score = loop.run_until_complete(score_lead(lead))
        action = get_lead_action(score)
        return {
            **score.model_dump(),
            "action": action,
            "lead_name": lead.name,
            "lead_company": lead.company
        }
    finally:
        loop.close()
