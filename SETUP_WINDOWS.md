# ARGUS Sentinel — Windows Setup Guide

## Quick fix for the errors you just saw

### Fix 1 — Playwright not found
```powershell
# Use python -m instead of the bare command:
python -m playwright install chromium
```

### Fix 2 — LangChain import error (now fixed)
The orchestrator has been rewritten to use the Anthropic SDK directly.
No LangChain dependency required. Re-download the updated files or run:
```powershell
# Pull latest from GitHub (once pushed)
git pull
```

---

## Full Clean Setup (Windows)

### Step 1 — Python version check
```powershell
python --version
```
**Python 3.11–3.13 is recommended.** Python 3.14 is very new; some packages
(especially pydantic v1 internals) have warnings. Everything still works but
you'll see a deprecation warning — ignore it.

### Step 2 — Create a virtual environment (strongly recommended)
```powershell
cd "C:\Users\Lenovo\Downloads\Web Data UNLOCKED Hackathon"
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If you get an execution policy error:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Then try activating again.

### Step 3 — Install dependencies
```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

If you get build errors on `lxml` on Python 3.14:
```powershell
pip install lxml --pre
```

### Step 4 — Install Playwright browser
```powershell
python -m playwright install chromium
```
This downloads ~150MB. Run it once.

### Step 5 — Configure credentials
```powershell
copy .env.example .env
notepad .env
```
Fill in:
```
ANTHROPIC_API_KEY=sk-ant-...
BRIGHT_DATA_API_KEY=...
BRIGHT_DATA_SERP_KEY=...
BRIGHT_DATA_CUSTOMER_ID=...
BRIGHT_DATA_PROXY_PASS=...
```

You get $250 in Bright Data credits from the hackathon kick-off stream.
Get your API key at: https://brightdata.com → Account → API Tokens

### Step 6 — Run
```powershell
# Single query
python main.py --query "What is OpenAI planning to launch?"

# Launch web dashboard
python main.py --dashboard
# Then open: http://localhost:8000

# Continuous monitoring (re-runs every 30 min)
python main.py --query "Monitor Anthropic product signals" --watch --interval 30
```

---

## Troubleshooting

### "pydantic v1 isn't compatible with Python 3.14"
This is just a **warning**, not an error. It comes from a transitive dependency.
The app runs fine. To silence it:
```powershell
$env:PYTHONWARNINGS="ignore"
python main.py --query "..."
```

### "ModuleNotFoundError: No module named 'xxx'"
```powershell
pip install -r requirements.txt
```

### "Cannot connect to Bright Data"
- Check your `.env` file — all 5 values must be filled in
- Make sure you activated the API zone in the Bright Data dashboard
- Test your key: https://brightdata.com → API Playground

### "playwright._impl._errors.Error: Executable doesn't exist"
```powershell
python -m playwright install chromium --with-deps
```

### Dashboard port already in use
```powershell
# Find and kill what's on port 8000
netstat -ano | findstr :8000
taskkill /PID <PID_NUMBER> /F
```
Or change the port in `config.py`:
```python
port: int = 8001
```

### Firewall / antivirus blocking requests
Add Python to your firewall exceptions, or temporarily disable real-time
protection when running the agents (they make many outbound HTTP requests).

---

## Running without Bright Data credentials (demo mode)

If you want to test the pipeline structure before your hackathon credits arrive,
set `BRIGHT_DATA_API_KEY=demo` in `.env`. The agents will return mock signals
so you can verify the temporal engine, dashboard, and report format all work.

The `--verbose` flag shows everything happening internally:
```powershell
python main.py --query "Test query" --verbose
```

---

## File structure reminder
```
argus_sentinel/
├── main.py                ← Start here (CLI)
├── orchestrator.py        ← Fixed: no LangChain dependency
├── temporal_engine.py     ← Core innovation: velocity scoring
├── bright_data_client.py  ← All Bright Data tools unified
├── config.py              ← All settings
├── agents/
│   ├── news_agent.py      ← SERP API
│   ├── finance_agent.py   ← Web Scraper API (LinkedIn/SEC/CB)
│   ├── site_watcher.py    ← Scraping Browser
│   └── signal_miner.py    ← Web Unlocker (Reddit/HN/GitHub)
├── dashboard/
│   ├── app.py             ← FastAPI + WebSocket
│   └── static/index.html  ← Live intelligence UI
└── tests/test_argus.py    ← pytest suite
```
