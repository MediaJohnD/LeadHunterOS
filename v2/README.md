# LeadHunterOS v2 — Hermes Agent Edition

A production-ready, local-first AI lead hunting agent powered by a Hermes-style ReAct loop.
No n8n. No workflow orchestrators. Just a pure Python autonomous agent.

## Architecture

- **Agent**: Hermes-style ReAct loop (Thought → Action → Observation → repeat)
- **LLM Priority**: Local model via Ollama (Hermes 3, Mistral, etc.) → Claude API fallback
- **APIs**: US-based only (Apollo.io, Hunter.io, NewsAPI, Reddit via PRAW)
- **Database**: PostgreSQL (local or Supabase US region)
- **No**: n8n, Zapier, Make, or any non-US external orchestration

## Stack

| Layer | Tool |
|-------|------|
| Agent loop | Custom ReAct (Hermes-style) |
| Local LLM | Ollama + Hermes 3 / Mistral |
| Fallback LLM | Claude claude-3-5-haiku (Anthropic US) |
| Lead enrichment | Apollo.io API (US) |
| Email lookup | Hunter.io API (US) |
| Signal monitoring | Reddit (PRAW), NewsAPI (US) |
| Database | PostgreSQL |
| Scheduling | APScheduler (in-process) |

## Quickstart

```bash
# 1. Clone repo and enter v2 folder
cd v2

# 2. Install deps
pip install -r requirements.txt

# 3. Copy and fill env
cp .env.example .env

# 4. Start Ollama with Hermes 3
ollama pull adrienbrault/nous-hermes2pro-llama3-8b:Q4_K_M
ollama serve

# 5. Run database migrations
psql $DATABASE_URL < db/schema.sql

# 6. Launch agent
python run_agent.py
```

## Folder Structure

```
v2/
  agent/
    hermes_agent.py   # Core ReAct loop
    tools.py          # All tool definitions
  db/
    schema.sql        # PostgreSQL schema
  config.py           # Centralized config / env loading
  run_agent.py        # Entry point
  requirements.txt
  docker-compose.yml
  .env.example
```

## Key Design Decisions

1. **Local-first LLM**: Ollama runs locally — zero API cost for most operations
2. **Claude fallback only**: Used when local model confidence is low or task is complex
3. **US-only data sources**: Apollo, Hunter, Reddit, NewsAPI — all US-headquartered
4. **No orchestration middleware**: The agent itself manages retries, scheduling, and state
5. **Hermes ReAct pattern**: Structured XML-style tool calling compatible with Hermes 3 prompt format

## Environment Variables

See `.env.example` for full list. Key vars:
- `OLLAMA_BASE_URL` — local Ollama endpoint (default: http://localhost:11434)
- `OLLAMA_MODEL` — model name (default: adrienbrault/nous-hermes2pro-llama3-8b:Q4_K_M)
- `ANTHROPIC_API_KEY` — Claude fallback (optional)
- `APOLLO_API_KEY` — Lead enrichment
- `HUNTER_API_KEY` — Email finder
- `DATABASE_URL` — PostgreSQL connection string
- `NEWSAPI_KEY` — US news signals
