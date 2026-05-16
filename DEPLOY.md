# ARGUS Sentinel — Deployment Guide

Three paths from easiest to most robust. Pick one.

---

## PATH A — Streamlit Cloud (easiest, 5 minutes, free)

Best for: hackathon demo, no DevOps needed, public URL instantly.

### Step 1 — Push to GitHub

```powershell
# In your project folder:
git init
git add .
git commit -m "ARGUS Sentinel — initial commit"
```

Go to https://github.com/new → create a repo (e.g. `argus-sentinel`) → then:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/argus-sentinel.git
git branch -M main
git push -u origin main
```

### Step 2 — Deploy on Streamlit Cloud

1. Go to **https://share.streamlit.io**
2. Sign in with GitHub
3. Click **New app**
4. Fill in:
   - Repository: `YOUR_USERNAME/argus-sentinel`
   - Branch: `main`
   - Main file path: `streamlit_app.py`
5. Click **Advanced settings → Secrets** and paste:

```toml
ANTHROPIC_API_KEY = "sk-ant-api03-..."
BRIGHT_DATA_API_KEY = "..."
BRIGHT_DATA_SERP_KEY = "..."
BRIGHT_DATA_CUSTOMER_ID = "..."
BRIGHT_DATA_PROXY_PASS = "..."
```

6. Click **Deploy**

You get a public URL like `https://argus-sentinel-abc123.streamlit.app` in ~2 minutes.

> **Note:** Streamlit Cloud doesn't support Playwright. The Site Watcher agent
> gracefully skips and the other 3 agents (News, Finance, Signal Miner) run fully.
> This is fine for the hackathon demo.

---

## PATH B — Railway (full Docker deploy, ~10 minutes, free tier)

Best for: full app including Scraping Browser (Playwright), permanent URL.

### Step 1 — Push to GitHub (same as Path A Step 1)

### Step 2 — Deploy on Railway

1. Go to **https://railway.app** → sign in with GitHub
2. Click **New Project → Deploy from GitHub repo**
3. Select your `argus-sentinel` repository
4. Railway auto-detects the `Dockerfile` and builds it

### Step 3 — Add environment variables

In Railway dashboard → your project → **Variables** tab → add:

```
ANTHROPIC_API_KEY     = sk-ant-api03-...
BRIGHT_DATA_API_KEY   = ...
BRIGHT_DATA_SERP_KEY  = ...
BRIGHT_DATA_CUSTOMER_ID = ...
BRIGHT_DATA_PROXY_PASS  = ...
```

### Step 4 — Add a public domain

Railway dashboard → your project → **Settings → Domains → Generate Domain**

You get a URL like `https://argus-sentinel-production.up.railway.app`

> Railway free tier gives $5/month credit — enough for the hackathon demo period.

---

## PATH C — Render (alternative to Railway)

1. Go to **https://render.com** → New → Web Service
2. Connect your GitHub repo
3. Render detects `render.yaml` automatically
4. Set environment variables in the Render dashboard (same 5 keys)
5. Deploy → get a `https://argus-sentinel.onrender.com` URL

> Render free tier spins down after inactivity — add `?wakeup=1` to your first
> request if it's slow. Paid tier ($7/mo) keeps it always-on.

---

## PATH D — Local + ngrok (instant public URL, no GitHub needed)

Best for: immediate demo without pushing code anywhere.

### Step 1 — Install ngrok

```powershell
# Download from https://ngrok.com/download
# Or with winget:
winget install ngrok
```

### Step 2 — Run the dashboard locally

```powershell
# In your project folder with .venv activated:
python dashboard/app.py
```

Dashboard starts at http://localhost:8000

### Step 3 — Expose with ngrok

```powershell
# In a second PowerShell window:
ngrok http 8000
```

ngrok gives you a public URL like `https://abc123.ngrok-free.app`
Share that URL as your demo link. Works immediately, no deployment needed.

> Free ngrok URLs change every session. For a persistent URL, use ngrok's
> free account (sign up at ngrok.com) and run `ngrok config add-authtoken YOUR_TOKEN`

---

## Quickest path summary

| Path | Time | URL type | Playwright | Cost |
|------|------|----------|------------|------|
| Streamlit Cloud | 5 min | Permanent | ❌ (3/4 agents) | Free |
| Railway | 10 min | Permanent | ✅ (all agents) | Free tier |
| Render | 10 min | Permanent | ✅ (all agents) | Free tier |
| ngrok local | 2 min | Temporary | ✅ (all agents) | Free |

**For the hackathon submission:** Use Railway or Streamlit Cloud for the permanent
Application URL field. Use ngrok if you need something working in the next 5 minutes.

---

## After deployment — test it

```
GET  https://YOUR_URL/api/health     → {"status":"ok"}
POST https://YOUR_URL/api/query      → runs intelligence pipeline
WS   wss://YOUR_URL/ws               → real-time alert stream
```
