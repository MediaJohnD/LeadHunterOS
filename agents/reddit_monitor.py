"""
LeadHunterOS - Reddit Signal Monitor
Monitors subreddits for B2B buyer intent signals using asyncpraw.
Detects pain points, tool evaluations, competitor mentions, and buying signals.
"""

import asyncio
import logging
import os
import re
from datetime import datetime
from typing import Optional
import asyncpraw
import redis.asyncio as aioredis
import httpx

logger = logging.getLogger(__name__)

# 15 intent signal patterns - beats Gojiberry's LinkedIn-only approach
INTENT_PATTERNS = [
    r"\blooking for\b.{0,50}\b(crm|outreach|sales|tool|software|platform)\b",
    r"\brecommend.{0,30}\b(crm|outreach|automation|prospecting)\b",
    r"\bswitching from\b",
    r"\balternative to\b.{0,50}\b(salesforce|hubspot|apollo|outreach|salesloft)\b",
    r"\bhate\b.{0,30}\b(salesforce|hubspot|apollo|outreach)\b",
    r"\btoo expensive\b",
    r"\bcan.?t afford\b",
    r"\bfree alternative\b",
    r"\bjust (got|raised|closed).{0,30}\b(funding|round|seed|series)\b",
    r"\bhiring.{0,30}\b(sales|sdr|bdr|account executive)\b",
    r"\bscaling.{0,30}\b(sales|team|outreach)\b",
    r"\b(need|want|looking for).{0,30}\b(demo|pricing|trial)\b",
    r"\bevaluating\b.{0,50}\b(tools|platforms|software|options)\b",
    r"\bopen to\b.{0,30}\b(suggestions|recommendations|tools)\b",
    r"\bwhat.{0,20}\b(crm|outreach tool|prospecting tool)\b.{0,20}\buse\b",
]

SUBREDDITS = os.environ.get(
    "REDDIT_SUBREDDITS",
    "sales,entrepreneur,startups,SaaS,smallbusiness,b2b,marketing,leadgeneration"
).split(",")

APIFY_WEBHOOK_URL = os.environ.get("API_BASE_URL", "http://api:8000") + "/api/signals"


async def get_reddit_client() -> asyncpraw.Reddit:
    """Initialize async Reddit client."""
    return asyncpraw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "LeadHunterOS/1.0"),
        username=os.environ.get("REDDIT_USERNAME"),
        password=os.environ.get("REDDIT_PASSWORD"),
    )


def calculate_intent_score(text: str) -> tuple[int, list[str]]:
    """
    Score text against intent patterns.
    Returns (score 0-100, list of matched patterns).
    """
    text_lower = text.lower()
    matched = []
    for pattern in INTENT_PATTERNS:
        if re.search(pattern, text_lower):
            matched.append(pattern[:50])
    
    # Score based on matches (max 100)
    score = min(100, len(matched) * 15 + (20 if len(matched) >= 3 else 0))
    return score, matched


async def is_duplicate(redis_client: aioredis.Redis, post_id: str) -> bool:
    """Check Redis cache to avoid processing duplicate posts."""
    key = f"reddit:seen:{post_id}"
    exists = await redis_client.exists(key)
    if not exists:
        await redis_client.setex(key, 86400 * 7, "1")  # 7-day TTL
    return bool(exists)


async def send_signal_to_api(signal_data: dict) -> bool:
    """Send detected signal to FastAPI for enrichment and scoring."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(APIIFY_WEBHOOK_URL, json=signal_data)
            return response.status_code == 200
    except Exception as e:
        logger.error(f"Failed to send signal to API: {e}")
        return False


async def process_submission(submission, redis_client: aioredis.Redis, subreddit_name: str):
    """Process a Reddit post/submission for intent signals."""
    # Skip if already seen
    if await is_duplicate(redis_client, submission.id):
        return
    
    # Combine title + selftext for analysis
    full_text = f"{submission.title} {getattr(submission, 'selftext', '')}"
    intent_score, matched_patterns = calculate_intent_score(full_text)
    
    if intent_score < 15:  # Below minimum threshold
        return
    
    # Extract author info
    author = submission.author
    author_name = str(author) if author else "[deleted]"
    
    signal_data = {
        "source": "reddit",
        "source_id": submission.id,
        "subreddit": subreddit_name,
        "title": submission.title[:500],
        "text": full_text[:1000],
        "url": f"https://reddit.com{submission.permalink}",
        "author_username": author_name,
        "intent_score": intent_score,
        "matched_patterns": matched_patterns,
        "upvotes": submission.score,
        "created_utc": datetime.utcfromtimestamp(submission.created_utc).isoformat(),
        "signal_type": "reddit_post",
        "lead_data": {
            "name": author_name,
            "signal_source": "reddit",
            "signal_text": full_text[:500],
        }
    }
    
    success = await send_signal_to_api(signal_data)
    if success:
        logger.info(f"Reddit signal: r/{subreddit_name} - '{submission.title[:60]}' (score: {intent_score})")


async def monitor_subreddit(subreddit_name: str, reddit: asyncpraw.Reddit, redis_client: aioredis.Redis):
    """Stream new posts from a subreddit and detect intent signals."""
    logger.info(f"Starting monitor for r/{subreddit_name}")
    subreddit = await reddit.subreddit(subreddit_name)
    
    try:
        async for submission in subreddit.stream.submissions(skip_existing=True):
            await process_submission(submission, redis_client, subreddit_name)
            await asyncio.sleep(0.1)  # Rate limiting
    except Exception as e:
        logger.error(f"Error in r/{subreddit_name} stream: {e}")
        raise


async def run_reddit_monitor():
    """Main entry point - monitor all configured subreddits concurrently."""
    redis_client = aioredis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379")
    )
    reddit = await get_reddit_client()
    
    logger.info(f"Starting Reddit monitor for {len(SUBREDDITS)} subreddits")
    
    tasks = [
        monitor_subreddit(sub.strip(), reddit, redis_client)
        for sub in SUBREDDITS
    ]
    
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        await reddit.close()
        await redis_client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_reddit_monitor())
