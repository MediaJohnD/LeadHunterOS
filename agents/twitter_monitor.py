def __init__(self, db_pool, redis_client):
    self.db_pool = db_pool
    self.redis = redis_client
    self.apify_token = os.environ.get("APIFY_API_TOKEN")
    self.actor_id = os.environ.get(
        "APIFY_TWITTER_ACTOR_ID", "apidojo/tweet-scraper"
    )
    self.base_url = "https://api.apify.com/v2"
    self.queries = TWITTER_SEARCH_QUERIES
    self.exclude = [kw.lower() for kw in EXCLUDE_KEYWORDS]

    log.info("TwitterMonitor initialized", queries=len(TWITTER_SEARCH_QUERIES))

async def run(self) -> int:
    """
    Run Twitter scraping for all configured queries.
    Returns total number of new signals found.
    """
    if not self.apify_token:
        log.warning("APIFY_API_TOKEN not set — skipping Twitter monitor")
        return 0

    log.info("TwitterMonitor.run() started")
    total_found = 0

    async with httpx.AsyncClient(timeout=120.0) as client:
        for query in self.queries:
            try:
                tweets = await self._scrape_query(client, query)
                for tweet in tweets:
                    if await self._process_tweet(tweet, query):
                        total_found += 1
                log.info("twitter_query_done", query=query, tweets=len(tweets))
            except Exception as e:
                log.error("twitter_query_failed", query=query, error=str(e))
                continue

            # Rate limit between queries to be a good citizen
            await asyncio.sleep(2)

    log.info("TwitterMonitor.run() complete", total_signals=total_found)
    return total_found

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=30),
)
async def _scrape_query(self, client: httpx.AsyncClient, query: str) -> list:
    """
    Run an Apify actor scrape for a single search query.
    Uses synchronous run endpoint (waits for completion).
    """
    run_response = await client.post(
        f"{self.base_url}/acts/{self.actor_id}/run-sync-get-dataset-items",
        params={"token": self.apify_token},
        json={
            "searchTerms": [query],
            "maxTweets": 20,  # Keep costs low — 20 tweets per query
            "lang": "en",
            "sort": "Latest",  # Recency matters for intent signals
        },
        timeout=90.0,
    )

    if run_response.status_code == 402:
        log.error("apify_payment_required", query=query)
        return []

    if run_response.status_code != 200:
        log.error(
            "apify_request_failed",
            query=query,
            status=run_response.status_code,
            body=run_response.text[:500],
        )
        return []

    data = run_response.json()
    return data if isinstance(data, list) else []

async def _process_tweet(self, tweet: dict, search_query: str) -> bool:
    """
    Process a single tweet. Returns True if it's a new qualifying signal.
    """
    tweet_id = tweet.get("id") or tweet.get("tweet_id") or tweet.get("tweetId")
    if not tweet_id:
        return False

    # Dedup check
    dedup_key = f"twitter:seen:{self._fingerprint(str(tweet_id))}"
    if await self.redis.exists(dedup_key):
        return False

    # Get tweet text
    text = tweet.get("text") or tweet.get("full_text") or tweet.get("content", "")

    # Filter out excluded keywords
    text_lower = text.lower()
    if any(kw in text_lower for kw in self.exclude):
        await self.redis.setex(dedup_key, DEDUP_TTL, "1")
        return False

    # Filter out retweets (usually not original intent signals)
    if text.startswith("RT @"):
        await self.redis.setex(dedup_key, DEDUP_TTL, "1")
        return False

    # Extract author details
    author = tweet.get("author") or tweet.get("user") or {}
    author_username = (
        author.get("userName")
        or author.get("screen_name")
        or tweet.get("username", "unknown")
    )
    author_name = (
        author.get("name")
        or author.get("displayName")
        or author_username
    )
    author_followers = (
        author.get("followers")
        or author.get("followers_count")
        or 0
    )
    author_bio = author.get("description") or author.get("bio") or ""

    # Calculate intent score
    intent_score = self._calculate_intent_score(tweet, search_query, author)

    signal_data = {
        "source": "twitter",
        "source_id": str(tweet_id),
        "url": tweet.get("url") or f"https://twitter.com/i/web/status/{tweet_id}",
        "text": text[:1000],
        "author_username": author_username,
        "author_name": author_name,
        "author_followers": author_followers,
        "author_bio": author_bio[:500],
        "likes": tweet.get("likeCount") or tweet.get("favorite_count") or 0,
        "retweets": tweet.get("retweetCount") or tweet.get("retweet_count") or 0,
        "created_at": tweet.get("createdAt") or tweet.get("created_at", ""),
        "search_query": search_query,
        "intent_score": intent_score,
    }

    await self._save_signal(signal_data)
    await self._try_create_lead(signal_data)
    await self.redis.setex(dedup_key, DEDUP_TTL, "1")

    log.info(
        "twitter_signal_found",
        username=author_username,
        intent_score=intent_score,
        query=search_query,
    )

    return True

