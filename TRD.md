# Technical Requirements Document
## ARGUS Sentinel — Autonomous Real-time Global Understanding System

**Version:** 1.0  
**Date:** 2026-05-16

---

## 1. Technology Stack

### Core Runtime
| Component | Technology | Version |
|-----------|-----------|---------|
| Language | Python | 3.11+ |
| Async runtime | asyncio | stdlib |
| HTTP client | aiohttp | 3.9+ |
| Browser automation | Playwright (async) | 1.44+ |
| Web framework | FastAPI | 0.111+ |
| ASGI server | Uvicorn | 0.29+ |
| Terminal UI | Rich | 13+ |

### AI & Orchestration
| Component | Technology |
|-----------|-----------|
| LLM provider | Anthropic (Claude Sonnet) |
| SDK | `anthropic` Python SDK 0.28+ |
| MCP integration | Anthropic SDK native MCP tool type |
| Model: orchestration | `claude-sonnet-4-20250514` |
| Model: prediction | `claude-sonnet-4-20250514` |

### Bright Data Infrastructure
| Product | Usage | Python Interface |
|---------|-------|-----------------|
| MCP Server | Live web access for synthesis | Anthropic SDK `mcp` tool type |
| SERP API | News search (Google/Bing/Yandex) | `aiohttp` REST calls |
| Web Scraper API | LinkedIn / Crunchbase / SEC structured data | `aiohttp` dataset polling |
| Web Unlocker | Reddit / HN / GitHub / Product Hunt | `aiohttp` POST requests |
| Scraping Browser | Competitor site JS rendering | Playwright over CDP WebSocket |
| Proxies | All agents geo-routing | Environment-configured proxy URLs |

### Parsing & Analysis
| Library | Purpose |
|---------|---------|
| `beautifulsoup4` | HTML parsing for site watcher + signal miner |
| `lxml` | BS4 parser backend |
| `python-dateutil` | Flexible date string parsing |
| `difflib` | Content similarity ratio for site diffs |
| `statistics` | Velocity calculations (mean, stdev) |
| `hashlib` | Signal fingerprinting for deduplication |

### Deployment
| Component | Technology |
|-----------|-----------|
| Container | Docker (Python 3.11-slim) |
| Cloud targets | Render, Railway, or any Docker host |
| CI | GitHub Actions |

---

## 2. Architecture

### 2.1 System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      Client Layer                           │
│  CLI (main.py + argparse + Rich)  │  Browser (dashboard)   │
└────────────────┬───────────────────────────┬────────────────┘
                 │ asyncio.run()             │ HTTP + WebSocket
┌────────────────▼───────────────────────────▼────────────────┐
│                   Application Layer                         │
│  FastAPI (dashboard/app.py)  │  ArgusOrchestrator          │
│  REST: POST /api/query       │  (orchestrator.py)          │
│  WS:   /ws                   │                             │
└────────────────┬─────────────────────────┬──────────────────┘
                 │                         │
