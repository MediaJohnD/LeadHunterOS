# 🎯 LeadHunterOS

> **Open-source AI lead intelligence and orchestration system focused on quality, transparency, and local control.**

LeadHunterOS is a production-ready, modular AI agent pipeline that monitors Reddit, Twitter/X, LinkedIn, news, and Google Maps for buyer intent signals, enriches leads from multiple sources, scores them with Claude Haiku, and generates hyper-personalized outreach with Claude Sonnet — all orchestrated by n8n.

## ✅ Core Product Principles

- Signal-first lead discovery across multiple public channels.
- Deterministic qualification gates and explainable ICP scoring.
- Provider-safe enrichment waterfall with provenance and confidence.
- CRM handoff readiness with auditability and suppression controls.
- Local-first operation with optional cloud fallback.

## 🏗️ Architecture

```
Signal Monitors (Reddit/X/LinkedIn/Web/Maps)
          ↓
    Redis Signal Queue (dedup)
          ↓
   Enrichment Agent (public-source waterfall + optional adapters)
          ↓
   ICP Scorer (Claude Haiku 3.5) → Score 0-100
          ↓
  Score 70-100: Outreach Writer (Claude Sonnet)
  Score 41-69:  Nurture Queue
  Score 0-40:   Discard
          ↓
   Outreach Sender (Gmail SMTP + LinkedIn OutX)
          ↓
      PostgreSQL (leads, signals, campaigns)
          ↓
      n8n Dashboard (orchestration + analytics)
```

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Anthropic API key (Claude)
- Reddit API credentials (free)

### Setup

```bash
git clone https://github.com/MediaJohnD/LeadHunterOS.git
cd LeadHunterOS
cp .env.example .env
# Edit .env with your API keys
docker-compose up -d
```

Then visit `http://localhost:5678` for the n8n dashboard.

## 📁 Project Structure

```
LeadHunterOS/
├── README.md
├── docker-compose.yml      # n8n + FastAPI + PostgreSQL + Redis
├── Dockerfile              # FastAPI microservice
├── .env.example            # All 30+ environment variables
├── main.py                 # FastAPI app (12 endpoints)
├── requirements.txt
├── agents/
│   ├── __init__.py
│   ├── reddit_monitor.py   # PRAW async Reddit scanner
│   ├── twitter_monitor.py  # Apify X/Twitter collector
│   ├── web_monitor.py      # RSS + Bing News + Google Maps
│   ├── enrichment.py       # Public-first enrichment waterfall
│   ├── icp_scorer.py       # Claude Haiku ICP scoring
│   ├── outreach_writer.py  # Claude Sonnet message writer
│   └── outreach_sender.py  # Gmail SMTP + LinkedIn OutX
├── db/
│   └── schema.sql          # PostgreSQL schema
└── n8n/
    └── workflows/
        └── main_workflow.json
```

## 🔧 ICP Scoring

The Claude Haiku scorer returns:
```json
{
  "score": 85,
  "fit_reason": "VP of Sales at 50-person SaaS, mentioned switching CRM",
  "urgency": "high",
  "recommended_channel": "linkedin"
}
```

**Thresholds:**
- `70-100` → Immediate outreach
- `41-69` → Nurture queue (weekly touchpoint)
- `0-40` → Discard

## 📄 License

MIT License — free to use, modify, and deploy commercially.

---
*Built for reliable, explainable lead intelligence workflows with continuous improvement loops.*
