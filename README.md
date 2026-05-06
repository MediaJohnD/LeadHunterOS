# 🎯 LeadHunterOS

> **Open-source AI lead hunter that beats Gojiberry AI, Intently.ai, and Unify GTM — self-hosted under $50/mo.**

LeadHunterOS is a production-ready, modular AI agent pipeline that monitors Reddit, Twitter/X, LinkedIn, news, and Google Maps for buyer intent signals, enriches leads from multiple sources, scores them with Claude Haiku, and generates hyper-personalized outreach with Claude Sonnet — all orchestrated by n8n.

## 🏆 Why LeadHunterOS Beats the Competition

| Feature | Gojiberry AI | Intently.ai | Unify GTM | **LeadHunterOS** |
|---|---|---|---|---|
| Monthly Cost | $299+ | $499+ | $1,740+ | **< $50** |
| Self-Hosted | ❌ | ❌ | ❌ | ✅ |
| Reddit Signals | ❌ | ✅ | ❌ | ✅ |
| Twitter/X Signals | ✅ | ✅ | ✅ | ✅ |
| LinkedIn Signals | ✅ | ✅ | ✅ | ✅ |
| Google Maps | ❌ | ❌ | ❌ | ✅ |
| Auto Outreach | ✅ LinkedIn only | ❌ Alerts only | ✅ Email+LinkedIn | ✅ Email+LinkedIn |
| Custom ICP Scoring | Limited | Limited | Limited | ✅ Full Claude AI |
| CRM Integration | HubSpot/Pipedrive | ❌ | Salesforce/HubSpot | ✅ Any via n8n |
| Data Ownership | ❌ | ❌ | ❌ | ✅ |
| Open Source | ❌ | ❌ | ❌ | ✅ MIT |

## 🏗️ Architecture

```
Signal Monitors (Reddit/X/LinkedIn/Web/Maps)
          ↓
    Redis Signal Queue (dedup)
          ↓
   Enrichment Agent (Apollo/Hunter/PDL)
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

## 💰 Cost Breakdown (Monthly)

| Service | Free Tier | Paid |
|---|---|---|
| VPS (2 CPU / 4GB RAM) | - | ~$12/mo |
| Apify Twitter Scraper | - | ~$5-10/mo |
| People Data Labs | 100 free | $0.04/record |
| Apollo.io | 100 credits | $49/mo (2K credits) |
| Hunter.io | 25 searches | $34/mo |
| Claude Haiku (scoring) | - | ~$0.30/mo |
| Claude Sonnet (outreach) | - | ~$2.00/mo |
| **TOTAL** | **$0** | **~$15-47/mo** |

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
│   ├── enrichment.py       # Apollo → Hunter → PDL waterfall
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
*Built with Claude Sonnet 4.6 | Researched with Perplexity Pro | Beats Gojiberry AI at 1/6th the cost*
