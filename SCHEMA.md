# Backend Schema Document
## ARGUS Sentinel — Data Models & Storage Architecture

**Version:** 1.0  
**Date:** 2026-05-16

---

## 1. Overview

ARGUS Sentinel v1 uses in-memory state exclusively. This document defines:
1. All Python dataclass schemas (current v1)
2. JSON serialisation formats (report files + API responses)
3. WebSocket message schemas
4. Proposed database schema for v2 persistence

---

## 2. Python Dataclass Schemas (v1)

### 2.1 ArgusSignal

The atomic unit of intelligence — a single observed signal from any source.

```python
@dataclass
class ArgusSignal:
    source:      str    # Enum: "news" | "finance" | "site" | "social"
    signal_type: str    # Enum: "mention" | "sentiment" | "change" | "filing" | "hiring"
    entity:      str    # Entity being tracked, e.g. "OpenAI"
    content:     str    # Human-readable description (max ~200 chars practical limit)
    url:         str    # Source URL (canonical, deduplicated)
    timestamp:   float  # Unix timestamp (seconds)
    weight:      float  # 0.0–1.0 importance score
    metadata:    dict   # Source-specific structured data (see below)
```

**Metadata schemas by source:**

```python
# news
metadata = {
    "source_domain": "reuters.com",    # str
    "sentiment":     "positive",       # "positive" | "negative" | "neutral"
    "date_str":      "2026-05-14",     # str, raw date from SERP result
}

# finance (LinkedIn)
metadata = {
    "headcount":  25000,               # int
    "open_roles": 432,                 # int
    "platform":   "linkedin",          # str
}

# finance (Crunchbase)
metadata = {
    "round": {                         # dict
        "funding_type":    "Series D",
        "raised_amount_usd": 500000000,
        "lead_investors":  ["Sequoia", "a16z"],
        "announced_on":    "2026-04-20",
    },
    "signal_class": "funding",         # str
}

# finance (SEC EDGAR)
metadata = {
    "form_type":   "8-K",             # str
    "filed_date":  "2026-05-13",      # str
    "signal_class": "sec_filing",     # str
}

# site (content change)
metadata = {
    "change_pct":      0.142,         # float (14.2% content changed)
    "has_screenshot":  True,          # bool
}

# site (nav change)
metadata = {
    "nav_item":    "models",          # str
    "signal_class": "nav_addition",  # "nav_addition" | "nav_removal"
}

# site (pricing change)
metadata = {
    "price_samples": ["$20/month", "$50/seat"],  # list[str]
    "signal_class":  "pricing",                  # str
}

# social (Reddit)
metadata = {
    "platform":         "reddit",     # str
    "subreddit":        "MachineLearning",  # str
    "score":            4820,         # int (upvotes)
    "comments":         312,          # int
    "has_hype_keywords": True,        # bool
}

# social (Hacker News)
metadata = {
    "platform":     "hackernews",    # str
    "points":       842,             # int
    "num_comments": 247,             # int
    "story_url":    "https://...",   # str (original article, if any)
}

# social (GitHub)
metadata = {
    "platform": "github",            # str
    "repo":     "openai/gpt-5",     # str
    "commits":  47,                  # int
}

# social (Product Hunt)
metadata = {
    "platform": "producthunt",       # str
    "votes":    389,                 # int
}
```

**Fingerprint:**
```python
fingerprint = MD5(f"{source}:{url}:{content[:80]}")  # hex string
```

---

### 2.2 AgentSnapshot

One collection run from a single agent for one entity.

```python
@dataclass
class AgentSnapshot:
    agent_name:   str                  # "news" | "finance" | "site" | "signal"
    entity:       str                  # Entity name
    timestamp:    float                # Unix timestamp of collection
    signals:      list[ArgusSignal]    # All signals collected
    signal_count: int                  # Auto-derived: len(signals)
    fingerprints: set[str]             # Auto-derived: {s.fingerprint() for s in signals}
```

**Storage:** Dict `{entity: list[AgentSnapshot]}` per agent instance, max 10 snapshots per entity.

---

### 2.3 VelocityWindow

Rolling window of signal counts for one source per entity.

```python
@dataclass
class VelocityWindow:
    source:     str          # "news" | "finance" | "site" | "social"
    counts:     list[float]  # Weighted signal counts, most recent last
    timestamps: list[float]  # Corresponding collection timestamps
    max_window: int = 10     # Max entries before oldest evicted
```

