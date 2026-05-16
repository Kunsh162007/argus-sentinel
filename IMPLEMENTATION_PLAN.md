# Implementation Plan
## ARGUS Sentinel — Development Roadmap & Technical Improvement Plan

**Version:** 1.0  
**Date:** 2026-05-16

---

## 1. Current State Assessment

### What's Complete (v1.0 — Hackathon MVP)

| Component | Status | Quality |
|-----------|--------|---------|
| `config.py` — centralised configuration | Done | Good |
| `bright_data_client.py` — unified Bright Data client | Done | Good |
| `agents/base_agent.py` — abstract base with snapshot history | Done | Good |
| `agents/news_agent.py` — SERP multi-engine news collection | Done | Good |
| `agents/finance_agent.py` — LinkedIn + Crunchbase + SEC | Done | Good |
| `agents/site_watcher.py` — Playwright site change detection | Done | Good |
| `agents/signal_miner.py` — Reddit + HN + GitHub + PH | Done | Good |
| `orchestrator.py` — intent extraction + agent dispatch + synthesis | Done | Good |
| `temporal_engine.py` — velocity + trajectory + anomaly + prediction | Done | Excellent |
| `dashboard/app.py` — FastAPI + WebSocket backend | Done | Good |
| `dashboard/static/index.html` — real-time dashboard | Done | Good |
| `main.py` — CLI with Rich output + watch mode | Done | Excellent |
| `streamlit_app.py` — Streamlit alternative UI | Done | Good |
| Docker + CI + Render/Railway deploy configs | Done | Good |

### Known Gaps & Bugs

| Issue | Priority | Effort |
|-------|----------|--------|
| Velocity scores zero on first run (no baseline) | High | Low |
| In-memory state lost on process restart | High | Medium |
| No mobile responsiveness in dashboard | Medium | Low |
| Multi-entity: UI only renders first profile | Medium | Low |
| Watch mode not accessible from dashboard UI | Medium | Medium |
| No rate limiting on `/api/query` | Medium | Low |
| `BeautifulSoup` imported at module level in `signal_miner.py` (crashes if not installed) | High | Low |
| `_page_text_cache` initialised lazily (anti-pattern) | Low | Low |
| `quote_url` function defined locally, not imported from `urllib.parse` | Low | Low |
| Model IDs may be stale (`claude-sonnet-4-20250514`) | Medium | Low |
| No authentication on dashboard | High (prod) | High |

---

## 2. Immediate Bug Fixes (Pre-Demo)

### Fix 1: Guard BeautifulSoup imports

**File:** `agents/signal_miner.py`

Currently: `from bs4 import BeautifulSoup` at top level — crashes if not installed.

```python
# After fix:
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BeautifulSoup = None
    BS4_AVAILABLE = False
```

### Fix 2: Multi-entity UI rendering

**File:** `dashboard/static/index.html`

Currently: `renderReport` only renders `r.profiles?.[0]` — ignores additional entities.

```javascript
// After fix: render all profiles with tab navigation
function renderReport(r) {
    if (!r.profiles?.length) return;
    if (r.profiles.length === 1) {
        renderSingleProfile(r, r.profiles[0]);
    } else {
        renderMultiProfile(r);  // Tab UI for each entity
    }
}
```

### Fix 3: Model ID update

**File:** `config.py`

```python
# Before:
orchestrator_model: str = "claude-sonnet-4-20250514"

# After:
orchestrator_model: str = "claude-sonnet-4-6"
analysis_model: str = "claude-sonnet-4-6"
```

### Fix 4: Lazy cache pattern cleanup

**File:** `agents/site_watcher.py`

Replace `if not hasattr(self, "_page_text_cache"): self._page_text_cache = {}` with proper `__init__` initialisation.

```python
def __init__(self, client: BrightDataClient):
    super().__init__(client)
    self.cfg = CONFIG.agent
    self._page_hashes: dict[str, str] = {}
    self._nav_cache: dict[str, set[str]] = {}
    self._page_text_cache: dict[str, str] = {}
    self._entry_cache: set[str] = set()
    self._pricing_cache: dict[str, str] = {}
```

