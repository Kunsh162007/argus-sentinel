# App Flow Document
## ARGUS Sentinel — User Journeys & System Flows

**Version:** 1.0  
**Date:** 2026-05-16

---

## 1. Entry Points

ARGUS Sentinel has two entry points that share the same underlying pipeline:

```
                    ┌─────────────────────────┐
                    │       User Entry         │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
       ┌──────▼──────┐  ┌───────▼───────┐  ┌──────▼──────┐
       │ CLI          │  │ Web Dashboard │  │  Watch Mode  │
       │ main.py      │  │ FastAPI + WS  │  │  Scheduled   │
       │ --query      │  │ localhost:8000 │  │  Polling     │
       └──────┬──────┘  └───────┬───────┘  └──────┬──────┘
              │                  │                  │
              └──────────────────┼──────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   ArgusOrchestrator     │
                    │      .run(query)        │
                    └─────────────────────────┘
```

---

## 2. Primary User Journey: Web Dashboard

### 2.1 Initial Load

```
User opens http://localhost:8000
          │
          ▼
Browser loads index.html
          │
          ▼
JavaScript: connect() called
          │
          ▼
WebSocket connects to /ws
          │
  ┌───────┴───────┐
  │ Connected     │ Failed
  │               │
  ▼               ▼
Status dot     Status dot
→ green        → grey
"Connected"    "Reconnecting…"
               (retry in 3s)
          │
          ▼
Server sends: {type: "history", data: [...last 20 reports]}
          │
          ▼
History feed populated (or shows "No queries yet")
          │
          ▼
Empty state shown in main panel:
  - Satellite icon
  - Description text
  - 4 example query chips
```

### 2.2 Running a Query

```
User types query (or clicks example chip)
          │
          ▼
Presses Enter or clicks "Run Intelligence"
          │
          ▼
UI State: setRunning(true)
  - Button disabled → "Running…"
  - Status dot → amber pulsing
  - Empty state hidden
  - Processing state shown
  - Step 1 ("Parsing query intent") → active
          │
          ▼
POST /api/query {query: "...", stream: true}
          │
          ▼ (server side)
ArgusOrchestrator.run() starts
          │
          ▼
WebSocket broadcasts: {type: "status", status: "running"}
  UI: Step 1 active
          │
          ▼
_extract_intent() completes
          │
          ▼
WebSocket broadcasts: {type: "status", status: "agents_deployed"}
  UI: Step 1 ✓ done | Step 2 active
          │
          ▼
All 4 agents collecting in parallel:
  NewsAgent → SERP API (Google + Bing + Yandex)
  FinanceAgent → LinkedIn + Crunchbase + SEC EDGAR
  SiteWatcherAgent → Playwright over Scraping Browser CDP
  SignalMinerAgent → Reddit + HN + GitHub + Product Hunt (via Web Unlocker)
          │
          ▼
Temporal Velocity Engine processes all signals
  UI: Step 3 active
          │
          ▼
ArgusOrchestrator._synthesise() called
  → tries MCP-enhanced Claude call first
  → falls back to direct Claude call
  UI: Step 4 active
          │
          ▼
ArgusReport constructed
          │
          ▼
WebSocket broadcasts: {type: "report", data: report, alert: bool}
          │
          ▼
UI: renderReport(report) called
  - Processing state hidden
  - Report container shown
  - Status dot → green "Connected"
  - Button re-enabled "Run Intelligence"
  - Feed item added to sidebar
          │
  ┌───────┴───────┐
  │ alert: false  │ alert: true
  │               │
  ▼               ▼
Normal report  Alert banner shown at top
               Status dot stays red briefly
```

### 2.3 Viewing a Report

```
Report container shows:
  ┌─────────────────────────────────────────┐
  │ [Alert Banner] (if triggered)           │
  │                                         │
  │ [Velocity Card]                         │
  │   - Composite score (44px, coloured)    │
  │   - Trajectory sparkline                │
  │   - 4 source velocity boxes             │
  │                                         │
  │ [Prediction Card]                       │
  │   - Prediction text                     │
  │   - Confidence progress bar + %         │
  │                                         │
  │ [Signals Card]                          │
  │   - Up to 6 signals with badges         │
  │                                         │
  │ [Executive Summary Card]                │
  │   - Summary paragraph                   │
  │   - Key findings list                   │
  │   - Recommended actions list            │
  │                                         │
  │ Processing time · Powered by Bright Data│
  └─────────────────────────────────────────┘
```