┌────────────────▼─────────┐  ┌───────────▼──────────────────┐
│   Agent Layer            │  │  Intelligence Layer           │
│  NewsAgent               │  │  TemporalVelocityEngine       │
│  FinanceAgent            │  │  (temporal_engine.py)        │
│  SiteWatcherAgent        │  │   - VelocityWindow            │
│  SignalMinerAgent        │  │   - TemporalProfile           │
│  (agents/*.py)           │  │   - LLM prediction            │
└────────────────┬─────────┘  └───────────────────────────────┘
                 │
┌────────────────▼─────────────────────────────────────────────┐
│                  Bright Data Layer (bright_data_client.py)   │
│  serp_search()           scraper_api_fetch()                 │
│  serp_news_multi_engine()  unlock()                          │
│  scraping_browser_fetch()  _request_with_retry()            │
└────────────────┬─────────────────────────────────────────────┘
                 │
┌────────────────▼─────────────────────────────────────────────┐
│                  Bright Data Cloud Infrastructure            │
│  400M+ IP pool  │  CAPTCHA solving  │  CDP browser clusters  │
│  SERP endpoints │  660+ pre-scrapers│  Web Unlocker zones    │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
User Query (string)
     │
     ▼
ArgusOrchestrator._extract_intent()
     │  Claude Sonnet → QueryIntent JSON
     ▼
asyncio.gather() over entities (max 3)
     │
     ▼  per entity:
asyncio.gather() over 4 agents
     │   NewsAgent.run_and_snapshot()
     │   FinanceAgent.run_and_snapshot()
     │   SiteWatcherAgent.run_and_snapshot()
     │   SignalMinerAgent.run_and_snapshot()
     │
     ▼
all_signals: list[ArgusSignal] + new_signals: list[ArgusSignal]
     │
     ▼
TemporalVelocityEngine.process()
     │  VelocityWindow.push() per source
     │  Composite velocity (weighted sum + cross-domain boost)
     │  Trajectory slope (linear regression)
     │  Anomaly detection (z-score)
     │  LLM prediction (Claude Sonnet → JSON)
     ▼
TemporalProfile
     │
     ▼
ArgusOrchestrator._synthesise()
     │  Claude Sonnet (+ optional MCP web access)
     │  → executive_summary, key_findings, recommended_actions
     ▼
ArgusReport
     │
     ├──▶ render_report() → terminal
     ├──▶ save_report() → JSON file
     └──▶ broadcast() → WebSocket clients
```

---

## 3. Module Specifications

### 3.1 `config.py`

**Responsibility:** Single source of truth for all configuration.

```python
@dataclass
class ArgusConfig:
    bright_data: BrightDataConfig    # API keys, endpoint URLs, proxy strings
    model: ModelConfig               # Model IDs, max_tokens, temperature
    temporal: TemporalConfig         # Velocity windows, alert thresholds
    agent: AgentConfig               # Dataset IDs, search limits
    dashboard: DashboardConfig       # Host, port, WebSocket settings
    output_dir: str                  # Report output directory
    log_level: str
```

**Improvement:** Add `Pydantic` validation with `BaseSettings` to catch misconfiguration early and support `.env` hierarchical overrides.

### 3.2 `bright_data_client.py`

**Responsibility:** Unified async client for all Bright Data products.

Key design decisions:
- Uses `aiohttp.ClientSession` with `Bearer` auth header applied globally
- Playwright `Browser` instance lazy-initialised and reused within a session
- Exponential backoff retry on 429/5xx (max 4 attempts, delays: 2, 4, 8, 16s)
- Context manager (`async with`) ensures session cleanup

**Improvement areas:**
- Add circuit breaker per product (if SERP API consistently fails, stop retrying)
- Cache Scraping Browser page results for identical URLs within 60s window
- Add per-request tracing headers for Bright Data billing attribution

### 3.3 `agents/base_agent.py`

**Responsibility:** Abstract base defining the agent contract.

```python
class BaseAgent(ABC):
    async def collect(entity, query) → list[ArgusSignal]  # Subclass implements
    async def run_and_snapshot(entity, query)              # Calls collect(), manages history
    def get_snapshot_series(entity) → list[AgentSnapshot]
    def last_snapshot(entity) → AgentSnapshot | None
```

**Signal deduplication:** MD5 fingerprint of `source:url:content[:80]`. Fingerprints persisted per entity across runs.

**Improvement:** Persist snapshot history to disk/Redis so velocity windows survive process restarts.

### 3.4 `temporal_engine.py`

**Responsibility:** Core innovation — velocity computation, trajectory analysis, prediction.

**Velocity formula:**
```
velocity = clamp((recent_avg - baseline_avg) / baseline_avg × 5, 0, 10)

where:
  recent_avg  = mean of last 2 counts in window
  baseline_avg = mean of counts[:-2] (all but last 2)
```

**Composite score:**
```
composite = Σ (source_velocity[s] × weight[s])   for s in {news, finance, site, social}

weights: news=0.28, finance=0.32, site=0.22, social=0.18

if active_sources_above_3.0 >= 3:
    composite *= 1.4   (cross-domain amplification)

composite = clamp(composite, 0, 10)
```

**Alert trigger:**
```
alert = composite >= 6.5  OR  anomaly_detected  OR  confidence >= 0.80
```

**Improvement:** Store velocity windows in Redis with TTL for horizontal scaling and process-restart resilience.

### 3.5 `orchestrator.py`

**Responsibility:** Top-level orchestration — intent extraction, agent dispatch, synthesis.

**MCP integration:**
```python
mcp_tool = {
    "type": "mcp",
    "server_label": "brightdata",
    "server_url": "https://mcp.brightdata.com/sse",
    "require_approval": "never",
    "headers": {"Authorization": f"Bearer {api_key}"},
}
```

When `BRIGHT_DATA_API_KEY` is present, synthesis call includes the MCP tool, giving Claude live web access to verify/augment collected signals. Falls back to direct Claude call if MCP unavailable.

**Improvement:** Add structured output parsing with retry for malformed JSON from LLM calls.

### 3.6 `dashboard/app.py`

**Responsibility:** FastAPI + WebSocket real-time dashboard backend.

Endpoints:
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serve HTML dashboard |
| POST | `/api/query` | Run intelligence query, stream updates via WS |
| GET | `/api/history` | Return last N reports |
| GET | `/api/health` | Health check |
| WS | `/ws` | Real-time push channel |

**WebSocket message types:**
```json
{ "type": "status",  "status": "running|agents_deployed", "query": "..." }
{ "type": "report",  "data": ArgusReport, "alert": bool }
{ "type": "error",   "message": "..." }
{ "type": "history", "data": [ArgusReport...] }
{ "type": "ping",    "ts": 1234567890 }
```

**Improvement:** Add background task queue so multiple concurrent queries don't block each other.

---

## 4. Data Models

### 4.1 ArgusSignal

```python
@dataclass
class ArgusSignal:
    source:      str    # "news" | "finance" | "site" | "social"
    signal_type: str    # "mention" | "sentiment" | "change" | "filing" | "hiring"
    entity:      str    # Company/topic being tracked
    content:     str    # Human-readable signal description (≤ 200 chars)
    url:         str    # Source URL
    timestamp:   float  # Unix timestamp
    weight:      float  # 0.0–1.0 importance score
    metadata:    dict   # Source-specific extras
```

### 4.2 TemporalProfile

```python
@dataclass
class TemporalProfile:
    entity:               str
    timestamp:            float
    velocity_score:       float        # 0–10 composite
    source_velocities:    dict[str, float]   # per-source scores
    trajectory:           list[float]  # last 10 composite scores
    trajectory_slope:     float        # linear regression slope
    prediction:           str          # NL prediction text
    prediction_confidence: float       # 0–1
    anomaly_detected:     bool
    top_signals:          list[dict]   # top 8 signals by weight
    alert:                bool
```

### 4.3 ArgusReport

```python
@dataclass
class ArgusReport:
    query:              str
    entities:           list[str]
    timestamp:          float
    profiles:           list[TemporalProfile]
    executive_summary:  str
    key_findings:       list[str]
    recommended_actions: list[str]
    alert_triggered:    bool
    processing_time_s:  float
```

---

## 5. API Specifications

### POST /api/query

**Request:**
```json
{
  "query": "string (required) — natural language intelligence query",
  "stream": "boolean (optional, default: true)"
}
```

**Response (200 OK):**
```json
{
  "query": "OpenAI launch signals",
  "entities": ["OpenAI"],
  "timestamp": 1747390331.0,
  "profiles": [{
    "entity": "OpenAI",
    "velocity_score": 8.7,
    "source_velocities": {"news": 7.2, "finance": 9.1, "site": 5.4, "social": 8.8},
    "trajectory": [2.1, 3.4, 4.8, 6.2, 8.7],
    "trajectory_slope": 1.65,
    "prediction": "High probability of a major model announcement within 14 days",
    "prediction_confidence": 0.82,
    "anomaly_detected": true,
    "top_signals": [...],
    "alert": true
  }],
  "executive_summary": "...",
  "key_findings": ["..."],
  "recommended_actions": ["..."],
  "alert_triggered": true,
  "processing_time_s": 42.3
}
```

**Error (500):**
```json
{ "detail": "error message" }
```

### GET /api/history?limit=20

**Response:** Array of last `limit` ArgusReport objects.

### GET /api/health

**Response:** `{ "status": "ok", "connections": 3 }`

---

## 6. Configuration Reference

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for Claude |
| `BRIGHT_DATA_API_KEY` | Yes | Bright Data API key (all products) |
| `BRIGHT_DATA_SERP_KEY` | Yes | SERP API key (may differ) |
| `BRIGHT_DATA_CUSTOMER_ID` | For proxies | Proxy customer ID |
| `BRIGHT_DATA_PROXY_PASS` | For proxies | Proxy password |

### Temporal Engine Tuning

| Parameter | Default | Description |
|-----------|---------|-------------|
| `snapshot_window` | 5 | Historical snapshots for velocity |
| `alert_threshold` | 6.5 | Composite score to trigger alert |
| `poll_interval_news` | 300s | News agent poll interval |
| `poll_interval_finance` | 1800s | Finance agent poll interval |
| `poll_interval_site` | 3600s | Site watcher poll interval |
| `poll_interval_social` | 600s | Social signal poll interval |
| `prediction_confidence_min` | 0.55 | Minimum confidence to surface |

---

## 7. Error Handling Strategy

| Error Type | Strategy |
|-----------|---------|
| Agent collection failure | Log warning, return empty list, continue pipeline |
| Bright Data API 429 | Sleep `Retry-After`, re-raise after max_retries |
| Bright Data API 5xx | Exponential backoff, raise after 4 attempts |
| LLM JSON parse failure | Log warning, use heuristic fallback prediction |
| Playwright connection failure | Degrade gracefully — skip site watcher |
| WebSocket disconnect | Remove from `active_connections`, auto-reconnect client-side |
| Missing API keys | Fail fast at startup with clear error message |

---

## 8. Security Requirements

- **TR-SEC-01:** All API keys loaded from environment, never hardcoded
- **TR-SEC-02:** `.env` excluded via `.gitignore`
- **TR-SEC-03:** HTML output from signals escaped via `escHtml()` to prevent XSS
- **TR-SEC-04 (v2):** Dashboard authenticated with JWT or API key header
- **TR-SEC-05 (v2):** Rate limiting on `/api/query` (max 10 requests/min per IP)
- **TR-SEC-06:** Playwright runs in ephemeral pages — no session persistence between queries

---

## 9. Deployment Requirements

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y chromium  # For Playwright
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN playwright install chromium
COPY . .
EXPOSE 8000
CMD ["python", "dashboard/app.py"]
```

### Environment at Runtime
- Minimum 2 vCPU, 2 GB RAM (Playwright + async agents)
- Outbound internet access (Bright Data endpoints + Anthropic API)
- `ANTHROPIC_API_KEY`, `BRIGHT_DATA_API_KEY`, `BRIGHT_DATA_SERP_KEY` set as secrets

### Render / Railway
- `render.yaml` / `railway.toml` provided in repository
- One-click deploy: set 3 environment variables and deploy

---

## 10. Testing Requirements

### Unit Tests (`tests/test_argus.py`)
- `TemporalVelocityEngine` velocity calculation correctness
- `VelocityWindow` baseline, recent, velocity, slope properties
- `ArgusSignal.fingerprint()` determinism
- `ArgusOrchestrator._parse_synthesis()` JSON parsing + fallback

### Integration Tests (v2)
- End-to-end query with mock Bright Data responses
- WebSocket message delivery on report completion
- Report persistence and retrieval from `/api/history`

### Load Tests (v2)
- 10 concurrent WebSocket connections
- 3 concurrent queries (parallel entity processing)