**Computed properties:**
```python
@property
def baseline(self) -> float:
    # Mean of all counts except last 2 (or last count if < 3 entries)
    
@property
def recent(self) -> float:
    # Mean of last 2 counts
    
@property
def velocity(self) -> float:
    # clamp((recent - baseline) / baseline × 5, 0, 10)
    
@property
def slope(self) -> float:
    # Linear regression slope across all counts
```

**Storage:** Nested dict `{entity: {source: VelocityWindow}}` in `TemporalVelocityEngine._windows`.

---

### 2.4 TemporalProfile

Complete intelligence profile for one entity at one point in time.

```python
@dataclass
class TemporalProfile:
    entity:                str
    timestamp:             float         # Unix timestamp of computation
    velocity_score:        float         # 0–10, rounded to 2dp
    source_velocities:     dict[str, float]  # {source: velocity}
    trajectory:            list[float]   # Last 10 composite scores
    trajectory_slope:      float         # Linear regression slope
    prediction:            str           # NL prediction (1–2 sentences)
    prediction_confidence: float         # 0.0–1.0
    anomaly_detected:      bool
    top_signals:           list[dict]    # Serialised ArgusSignals, top 8
    alert:                 bool
```

**JSON serialisation (`.to_dict()`):**
```json
{
  "entity": "OpenAI",
  "timestamp": 1747390331.42,
  "velocity_score": 8.7,
  "source_velocities": {
    "news":    7.2,
    "finance": 9.1,
    "site":    5.4,
    "social":  8.8
  },
  "trajectory": [2.1, 3.4, 4.8, 6.2, 8.7],
  "trajectory_slope": 1.65,
  "prediction": "High probability of a major model announcement within 14 days",
  "prediction_confidence": 0.82,
  "anomaly_detected": true,
  "top_signals": [
    {
      "source": "news",
      "signal_type": "mention",
      "entity": "OpenAI",
      "content": "3× increase in GPT-5 mentions in 48h — Reuters",
      "url": "https://reuters.com/...",
      "timestamp": 1747390000.0,
      "weight": 0.91,
      "metadata": {"source_domain": "reuters.com", "sentiment": "positive"}
    }
  ],
  "alert": true
}
```

---

### 2.5 QueryIntent

Structured intent extracted from raw query by Claude.

```python
@dataclass
class QueryIntent:
    entities:       list[str]   # Max 3 entities
    intent:         str         # "monitor" | "investigate" | "predict" | "compare"
    domain:         str         # "product" | "financial" | "competitive" | "general"
    timeframe_days: int         # How far ahead to predict
    urgency:        str         # "immediate" | "scheduled" | "background"
    raw_query:      str         # Original user query
```

---

### 2.6 ArgusReport

Top-level intelligence output for a query.

```python
@dataclass
class ArgusReport:
    query:               str
    entities:            list[str]
    timestamp:           float
    profiles:            list[TemporalProfile]
    executive_summary:   str
    key_findings:        list[str]
    recommended_actions: list[str]
    alert_triggered:     bool
    processing_time_s:   float
```

**JSON serialisation (`.to_dict()`):**
```json
{
  "query": "What is OpenAI planning to launch?",
  "entities": ["OpenAI"],
  "timestamp": 1747390331.42,
  "profiles": [ /* TemporalProfile.to_dict() array */ ],
  "executive_summary": "OpenAI exhibits unusually high cross-domain velocity...",
  "key_findings": [
    "3× mention velocity increase in 48 hours across Tier-1 press",
    "SEC 8-K filing for material event detected"
  ],
  "recommended_actions": [
    "Monitor OpenAI blog and documentation hourly",
    "Alert key stakeholders"
  ],
  "alert_triggered": true,
  "processing_time_s": 42.3
}
```

---

## 3. WebSocket Message Schemas

All messages are JSON objects sent server → client.

```json
// On client connect — replay recent history
{"type": "history", "data": [ArgusReport, ...]}

// Query started
{"type": "status", "status": "running", "query": "...", "ts": 1747390331}

// Agents deployed
{"type": "status", "status": "agents_deployed", "query": "...", "ts": 1747390332}

// Report complete
{"type": "report", "data": ArgusReport, "alert": true}

// Error
{"type": "error", "message": "LLM call timed out"}

// Keepalive
{"type": "ping", "ts": 1747390351}
```