def _calculate_intent_score(self, tweet: dict, query: str, author: dict) -> int:
    """
    Score the buying intent of a tweet.
    """
    score = 40  # Base

    text = (tweet.get("text") or "").lower()

    # Question marks = active looking
    if "?" in text:
        score += 10

    # Specific pain = stronger signal
    high_intent_phrases = [
        "switching from", "need alternative", "looking for",
        "recommend", "evaluating", "tired of", "replacing",
    ]
    for phrase in high_intent_phrases:
        if phrase in text:
            score += 15
            break

    # Follower count as proxy for decision-maker authority
    followers = (
        author.get("followers")
        or author.get("followers_count")
        or 0
    )
    if followers > 5000:
        score += 10
    elif followers > 1000:
        score += 5

    # Recent engagement
    likes = tweet.get("likeCount") or tweet.get("favorite_count") or 0
    if likes > 50:
        score += 10
    elif likes > 10:
        score += 5

    # Bio signals (job title in bio = B2B buyer)
    bio = (author.get("description") or "").lower()
    b2b_signals = ["founder", "ceo", "vp", "head of", "director", "cro", "cmo"]
    if any(s in bio for s in b2b_signals):
        score += 15

    return min(score, 100)

async def _try_create_lead(self, signal_data: dict) -> None:
    """
    Attempt to create a lead record from a Twitter signal.
    The author becomes a lead candidate for enrichment.
    """
    author_username = signal_data.get("author_username")
    if not author_username or author_username == "unknown":
        return

    async with self.db_pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT id FROM leads WHERE twitter_handle = $1",
            author_username,
        )
        if existing:
            return

        await conn.execute(
            """
            INSERT INTO leads (
                twitter_handle, full_name, source, status, raw_signal_data, created_at
            ) VALUES ($1, $2, 'twitter', 'new', $3, NOW())
            ON CONFLICT DO NOTHING
            """,
            author_username,
            signal_data.get("author_name", ""),
            json.dumps(signal_data),
        )

async def _save_signal(self, signal_data: dict) -> None:
    """Persist signal to PostgreSQL."""
    async with self.db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO signals (source, source_id, raw_data, intent_score, created_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (source, source_id) DO NOTHING
            """,
            signal_data["source"],
            signal_data["source_id"],
            json.dumps(signal_data),
            signal_data["intent_score"],
        )

def _fingerprint(self, tweet_id: str) -> str:
    return hashlib.sha256(f"twitter:{tweet_id}".encode()).hexdigest()[:16]

async def process_signal(self, raw_data: dict, metadata: dict) -> None:
    """Called from FastAPI when n8n pushes a Twitter signal."""
    tweet_id = str(raw_data.get("id") or raw_data.get("source_id", ""))
    if not tweet_id:
        return

    query = metadata.get("search_query", "")
    await self._process_tweet(raw_data, query)