### Fix 5: Rate limiting on dashboard API

**File:** `dashboard/app.py`

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/api/query")
@limiter.limit("10/minute")
async def run_query(request: Request, req: QueryRequest):
    ...
```

---

## 3. Phase 1: Stability & Quality (Week 1–2)

### P1.1 — Structured Config with Pydantic

**Goal:** Catch missing credentials at startup with clear error messages.

```python
# config.py — rewrite with pydantic-settings
from pydantic import BaseSettings, Field, validator

class ArgusSettings(BaseSettings):
    anthropic_api_key: str = Field(..., env="ANTHROPIC_API_KEY")
    bright_data_api_key: str = Field(..., env="BRIGHT_DATA_API_KEY")
    bright_data_serp_key: str = Field(..., env="BRIGHT_DATA_SERP_KEY")
    alert_threshold: float = Field(6.5, ge=0, le=10)
    
    class Config:
        env_file = ".env"
```

### P1.2 — Comprehensive Test Suite

Expand `tests/test_argus.py`:

```python
class TestVelocityWindow:
    def test_velocity_with_one_entry(self):
        w = VelocityWindow("news")
        w.push(5.0)
        assert w.velocity == 0.0  # No baseline yet

    def test_velocity_with_surge(self):
        w = VelocityWindow("news")
        for c in [2.0, 2.1, 2.0, 2.2, 10.0]:
            w.push(c)
        assert w.velocity > 5.0  # Surge detected

    def test_anomaly_detection(self):
        series = [2.0, 2.1, 1.9, 2.0, 2.1, 9.5]
        assert TemporalVelocityEngine._detect_anomaly(series) is True

class TestSignalDedup:
    def test_fingerprint_deterministic(self):
        s = ArgusSignal(source="news", signal_type="mention", entity="X",
                       content="test", url="http://ex.com", timestamp=0.0, weight=1.0)
        assert s.fingerprint() == s.fingerprint()

class TestOrchestrator:
    @pytest.mark.asyncio
    async def test_intent_extraction_fallback(self, monkeypatch):
        # Test that intent extraction fails gracefully
        ...
```

### P1.3 — Dashboard Mobile Responsiveness

Add CSS media queries to `dashboard/static/index.html`:

```css
@media (max-width: 1024px) {
    .layout {
        grid-template-columns: 1fr;
        height: auto;
    }
    .side-panel {
        border-right: none;
        border-top: 1px solid var(--border);
        max-height: 300px;
    }
}

@media (max-width: 768px) {
    .velocity-row { grid-template-columns: repeat(2, 1fr); }
    .header { padding: 12px 16px; }
    .query-bar { flex-direction: column; }
    .run-btn { width: 100%; }
}
```

### P1.4 — Logging Improvement

Replace print statements with structured logging:

```python
import structlog

logger = structlog.get_logger()

# Usage:
logger.info("agent_complete",
    agent="news",
    entity="OpenAI",
    signal_count=14,
    elapsed_s=3.2)
```

---

## 4. Phase 2: Persistence & Reliability (Week 3–4)

### P2.1 — SQLite Persistence (simplest path to v2)

Create `storage.py`:

```python
import sqlite3
from pathlib import Path