---

## 4. Report File Schema (JSON on disk)

Files saved to `./reports/argus_{entity}_{timestamp}.json`.

Complete schema = `ArgusReport.to_dict()` with all nested objects serialised.

**File naming convention:**
```
argus_{entities[0].lower().replace(" ","_")}_{int(timestamp)}.json
```

---

## 5. Configuration Schemas

### `.env` file

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...
BRIGHT_DATA_API_KEY=...
BRIGHT_DATA_SERP_KEY=...

# Optional (for proxy support)
BRIGHT_DATA_CUSTOMER_ID=brd-customer-xxx
BRIGHT_DATA_PROXY_PASS=...

# Optional overrides
ARGUS_ALERT_THRESHOLD=6.5
ARGUS_SNAPSHOT_WINDOW=5
ARGUS_OUTPUT_DIR=./reports
ARGUS_LOG_LEVEL=INFO
```

### Bright Data Dataset IDs (in `config.py`)

```python
linkedin_dataset_id   = "gd_l1viktl72bvl7bjuj"   # LinkedIn Company
crunchbase_dataset_id = "gd_l1vikfnt16wg0b9pe"   # Crunchbase Funding
sec_edgar_dataset_id  = "gd_lxfe4bnt1ikf3bm0x6"  # SEC EDGAR Filings
```

---

## 6. Proposed v2 Database Schema (PostgreSQL)

For persistent multi-session state, report history, and horizontal scaling.

### 6.1 Tables

#### `entities`
```sql
CREATE TABLE entities (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255) NOT NULL UNIQUE,
    slug        VARCHAR(255) NOT NULL UNIQUE,    -- "openai", "stripe"
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

#### `reports`
```sql
CREATE TABLE reports (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query               TEXT NOT NULL,
    entity_ids          UUID[] NOT NULL,
    timestamp           TIMESTAMPTZ NOT NULL,
    velocity_score      FLOAT,                  -- max across profiles
    alert_triggered     BOOLEAN DEFAULT FALSE,
    processing_time_s   FLOAT,
    executive_summary   TEXT,
    key_findings        JSONB,                  -- list[str]
    recommended_actions JSONB,                  -- list[str]
    raw_json            JSONB NOT NULL,         -- full ArgusReport.to_dict()
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT reports_timestamp_idx UNIQUE (query, timestamp)
);

CREATE INDEX idx_reports_alert ON reports (alert_triggered) WHERE alert_triggered = TRUE;
CREATE INDEX idx_reports_created ON reports (created_at DESC);
```

#### `profiles`
```sql
CREATE TABLE profiles (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id             UUID REFERENCES reports(id) ON DELETE CASCADE,
    entity_id             UUID REFERENCES entities(id),
    timestamp             TIMESTAMPTZ NOT NULL,
    velocity_score        FLOAT NOT NULL,
    source_velocities     JSONB NOT NULL,        -- {news: 7.2, finance: 9.1, ...}
    trajectory            FLOAT[] NOT NULL,
    trajectory_slope      FLOAT,
    prediction            TEXT,
    prediction_confidence FLOAT,
    anomaly_detected      BOOLEAN DEFAULT FALSE,
    alert                 BOOLEAN DEFAULT FALSE,
    top_signals           JSONB,                 -- list[ArgusSignal.to_dict()]
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_profiles_entity ON profiles (entity_id, timestamp DESC);
CREATE INDEX idx_profiles_velocity ON profiles (velocity_score DESC);
```

#### `velocity_windows` (Redis alternative as SQL fallback)
```sql
CREATE TABLE velocity_windows (
    entity_id   UUID REFERENCES entities(id),
    source      VARCHAR(20) NOT NULL,
    counts      FLOAT[] NOT NULL DEFAULT '{}',
    timestamps  FLOAT[] NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (entity_id, source)
);
```

#### `signals`
```sql
CREATE TABLE signals (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id  UUID REFERENCES profiles(id) ON DELETE CASCADE,
    source      VARCHAR(20) NOT NULL,
    signal_type VARCHAR(30) NOT NULL,
    entity_id   UUID REFERENCES entities(id),
    content     TEXT NOT NULL,
    url         TEXT,
    signal_ts   TIMESTAMPTZ,
    weight      FLOAT NOT NULL,
    metadata    JSONB,
    fingerprint VARCHAR(32) UNIQUE,            -- MD5 hex for deduplication
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_signals_fingerprint ON signals (fingerprint);
CREATE INDEX idx_signals_entity_source ON signals (entity_id, source, signal_ts DESC);
```

