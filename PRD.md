# Product Requirements Document
## ARGUS Sentinel — Autonomous Real-time Global Understanding System

**Version:** 1.0  
**Date:** 2026-05-16  
**Track:** Bright Data × lablab.ai Hackathon 2026 — Track 1: UNLOCKED (AGENT)

---

## 1. Executive Summary

ARGUS Sentinel is an autonomous multi-agent intelligence platform that monitors the live web to detect **pre-announcement signals** before they become public news. Unlike traditional monitoring tools that deliver snapshots, ARGUS measures *velocity* — how fast information is changing across news, financial filings, social platforms, and competitor sites — and uses that trajectory to generate probabilistic predictions about upcoming corporate or product events.

**Core value proposition:** Replace $50,000+/year analyst teams with a system that provides 48–72 hours of predictive lead time on major announcements.

---

## 2. Problem Statement

### Current Landscape
Intelligence analysts and competitive teams today face three critical gaps:

| Gap | Consequence |
|-----|-------------|
| **Snapshot-only tools** | Analysts see what *happened*, not what is *about to happen* |
| **Siloed data sources** | News monitors ignore SEC filings; finance tools miss social buzz |
| **Reactive workflows** | Teams respond to announcements rather than preparing before them |

### The Core Insight
A major corporate event (product launch, funding round, M&A, regulatory action) is rarely instantaneous. It leaves detectable traces across multiple independent channels 24–72 hours beforehand:
- Engineering teams discuss it on Hacker News and Reddit
- Headcount in specific departments surges on LinkedIn
- Competitor documentation gets restructured
- SEC 8-K filings appear before press releases
- Social sentiment on platforms shifts noticeably

**No single data point reveals this. Cross-domain velocity correlation does.**

---

## 3. Target Users

### Primary: Corporate Intelligence Analysts
- Track competitor product launches, M&A signals, executive moves
- Need: Early warning, structured reports, confident probability scores

### Secondary: Venture Capital Researchers
- Monitor portfolio companies and potential investments
- Need: Financial signal correlation, hiring velocity, funding signals

### Tertiary: Product Strategy Teams
- Watch competitors' pricing, documentation, and feature releases
- Need: Site change detection, changelog monitoring

### Quaternary: Geopolitical & Regulatory Risk Teams
- Track regulatory filings, government statements, policy signals
- Need: Multi-jurisdiction monitoring, alert thresholds

---

## 4. Product Goals

### Hackathon Goals (MVP)
1. Demonstrate all 6 Bright Data products working in a single cohesive pipeline
2. Show Claude Sonnet as a production orchestrator (not just a chatbot)
3. Deliver predictive intelligence with quantified confidence scores
4. Provide a real-time dashboard that visualises velocity and predictions

### Post-Hackathon Product Goals
1. **G1:** Achieve >70% accuracy on predictions with confidence ≥ 75%
2. **G2:** Sub-60-second end-to-end latency for a fresh query
3. **G3:** Support persistent watch mode with daily reports
4. **G4:** Integrate alert delivery (Slack, email, webhooks)
5. **G5:** Multi-tenant SaaS with team workspaces

---

## 5. Functional Requirements

### 5.1 Query Interface
- **FR-01:** Users can enter any natural-language query about an entity or topic
- **FR-02:** System automatically extracts entities, intent, domain, and urgency from queries
- **FR-03:** System supports comparison queries across up to 3 entities simultaneously
- **FR-04:** Pre-built query templates cover the most common intelligence use-cases
- **FR-05:** Query history is persisted and replayable from the dashboard sidebar

### 5.2 Agent Pipeline
- **FR-06:** Four specialised agents run concurrently for every query
  - **News Agent:** Real-time search across Google, Bing, Yandex via SERP API
  - **Finance Agent:** LinkedIn headcount + Crunchbase funding + SEC EDGAR filings
  - **Site Watcher:** Full JS-rendered competitor site monitoring via Scraping Browser
  - **Signal Miner:** Reddit, Hacker News, GitHub, Product Hunt via Web Unlocker
- **FR-07:** Each agent produces normalised `ArgusSignal` objects with source, content, weight, and metadata
- **FR-08:** Agents deduplicate signals using content fingerprints across runs
- **FR-09:** Agent failures degrade gracefully — pipeline continues with available data

### 5.3 Temporal Velocity Engine
- **FR-10:** Engine computes per-source velocity scores (0–10 scale) using rolling windows
- **FR-11:** Engine computes composite velocity with configurable source weights
- **FR-12:** Engine applies cross-domain amplification when ≥3 sources show elevated velocity
- **FR-13:** Engine maintains trajectory history (up to 20 data points per entity)
- **FR-14:** Engine detects anomalies using z-score analysis (threshold: 2.5σ)
- **FR-15:** Linear regression slope indicates acceleration vs. deceleration