class ReportStorage:
    def __init__(self, path: str = "./argus.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                query TEXT,
                timestamp REAL,
                alert_triggered INTEGER,
                velocity_score REAL,
                raw_json TEXT,
                created_at REAL DEFAULT (unixepoch())
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS velocity_windows (
                entity TEXT,
                source TEXT,
                counts TEXT,   -- JSON array
                timestamps TEXT,  -- JSON array
                PRIMARY KEY (entity, source)
            )
        """)
        self.conn.commit()

    def save_report(self, report: ArgusReport) -> str:
        ...

    def get_history(self, limit: int = 20) -> list[dict]:
        ...

    def save_velocity_window(self, entity: str, source: str, w: VelocityWindow):
        ...

    def load_velocity_windows(self, entity: str) -> dict[str, VelocityWindow]:
        ...
```

### P2.2 — Velocity Window Persistence

Modify `TemporalVelocityEngine`:

```python
def __init__(self, storage: ReportStorage = None):
    self._windows = {}
    self._composite_history = {}
    self._storage = storage
    if storage:
        self._load_from_storage()

def _load_from_storage(self):
    # Restore velocity windows from SQLite on startup
    # Enables meaningful velocity on first run after restart
    ...
```

### P2.3 — Background Task Queue

For concurrent dashboard queries without blocking:

```python
# dashboard/app.py
from fastapi import BackgroundTasks

@app.post("/api/query")
async def run_query(req: QueryRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    background_tasks.add_task(run_intelligence_job, job_id, req.query)
    return {"job_id": job_id, "status": "accepted"}

async def run_intelligence_job(job_id: str, query: str):
    await broadcast({"type": "status", "job_id": job_id, "status": "running"})
    report = await ArgusOrchestrator().run(query)
    await broadcast({"type": "report", "job_id": job_id, "data": report.to_dict()})
```

---

## 5. Phase 3: Feature Completeness (Week 5–8)

### P3.1 — Watch Mode in Dashboard

Add watch mode UI to dashboard:
- Toggle switch: "Watch Mode"
- Interval selector: 5 / 15 / 30 / 60 minutes
- Active watches list in sidebar
- "Stop Watch" button per query

### P3.2 — Alert Delivery

```python
# alerts.py
class AlertDispatcher:
    async def dispatch(self, report: ArgusReport, profile: TemporalProfile):
        tasks = []
        if CONFIG.alerts.slack_webhook_url:
            tasks.append(self._send_slack(report, profile))
        if CONFIG.alerts.email_to:
            tasks.append(self._send_email(report, profile))
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_slack(self, report, profile):
        payload = {
            "text": f"⚠️ ARGUS Alert: {profile.entity}",
            "blocks": [...]  # Rich Slack blocks
        }
        async with aiohttp.ClientSession() as s:
            await s.post(CONFIG.alerts.slack_webhook_url, json=payload)
```

### P3.3 — PDF Report Export

```python
# report_export.py
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table

def export_pdf(report: ArgusReport, output_path: str):
    doc = SimpleDocTemplate(output_path, pagesize=A4)
    story = [
        Paragraph(f"ARGUS Sentinel Intelligence Report", styles["Title"]),
        Paragraph(f"Query: {report.query}", styles["Normal"]),
        ...
    ]
    doc.build(story)
```

### P3.4 — Historical Trend Dashboard

Add velocity history chart for entities tracked over multiple days:
- Line chart (Chart.js or D3.js) showing velocity score over time
- Annotations for detected anomalies
- Prediction confidence timeline

---

## 6. Phase 4: SaaS Productisation (Week 9–16)

### P4.1 — Authentication

```python
# auth.py
from fastapi import Depends, HTTPException, Header

async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key not in CONFIG.valid_api_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key
```

### P4.2 — PostgreSQL Migration

Migrate from SQLite to PostgreSQL using SQLAlchemy async:

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase

engine = create_async_engine(CONFIG.database_url)
```

### P4.3 — Redis for Velocity Windows

```python
import redis.asyncio as aioredis

class RedisVelocityStore:
    async def push_count(self, entity: str, source: str, count: float, ts: float):
        key = f"argus:vw:{entity}:{source}"
        async with self.redis.pipeline() as pipe:
            pipe.rpush(f"{key}:counts", count)
            pipe.rpush(f"{key}:timestamps", ts)
            pipe.ltrim(f"{key}:counts", -10, -1)
            pipe.ltrim(f"{key}:timestamps", -10, -1)
            pipe.expire(f"{key}:counts", 7 * 86400)
            await pipe.execute()
```

### P4.4 — Multi-tenant Workspaces

```sql
-- teams table
CREATE TABLE teams (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    plan VARCHAR(50) DEFAULT 'free'  -- free | pro | enterprise
);

-- team_members
CREATE TABLE team_members (
    team_id UUID REFERENCES teams(id),
    user_id UUID REFERENCES users(id),
    role VARCHAR(20) DEFAULT 'member',  -- owner | admin | member
    PRIMARY KEY (team_id, user_id)
);

-- Scope reports to teams
ALTER TABLE reports ADD COLUMN team_id UUID REFERENCES teams(id);
```

---

## 7. Infrastructure Improvements

### 7.1 Docker Optimisation

Current `Dockerfile` uses `python:3.11-slim` but installs Chromium separately. Improve:

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1
CMD ["uvicorn", "dashboard.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 7.2 CI/CD Enhancement

Improve `.github/workflows/ci.yml`:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11"}
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-asyncio pytest-cov
      - run: pytest tests/ --cov=. --cov-report=xml
      - uses: codecov/codecov-action@v4

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install ruff mypy
      - run: ruff check .
      - run: mypy . --ignore-missing-imports

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install bandit
      - run: bandit -r . -x tests/
```

---

## 8. Dependency Updates

### Current `requirements.txt` gaps:

| Missing | Needed For |
|---------|-----------|
| `pydantic-settings` | Structured config validation |
| `slowapi` | Rate limiting |
| `structlog` | Structured logging |
| `pytest-asyncio` | Async test support |
| `pytest-cov` | Coverage reporting |
| `ruff` | Linting |
| `mypy` | Type checking |

### Recommended `requirements.txt` additions:

```
# Core (add)
pydantic-settings>=2.2.0
slowapi>=0.1.9

# Observability (add)
structlog>=24.1.0
prometheus-client>=0.20.0

# Dev (separate requirements-dev.txt)
pytest>=8.2.0
pytest-asyncio>=0.23.0
pytest-cov>=5.0.0
ruff>=0.4.0
mypy>=1.10.0
```

---

## 9. Implementation Priority Matrix

| Task | Impact | Effort | Priority |
|------|--------|--------|----------|
| Fix BeautifulSoup import guard | High | Low | **P0 — Now** |
| Fix site_watcher lazy init | Low | Low | **P0 — Now** |
| Update model IDs | Medium | Low | **P0 — Now** |
| Multi-entity UI tabs | High | Low | **P1 — This week** |
| Mobile responsiveness | Medium | Low | **P1 — This week** |
| Rate limiting on API | Medium | Low | **P1 — This week** |
| SQLite persistence | High | Medium | **P2 — Next sprint** |
| Watch mode in dashboard | High | Medium | **P2 — Next sprint** |
| Structured logging | Medium | Medium | **P2 — Next sprint** |
| Alert delivery (Slack/email) | High | Medium | **P3 — Month 2** |
| PDF export | Medium | Medium | **P3 — Month 2** |
| Authentication | Critical | High | **P4 — Pre-launch** |
| PostgreSQL + Redis | High | High | **P4 — Pre-launch** |
| Multi-tenant workspaces | High | Very High | **P5 — v2.0** |

---

## 10. Development Environment Setup

```bash
# 1. Clone repository
git clone https://github.com/YOUR_HANDLE/argus-sentinel
cd argus_sentinel

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
pip install playwright
playwright install chromium

# 4. Copy and configure .env
cp .env.example .env
# Edit .env with your API keys

# 5. Run tests
pytest tests/ -v

# 6. Run CLI (single query)
python main.py --query "What is OpenAI planning?" --verbose

# 7. Run dashboard
python dashboard/app.py
# Open http://localhost:8000

# 8. Run Streamlit UI (alternative)
streamlit run streamlit_app.py
```

---

## 11. Code Quality Standards

- **Type hints** on all public function signatures
- **Docstrings** only on non-obvious classes and methods
- **No magic numbers** — all thresholds in `config.py`
- **Async throughout** — no blocking I/O in async context
- **Exception specificity** — catch specific exceptions, not bare `except Exception`
- **Test coverage** — minimum 70% for core logic (temporal_engine, orchestrator)
- **Linting** — `ruff` with default config (replaces flake8 + isort + black)