#### `alerts`
```sql
CREATE TABLE alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id       UUID REFERENCES reports(id),
    entity_id       UUID REFERENCES entities(id),
    velocity_score  FLOAT NOT NULL,
    trigger_reason  VARCHAR(50),   -- "velocity_threshold" | "anomaly" | "confidence"
    notified_slack  BOOLEAN DEFAULT FALSE,
    notified_email  BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### 6.2 Redis Schema (Velocity Windows)

For high-frequency velocity window updates across multiple processes:

```
# Velocity window (sorted list, newest last)
key:   argus:vw:{entity_slug}:{source}:counts
type:  List[float]
ttl:   7 days

key:   argus:vw:{entity_slug}:{source}:timestamps  
type:  List[float]
ttl:   7 days

# Composite history
key:   argus:composite:{entity_slug}
type:  List[float] (max 20)
ttl:   7 days

# Signal fingerprints (dedup)
key:   argus:fp:{agent}:{entity_slug}
type:  Set[str]
ttl:   24 hours

# Report history (for dashboard)
key:   argus:history
type:  List[JSON string] (max 500, LPUSH + LTRIM)
ttl:   permanent
```

---

## 7. LLM Prompt/Response Schemas

### 7.1 Intent Extraction

**Input prompt:**
```
Extract intelligence query intent from: "{query}"

Return ONLY a JSON object:
{"entities":["Company"],"intent":"monitor|investigate|predict|compare",
"domain":"product|financial|competitive|general","timeframe_days":14,
"urgency":"immediate|scheduled|background"}
```

**Expected response:**
```json
{
  "entities": ["OpenAI"],
  "intent": "predict",
  "domain": "product",
  "timeframe_days": 30,
  "urgency": "immediate"
}
```

### 7.2 Temporal Prediction

**Input prompt:** (see `temporal_engine.py:_generate_prediction()`)

**Expected response:**
```json
{
  "prediction": "High probability of a major model announcement within 14 days based on 3× mention velocity and SEC material event filing",
  "confidence": 0.82,
  "timeframe_days": 14,
  "event_category": "product"
}
```

### 7.3 Synthesis

**Input prompt:** (see `orchestrator.py:_synthesise_direct()`)

**Expected response:**
```json
{
  "executive_summary": "OpenAI exhibits unusually high cross-domain velocity...",
  "key_findings": [
    "Mention velocity increased 3× in 48 hours across Tier-1 press sources",
    "SEC 8-K material event filing detected on 2026-05-13",
    "LinkedIn open roles in AI Research increased 40% in 30 days"
  ],
  "recommended_actions": [
    "Monitor OpenAI blog and documentation sections every 15 minutes",
    "Alert product and business development teams",
    "Prepare competitive response brief"
  ]
}
```

---

## 8. Source Weight Configuration

### Agent Source Weights (Temporal Engine)

```python
SOURCE_WEIGHTS = {
    "news":    0.28,   # High volume, early signal, moderate precision
    "finance": 0.32,   # Low volume, high precision, authoritative
    "site":    0.22,   # Medium precision, structural pre-announcement signal
    "social":  0.18,   # High noise, fastest to react
}
```

### News Source Tier Weights (News Agent)

```python
TIER_1_WEIGHT = 0.9   # reuters, bloomberg, ft, wsj, techcrunch, ...
TIER_2_WEIGHT = 0.7   # venturebeat, zdnet, engadget, ...
DEFAULT_WEIGHT = 0.4  # Unknown sources

KEYWORD_BOOST = +0.1  # Applied if high-signal keywords in content
MAX_WEIGHT = 1.0
```

### SEC Filing Weights (Finance Agent)

```python
FILING_WEIGHTS = {
    "S-1":     1.0,    # IPO filing — maximum signal
    "8-K":     0.9,    # Material event
    "SC 13D":  0.9,    # Activist stake
    "DEFM14A": 0.85,   # Merger proxy
    "SC 13G":  0.8,    # Large acquisition
    "10-K":    0.6,    # Annual report
    "4":       0.7,    # Insider transaction
    "10-Q":    0.5,    # Quarterly report
}
```