### 2.4 Viewing History

```
User clicks item in right sidebar
          │
          ▼
renderReport(cached_report) called immediately
(no new HTTP request — uses cached data)
          │
          ▼
Main panel updates with historical report
```

---

## 3. CLI User Journey

### 3.1 Single Query

```bash
python main.py --query "Monitor Stripe M&A signals"
```

```
CLI starts
     │
     ▼
Validate API keys (BRIGHT_DATA_API_KEY, BRIGHT_DATA_SERP_KEY)
     │
  missing?
  └──▶ Print error + exit(1)
     │
     ▼
Rich progress spinner: "Running ARGUS Sentinel…"
     │
     ▼
asyncio.run(ArgusOrchestrator().run(query))
     │
     ▼ (same pipeline as dashboard)
ArgusReport returned
     │
     ▼
render_report_rich(report) — if Rich installed
    OR
render_report_plain(report) — fallback
     │
     ▼
save_report(report, "./reports")
  → Saves JSON to ./reports/argus_stripe_1234567890.json
     │
     ▼
Print: "Report saved to ./reports/argus_stripe_1234567890.json"
     │
     ▼
Exit 0
```

### 3.2 Watch Mode

```bash
python main.py --query "OpenAI launch signals" --watch --interval 15
```

```
Print: "ARGUS Watch mode — polling every 15m"
Print: "Query: OpenAI launch signals"
     │
     ▼ loop:
Run #1 at HH:MM:SS
  → Full pipeline run
  → render_report()
  → save_report()
  → if alert_triggered: print "ALERT — Check report above."
  → Print: "Next run in 15 minutes…"
  → await asyncio.sleep(900)
Run #2 at HH:MM:SS
  → (velocity windows now have 2 snapshots — velocity meaningful)
  ...continues forever
```

**Key behaviour:** On second and subsequent runs, the temporal engine has historical snapshots. Velocity scores become meaningful. If the same entity is trending, trajectory slope turns positive.

### 3.3 Dashboard Launch

```bash
python main.py --dashboard
```

```
Print: "Starting ARGUS Sentinel dashboard…"
Print: "Open http://localhost:8000"
     │
     ▼
uvicorn.run(app, host="0.0.0.0", port=8000)
     │
     ▼
Blocks — serves until Ctrl+C
```

---

## 4. Agent Collection Flow (Detail)

### 4.1 News Agent Flow

```
NewsAgent.collect(entity, query)
     │
     ├── serp_news_multi_engine(f"{entity} {query}", lookback_days=7)
     │     ├── serp_search(query, engine="google", time_range="w")
     │     ├── serp_search(query, engine="bing",   time_range="w")  [parallel]
     │     └── serp_search(query, engine="yandex", time_range="w")
     │         └── Deduplicate by URL → flat list[dict]
     │
     └── serp_news_multi_engine(entity, lookback_days=1)  [24h pulse]
           └── Same fan-out, tbs="d"
     │
     ▼
For each result:
  _result_to_signal(result, entity):
    - Extract: url, title, snippet, date, source_domain
    - _compute_weight(domain, content) → 0.4/0.7/0.9 by tier + keyword boost
    - _detect_sentiment(content) → positive/negative/neutral
    - → ArgusSignal(source="news", weight=w, metadata={sentiment,...})

Return list[ArgusSignal]
```

### 4.2 Finance Agent Flow

```
FinanceAgent.collect(entity, query)
     │
     ├── _collect_linkedin(entity)   [parallel]
     │     scraper_api_fetch(linkedin_dataset_id, [{company_name: entity}])
     │       → Poll snapshot until ready
     │       → Parse: headcount, open_roles, recent_hires (exec signal)
     │       → Emit ArgusSignal per data point
     │
     ├── _collect_crunchbase(entity) [parallel]
     │     scraper_api_fetch(crunchbase_dataset_id, [{company: entity}])
     │       → Parse: funding_rounds, total_funding_usd
     │       → weight = min(0.5 + amount_B, 0.98)
     │
     └── _collect_sec_filings(entity) [parallel]
           scraper_api_fetch(sec_edgar_dataset_id,
             [{company: entity, filing_types: ["8-K","S-1","DEFM14A","SC 13D"]}])
           → FILING_WEIGHTS: S-1=1.0, 8-K=0.9, DEFM14A=0.85, ...

Return merged list[ArgusSignal]
```

