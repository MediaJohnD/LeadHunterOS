# LeadHunterOS v2 — True Hermes Agent Edition

> **Open-source autonomous B2B lead intelligence agent, optimized for high-quality discovery, enrichment, and CRM handoff.**
> Last audited: May 6, 2026

---

## Why LeadHunterOS v2

- Multi-source signal discovery with US-scope controls.
- Deterministic ICP scoring and qualification gates.
- Enrichment waterfall with provenance, confidence, and contact tiers.
- Entity graph, attribution fields, and operator suppression controls.
- Self-healing runtime behavior with health ledger and outcome learning.

---

## What Is This?

LeadHunterOS v2 is a **true Hermes Agent** — implementing the NousResearch Hermes function-calling standard with `<tools>` XML injection and `<tool_call>` XML response parsing, the same protocol used by Hermes Agent v2026.4.23 (27k+ GitHub stars).

It runs on **AMD hardware** using **Lemonade Server v10.3** (AMD's official open-source local LLM server, 3.7k stars), optimized for:
- Ryzen AI 3xx NPU (Strix/Kraken)
- Radeon RX 7800 / 9070+ (ROCm)
- Any AMD Ryzen with integrated GPU (Vulkan)

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│         LeadHunterOS v2 Agent Loop              │
│                                                  │
│  Objective → [HERMES REACT LOOP]                │
│    <tools> injected in system prompt              │
│    LLM emits <tool_call> XML                     │
│    Agent parses → dispatches → observes           │
│    Loop repeats until <final_answer>              │
└─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│              LLM ROUTING (Priority Order)          │
│                                                    │
│  1️⃣  Lemonade Server (AMD local - PRIMARY)        │
│      Qwen3-14B-Instruct-Q4_K_M (recommended)      │
│      http://localhost:13305/api/v1                 │
│                                                    │
│  2️⃣  Claude Pro / API (Anthropic US - heavy tasks) │
│      claude-opus-4 or claude-sonnet-4-5            │
│                                                    │
│  3️⃣  ChatGPT Plus / OpenAI API (US - fallback)    │
│      gpt-4.1 or gpt-4o                             │
│                                                    │
│  4️⃣  Perplexity Pro API (research tasks)           │
│      sonar-pro (with web search built in)          │
└─────────────────────────────────────────────────┘
```

---

## Stack (as of May 2026)

| Layer | Tool | Notes |
|-------|------|-------|
| **Agent protocol** | NousResearch Hermes Function-Calling | `<tools>` XML + `<tool_call>` XML |
| **Primary LLM** | Lemonade Server v10.3 + Qwen3-14B Q4 | AMD NPU/GPU/ROCm |
| **Heavy/Research tasks** | Claude Opus 4 / Sonnet 4.5 (Anthropic US) | Via API or Pro account |
| **Fallback LLM** | OpenAI GPT-4.1 / GPT-4o | Via API or Plus account |
| **Research mode** | Perplexity Sonar Pro | Real-time web search built-in |
| **Lead enrichment** | Public-source waterfall | Provider-safe, provenance-first |
| **Email lookup** | Public candidate + MX validation | Optional provider adapters |
| **Social signals** | Reddit PRAW (US) | Intent monitoring |
| **News signals** | NewsAPI.org (US) | Trigger event detection |
| **Database** | PostgreSQL | Local or Supabase US |
| **Scheduler** | Stdlib timed loop | No external orchestrator |

---

## Free / No-Login Signal Stack Rank (Hermes v2)

Priority order: intent strength > coverage > freshness > ease.  
Waterfall rule: run ranks 1-5 first (target 90% hit coverage) before optional sources.  
Policy: no paid APIs until free/no-login sources are exhausted.

| Rank | Source/tool | Status in v2 | Notes |
|---|---|---|---|
| 1 | Google X-ray (LinkedIn jobs/profiles) | Implemented (dispatcher layer) | `site:linkedin.com/jobs`, `site:linkedin.com/in` query fan-out |
| 2 | Crunchbase public | Implemented (news RSS) | Funding/team signal coverage via public feeds |
| 3 | Indeed/Glassdoor | Implemented (JobSpy + Glassdoor RSS) | Hiring velocity + workplace pain indicators |
| 4 | NewsAPI / Google News | Partial | Google News implemented; NewsAPI adapter pending |
| 5 | Reddit / GitHub search | Implemented | Pain + repo momentum signals |
| 6 | BuiltWith / Wappalyzer | Missing | Planned tech-stack enrichment source |
| 7 | G2 / Capterra | Missing | Planned review and buyer pain layer |
| 8 | X/Twitter company posts | Missing | Planned company activity pulse source |
| 9 | DuckDuckGo Instant API | Implemented | Lightweight broad-web signal recall |
| 10 | OpenCorporates / YellowPages | Missing | Planned firmographic verification layer |

Composite scoring uses deterministic components (`icp_fit`, `intent_strength`, `recency`, `evidence_confidence`) and blocks low-evidence leads at gate time.

---

## AMD Hardware Support

Lemonade Server v10.3 auto-detects and routes to best available backend:

| Your AMD Hardware | Backend | Recommended Model |
|---|---|---|
| Ryzen AI 3xx (Strix/Kraken) | NPU (Ryzen AI SW) | Qwen3-7B-Q4_K_M |
| Radeon RX 7800 / 9070+ | ROCm GPU | Qwen3-14B-Q4_K_M |
| Ryzen AI 7xxx/8xxx/2xx | Integrated GPU (Vulkan) | Qwen3-7B-Q4_K_M |
| Any Ryzen desktop | CPU fallback | Qwen3-4B-Q4_K_M |
| ASUS TUF RX 7600 | ROCm GPU | Qwen3-14B-Q4_K_M |

> Your ASUS TUF Gaming (Ryzen 7 7800X3D + RX 7600) and TUF FA707XV laptop (7940HS) are both fully supported.

---

## Quickstart

### 1. Install Lemonade Server (AMD)

```bash
# Windows one-click installer (recommended for AMD PCs)
# Download from: https://lemonade-server.ai
# OR pip install:
pip install lemonade-server

# Pull recommended model for LeadHunterOS
lemonade pull Qwen3-14B-Instruct-Q4_K_M
# Lighter option for 16GB RAM machines:
lemonade pull Qwen3-7B-Instruct-Q4_K_M

# Start server (auto-detects AMD hardware)
lemonade serve
# API now at: http://localhost:13305/api/v1
```

### 2. Setup LeadHunterOS v2

```bash
cd v2
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

### 3. Run the database

```bash
docker-compose up -d postgres
psql $DATABASE_URL < db/schema.sql
```

### 4. Launch the agent

```bash
# Single run (local AMD primary, auto-fallback)
python run_agent.py

# Scheduled (hourly)
python run_agent.py --schedule

# Force Claude for a harder task
python run_agent.py --llm claude --objective "Deep research: Find Series A SaaS companies hiring SDRs"

# Use Perplexity for research-heavy tasks
python run_agent.py --llm perplexity --objective "Find companies that just announced AI sales initiatives"
```

---

## Folder Structure

```
v2/
  agent/
    hermes_agent.py   # True Hermes function-calling agent loop
    tools.py          # Tool definitions with <tools> XML schema
    llm_router.py     # Multi-backend LLM routing
  db/
    schema.sql        # PostgreSQL schema
  config.py           # Centralized config
  run_agent.py        # Entry point with --llm flag
  requirements.txt
  docker-compose.yml
  .env.example
```

---

## True Hermes Protocol

LeadHunterOS v2 uses the **official NousResearch Hermes function-calling standard** (same as Hermes Agent v2026.4.23):

```
System prompt contains:
  <tools>
  [{"type": "function", "function": {"name": "search_apollo", ...}}]
  </tools>

Model responds with:
  <tool_call>
  {"name": "search_apollo", "arguments": {"titles": ["VP Sales"]}}
  </tool_call>

Agent parses XML -> dispatches -> returns:
  <tool_response>
  {"leads": [...], "count": 10}
  </tool_response>
```

This is compatible with: Hermes-3, Qwen3, Mistral, any model fine-tuned on Hermes function-calling data.

---

## LLM Backend Selection Logic

```
Task complexity score:
  Simple search/score  -> Lemonade local (Qwen3-7B)
  Enrichment/writing   -> Lemonade local (Qwen3-14B)
  Deep research        -> Perplexity Sonar Pro (web search)
  Complex reasoning    -> Claude Opus 4 / GPT-4.1
  Fallback if local down -> Claude Sonnet 4.5
```

Set via env var or `--llm` flag:
- `--llm local` (Lemonade, default)
- `--llm claude` (Anthropic)
- `--llm openai` (OpenAI)
- `--llm perplexity` (Perplexity Sonar Pro)

---

## Environment Variables

See `.env.example`. Key sections:
- `LEMONADE_*` — AMD local server (primary)
- `ANTHROPIC_API_KEY` — Claude Pro/API
- `OPENAI_API_KEY` — ChatGPT Plus/API
- `PERPLEXITY_API_KEY` — Perplexity Pro
- `APOLLO_API_KEY` — Lead enrichment (US)
- `HUNTER_API_KEY` — Email lookup (US)
- `DATABASE_URL` — PostgreSQL

## Production Readiness Tooling

- End-to-end eval harness: `python v2/evals/harness.py`
- Regression gate runner: `python v2/scripts/run_regression_gate.py`
- Trajectory replay/diff: `python v2/scripts/replay_trajectory.py --path <file> [--compare <file>]`
- Replay viewer (HTML): `python v2/scripts/render_replay_view.py --path <file> --out v2/reports/replay_view.html`
- Tuning experiments: `python v2/scripts/tuning_experiments.py`
- Live provider smoke lane: `python v2/scripts/live_provider_smoke.py`
- Run-time transparency view: `python v2/run_agent.py --timeline --objective "Find qualified US SMB leads"`
- Metrics endpoint for dashboards: `python v2/scripts/serve_metrics.py` then scrape `http://localhost:9464/metrics`
- Ops dashboard pack: [v2/ops/README.md](/D:/Codex/LeadHunterOS-audit/v2/ops/README.md)
- Detailed guide: [PRODUCTION_READINESS.md](/D:/Codex/LeadHunterOS-audit/v2/docs/PRODUCTION_READINESS.md)
