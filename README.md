# ARGUS Sentinel 🛰️
### Autonomous Real-time Global Understanding System

> **Track 1: UNLOCKED — AGENT** | Bright Data Hackathon 2026

---

## What is ARGUS Sentinel?

Most intelligence tools give you a **snapshot** of what's happening now.

ARGUS Sentinel gives you the **trajectory** — the velocity at which information is changing across the live web — and uses it to predict what's *about to happen* before it becomes news.

It doesn't just scrape. It **watches**, **correlates**, and **forecasts**.

---

## The Core Innovation: Temporal Velocity Intelligence

Traditional systems: `web → scrape → summarise`

ARGUS Sentinel: `web → scrape → delta-compare → velocity-score → cross-correlate → predict → alert`

By tracking *how fast* signals are moving (hiring surges, code commits accelerating, forum sentiment shifts, filing frequencies) and correlating them across independent sources, ARGUS detects **pre-announcement patterns** that no single data source reveals.

---

## Bright Data Integration (All Tools Used)

| Tool | Agent | Purpose |
|------|-------|---------|
| **MCP Server** | Orchestrator | Claude connects directly to live web via LangChain MCP |
| **SERP API** | News Agent | Real-time search across Google/Bing/Yandex for breaking signals |
| **Web Unlocker** | Signal Miner | Bypasses bot detection on Reddit, forums, social platforms |
| **Scraping Browser** | Site Watcher | Full JS rendering for SPA competitor sites, pricing pages |
| **Web Scraper API** | Finance Agent | Structured data from LinkedIn, SEC EDGAR, Crunchbase |
| **Proxies** | All Agents | 400M+ IP pool for geo-diverse, rate-limit-immune collection |

---

## Architecture

```
User Query (natural language)
        ↓
  Orchestrator Agent (Claude Sonnet via MCP Server)
        ↓
  ┌─────────────────────────────────────────────┐
  │      Bright Data Real-Time Infrastructure   │
  │  ┌───────────┐ ┌──────────┐ ┌────────────┐ │
  │  │News Agent │ │Finance   │ │Site Watcher│ │
  │  │SERP API   │ │Scraper   │ │Scraping    │ │
  │  │live news  │ │API+filings│ │Browser+JS  │ │
  │  └───────────┘ └──────────┘ └────────────┘ │
  │              ┌─────────────┐                │
  │              │Signal Miner │                │
  │              │Web Unlocker │                │
  │              │social/forums│                │
  │              └─────────────┘                │
  │   Proxies: 400M+ IPs · auto geo-routing     │
  └─────────────────────────────────────────────┘
        ↓
  Temporal Velocity Engine
  (trajectory analysis · cross-domain correlation · prediction)
        ↓
  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
  │Intelligence  │ │Real-time     │ │Trend Predictions │
  │Report (PDF)  │ │Alerts (WS)   │ │(confidence %)    │
  └──────────────┘ └──────────────┘ └──────────────────┘
```

---

## Features

- **Multi-agent parallel crawling** — 4 specialised agents run concurrently
- **Temporal delta engine** — compares snapshots over time to measure velocity
- **Cross-domain signal fusion** — correlates news + financial + social + competitor
- **Predictive confidence scores** — each prediction comes with a % likelihood
- **Self-healing infrastructure** — Bright Data handles retries, blocks, CAPTCHAs
- **Real-time WebSocket dashboard** — live intelligence feed in browser
- **Zero-maintenance** — no proxy management, no scraper maintenance
- **Any domain** — competitive intel, M&A signals, product launches, geopolitical risk

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/YOUR_HANDLE/argus-sentinel
cd argus-sentinel
pip install -r requirements.txt

# 2. Set credentials
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, BRIGHT_DATA_API_KEY, BRIGHT_DATA_SERP_KEY

# 3. Run
python main.py --query "What is OpenAI planning to launch in the next 30 days?"

# 4. Dashboard
python dashboard/app.py
# Open http://localhost:8000
```

---

## Example Queries

```
"Monitor Tesla's product launch signals for the next 2 weeks"
"What M&A signals exist around Stripe right now?"
"Track competitor pricing changes for Notion vs Linear"
"Detect early signs of a React major version announcement"
"What is the hiring trajectory at Anthropic suggesting?"
```

---

## Output Sample

```json
{
  "query": "OpenAI launch signals",
  "timestamp": "2026-05-14T09:32:11Z",
  "velocity_score": 8.7,
  "prediction": "High probability (82%) of a major model announcement within 14 days",
  "signals": [
    {"source": "news",    "signal": "3x increase in GPT-5 mentions in 48h",   "weight": 0.31},
    {"source": "finance", "signal": "Azure AI compute spend +40% in Q1 filing","weight": 0.28},
    {"source": "social",  "signal": "OpenAI eng team sentiment: excitement peak","weight": 0.22},
    {"source": "site",    "signal": "Docs navigation restructured (new section)","weight": 0.19}
  ],
  "trajectory": [2.1, 3.4, 4.8, 6.2, 8.7],
  "alert_threshold_crossed": true
}
```

---

## Project Structure

```
argus_sentinel/
├── main.py                    # CLI entry point
├── orchestrator.py            # LangChain orchestrator + MCP
├── temporal_engine.py         # Velocity & prediction engine
├── bright_data_client.py      # Unified Bright Data SDK wrapper
├── config.py                  # All configuration
├── agents/
│   ├── base_agent.py          # Abstract base agent
│   ├── news_agent.py          # SERP API news collection
│   ├── finance_agent.py       # Web Scraper API financials
│   ├── site_watcher.py        # Scraping Browser competitor monitoring
│   └── signal_miner.py        # Web Unlocker social signals
├── dashboard/
│   ├── app.py                 # FastAPI + WebSocket server
│   └── static/index.html      # Real-time intelligence dashboard
├── tests/
│   ├── test_agents.py
│   └── test_temporal_engine.py
├── requirements.txt
├── .env.example
└── README.md
```

---

## Judging Criteria Alignment

| Criterion | How ARGUS delivers |
|-----------|-------------------|
| **Application of Technology** | Uses ALL 6 Bright Data products in a cohesive pipeline; Claude Sonnet as orchestrator via MCP |
| **Presentation** | Real-time dashboard, PDF reports, live WebSocket alerts |
| **Business Value** | Replaces $50k+/year analyst teams for competitive intelligence |
| **Originality** | First system to apply *temporal velocity* to web scraping for prediction |

---

## License
MIT — built for the Bright Data × lablab.ai Hackathon 2026