### 4.3 Site Watcher Flow

```
SiteWatcherAgent.collect(entity, query)
     │
     ▼
_resolve_domain(entity):
  Try: {entity}.com, {entity}.ai, {entity}.io (via Scraping Browser)
  Fallback: SERP search for "{entity} official website"
     │
     ▼
watch_urls = [domain + path for path in WATCH_PATHS]
  /  /pricing  /docs  /blog  /changelog  /release-notes
  /products  /research  /api  /careers
     │
     ▼ [all paths in parallel]
For each URL: _watch_url(url, entity)
     │
     ▼
scraping_browser_fetch(url, scroll=True, screenshot=True)
     │
     ├── 1. Content hash diff
     │     MD5(text_content) vs cached hash
     │     If changed ≥ 8%: emit "Page content changed X%" signal
     │
     ├── 2. Navigation structure change
     │     Extract nav links from <nav>, <header>
     │     Diff against cached set
     │     New nav item → weight=0.85 if product keyword, else 0.65
     │     Removed item → weight=0.70
     │
     ├── 3. New blog/changelog entry
     │     Find articles with "post|entry|item|changelog" class
     │     Hash title → emit if not seen before (weight=0.75)
     │
     └── 4. Pricing change
           Find $N / "per month" / "per seat" text
           Hash price list → emit if changed (weight=0.80)
```

### 4.4 Signal Miner Flow

```
SignalMinerAgent.collect(entity, query)
     │
     ├── _collect_reddit(entity, query)    [parallel]
     │     unlock(reddit search JSON, render_js=False)
     │     Parse JSON posts: score, comments, subreddit
     │     weight = 0.4 + engagement(0-1) + hype_boost(0.2)
     │
     ├── _collect_hn(entity, query)         [parallel]
     │     unlock(HN Algolia API, render_js=False)
     │     Parse hits: points, num_comments
     │     weight = 0.45 + engagement(0-1) + hype_boost(0.2)
     │
     ├── _collect_github(entity)            [parallel]
     │     unlock(GitHub search, render_js=True)
     │     Top 3 repos → check /graphs/commit-activity
     │     Extract commits_this_week count
     │     weight = 0.3 + count/100
     │
     └── _collect_producthunt(entity)       [parallel]
           unlock(PH search, render_js=True)
           Find items matching entity in name/tagline
           weight = 0.5 + votes/500

Return merged list[ArgusSignal]
```

---

## 5. Temporal Velocity Engine Flow

```
TemporalVelocityEngine.process(entity, all_signals, new_signals)
     │
     ├── 1. Group signals by source, sum weights
     │     source_counts = {news: 4.2, finance: 2.1, site: 0.0, social: 3.8}
     │
     ├── 2. Push counts to VelocityWindow per source
     │     window.counts = [..., 4.2]  (max 10 entries)
     │
     ├── 3. Compute per-source velocity
     │     velocity = clamp((recent_avg - baseline_avg) / baseline_avg × 5, 0, 10)
     │
     ├── 4. Weighted composite
     │     composite = Σ velocity[s] × weight[s]
     │     (news=0.28, finance=0.32, site=0.22, social=0.18)
     │
     ├── 5. Cross-domain amplification
     │     if sources_above_3.0 >= 3: composite ×= 1.4
     │
     ├── 6. Trajectory history
     │     composite_history[entity].append(composite)
     │     (max 20 entries)
     │
     ├── 7. Trajectory slope
     │     Linear regression on composite_history → slope
     │
     ├── 8. Anomaly detection
     │     z-score of latest vs history
     │     if z > 2.5: anomaly = True
     │
     ├── 9. Sort top signals by weight (top 8)
     │
     └── 10. LLM Prediction
           Claude Sonnet → JSON {prediction, confidence, timeframe_days, event_category}
           Fallback heuristic if LLM fails:
             score ≥ 8 → "Major announcement imminent" (78%)
             score ≥ 5 → "Elevated activity, monitor" (55%)
             else → "Baseline activity" (35%)
```