### 5.4 AI Synthesis (Orchestrator)
- **FR-16:** Claude Sonnet synthesises multi-source signals into natural-language predictions
- **FR-17:** Each prediction includes a probability score (0–100%)
- **FR-18:** Orchestrator optionally accesses live web via Bright Data MCP Server
- **FR-19:** System generates executive summaries, key findings, and recommended actions
- **FR-20:** Synthesis falls back to direct Claude call if MCP is unavailable

### 5.5 Alerting
- **FR-21:** Alerts trigger when composite velocity ≥ 6.5/10, anomaly detected, or confidence ≥ 80%
- **FR-22:** Alerts are pushed to all connected WebSocket clients in real time
- **FR-23 (v2):** Alert delivery via Slack webhook, email, PagerDuty
- **FR-24:** Configurable per-query alert thresholds

### 5.6 Dashboard
- **FR-25:** Real-time web dashboard served at `http://localhost:8000`
- **FR-26:** WebSocket connection shows live pipeline progress (4 steps)
- **FR-27:** Velocity gauges displayed per source with composite score
- **FR-28:** Sparkline trajectory chart shows historical velocity trend
- **FR-29:** Top 6 signals displayed with source badge, content, and weight
- **FR-30:** Prediction card shows text prediction with confidence progress bar
- **FR-31:** Query history sidebar with recent runs, velocity scores, alert flags
- **FR-32:** Alert banner displayed prominently when threshold is crossed

### 5.7 Reporting
- **FR-33:** JSON reports saved to disk with timestamp and entity slug in filename
- **FR-34 (v2):** PDF export of intelligence reports
- **FR-35:** Reports include all signals, velocity scores, trajectory, and synthesis
- **FR-36:** Watch mode generates recurring reports at configurable intervals

### 5.8 CLI
- **FR-37:** CLI accepts natural-language queries via `--query` flag
- **FR-38:** Watch mode (`--watch`) polls at configurable intervals
- **FR-39:** Rich terminal rendering with colour-coded velocity scores
- **FR-40:** Dashboard launch via `--dashboard` flag

---

## 6. Non-Functional Requirements

### Performance
- **NFR-01:** Single query completes in under 90 seconds (cold, all agents)
- **NFR-02:** Watch mode polling interval minimum 5 minutes
- **NFR-03:** Dashboard WebSocket latency < 200ms for alert delivery
- **NFR-04:** Support up to 10 concurrent WebSocket connections

### Reliability
- **NFR-05:** Agent failure rate < 5% per collection run (Bright Data handles infrastructure)
- **NFR-06:** Retry logic with exponential backoff (max 4 attempts, 2^n delay)
- **NFR-07:** All Bright Data calls timeout at 60 seconds
- **NFR-08:** Graceful degradation — partial results better than failure

### Security
- **NFR-09:** API keys stored in environment variables only, never committed
- **NFR-10:** `.env` excluded from version control via `.gitignore`
- **NFR-11 (v2):** Dashboard protected by API key or OAuth

### Scalability
- **NFR-12:** Temporal engine stores per-entity velocity windows in memory (v1), Redis (v2)
- **NFR-13:** Report history bounded at 500 entries (configurable)
- **NFR-14 (v2):** Horizontal scaling via task queue (Celery or similar)

---

## 7. Out of Scope (v1)

- User authentication and multi-tenancy
- Persistent database storage (reports are in-memory + JSON files)
- PDF report generation
- Email/Slack alert delivery
- Mobile-native app
- Historical trend analysis across weeks (requires persistent storage)
- Geographic filtering for signals
- Custom weighting UI for source scores

---

## 8. Success Metrics

| Metric | Target |
|--------|--------|
| Query-to-report latency | < 90s |
| Agent collection success rate | > 95% |
| Prediction accuracy (confidence ≥ 75%) | > 65% |
| Dashboard WebSocket uptime | > 99% |
| Bright Data API products used | 6/6 |
| Hackathon demo impression score | Top 10% |

---

## 9. Constraints

- Must use Bright Data infrastructure exclusively for web access (no raw HTTP scraping)
- Must use Claude Sonnet (Anthropic) for orchestration and prediction synthesis
- Must demonstrate all 6 Bright Data products: MCP Server, SERP API, Web Unlocker, Scraping Browser, Web Scraper API, Proxies
- Python 3.11+ required (uses `removeprefix`, walrus operator, type hints)

---

## 10. Roadmap

### v1.0 (Hackathon MVP — complete)
- Multi-agent pipeline with all 4 agents
- Temporal velocity engine with prediction
- Real-time WebSocket dashboard
- CLI with watch mode

### v1.1 (Post-hackathon)
- Persistent report storage (SQLite → PostgreSQL)
- Slack/email alert delivery
- PDF report export
- Watch mode visible in dashboard UI

### v2.0 (SaaS)
- Multi-tenant authentication (OAuth)
- Team workspaces and shared dashboards
- Custom entity tracking lists
- API with webhooks for integrations
- Redis-backed velocity windows for horizontal scaling