---

## 6. Error & Edge Case Flows

### 6.1 Agent Failure

```
Agent.run_and_snapshot() catches exception
  → logger.error("Agent failed: ...")
  → Returns ([], []) — empty signals
  
Orchestrator._process_entity():
  → asyncio.gather(*[agent.run()], return_exceptions=True)
  → Checks isinstance(r, Exception), logs warning
  → Continues with signals from non-failed agents
  
TemporalVelocityEngine.process():
  → Still runs with partial signals
  → Source velocities will show 0.0 for failed agent source
  → Composite still computed from available sources
```

### 6.2 LLM Call Failure

```
_generate_prediction() → LLM raises Exception
  → logger.warning()
  → Heuristic fallback:
      score ≥ 8 → "High-velocity surge… Likely major announcement", confidence=0.78
      score ≥ 5 → "Elevated activity… Monitor closely", confidence=0.55
      else      → "Baseline activity… No imminent events", confidence=0.35
```

### 6.3 MCP Synthesis Failure

```
_synthesise():
  try: _synthesise_with_mcp()
  except: logger.warning() → _synthesise_direct()
  
_synthesise_direct():
  try: json.loads(response_text)
  except: return (text[:400], [], [])  # Best-effort text fallback
```

### 6.4 Missing Bright Data API Key

```
main.py startup:
  if not CONFIG.bright_data.api_key:
    missing.append("BRIGHT_DATA_API_KEY")
  if not CONFIG.bright_data.serp_key:
    missing.append("BRIGHT_DATA_SERP_KEY")
  if missing:
    print error + "Copy .env.example to .env"
    sys.exit(1)
```

### 6.5 Playwright Not Available

```
SiteWatcherAgent._watch_url():
  if not PLAYWRIGHT_AVAILABLE:
    logger.debug("Playwright not available — skipping Scraping Browser")
    return []
  
Result: site velocity = 0.0 for all entities
Composite still computed from news + finance + social
```

---

## 7. Data State Management

### 7.1 In-Memory State (v1)

| Object | Scope | Lifetime |
|--------|-------|----------|
| `report_history` | Dashboard process | Until restart (max 500) |
| `active_connections` | Dashboard process | Until disconnect |
| `TemporalVelocityEngine._windows` | Orchestrator instance | Per CLI run OR dashboard process |
| `TemporalVelocityEngine._composite_history` | Same | Same |
| `BaseAgent._history` | Per agent instance | Per CLI run |
| `BaseAgent._seen_fingerprints` | Per agent instance | Per CLI run |
| `SiteWatcherAgent._page_hashes` | Per agent instance | Per CLI run |

**Critical limitation:** In CLI single-run mode, velocity windows only have 1 data point. Velocity scores are meaningful only in watch mode (multiple runs) or dashboard mode (multiple queries for the same entity).

### 7.2 Persistence (v2 Improvement)

```
Redis (or SQLite for simplest case):
  - velocity_windows:{entity}:{source} → VelocityWindow serialised
  - composite_history:{entity} → list[float]
  - reports:{id} → ArgusReport JSON
  - fingerprints:{agent}:{entity} → set of fingerprint hashes
```

---

## 8. WebSocket Protocol

```
Client → Server:
  (no messages sent from client over WS — REST POST used for queries)

Server → Client:
  {type: "history",  data: [...ArgusReport]}        on connect
  {type: "status",   status: "running", query: "..."} on query start
  {type: "status",   status: "agents_deployed", query: "..."}
  {type: "report",   data: ArgusReport, alert: bool} on completion
  {type: "error",    message: "..."}                 on failure
  {type: "ping",     ts: 1234567890}                 every 20s keepalive
```

---

## 9. Report File Naming

```
./reports/argus_{entity_slug}_{unix_timestamp}.json

Examples:
  argus_openai_1747390331.json
  argus_stripe_1747390892.json
  argus_anthropic_vs_deepmind_1747391201.json

entity_slug = entities[0].lower().replace(" ", "_")
```
