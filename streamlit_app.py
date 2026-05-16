"""
ARGUS Sentinel — Streamlit Cloud App
Deploy in 3 minutes at share.streamlit.io — no Docker needed.
"""

import asyncio
import json
import sys
import os
import time

import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))

# ── Page config ─────────────────────────────────────────────────
st.set_page_config(
    page_title="ARGUS Sentinel",
    page_icon="🛰",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .block-container { padding-top: 1.5rem; }
  .metric-box {
    background: #1a1d24;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px;
    padding: 16px;
    text-align: center;
  }
  .stButton > button {
    background: #5b8df8;
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    width: 100%;
    padding: 0.6rem 1rem;
  }
  .stButton > button:hover { background: #3d6ee8; }
  div[data-testid="stAlert"] { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)


# ── Score colour helper ─────────────────────────────────────────
def score_colour(v: float) -> str:
    if v >= 8:   return "🔴"
    if v >= 5:   return "🟠"
    if v >= 3:   return "🟡"
    return "⚪"


def badge(source: str) -> str:
    return {"news": "🔵", "finance": "🟢", "site": "🩵", "social": "🟣"}.get(source, "⚪")


# ── Async runner helper ─────────────────────────────────────────
def run_async(coro):
    """Run async coroutine from Streamlit's sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ── Sidebar ─────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🛰 ARGUS Sentinel")
    st.markdown("*Temporal Web Intelligence*")
    st.divider()

    st.markdown("### Credentials")
    anthropic_key = st.text_input(
        "Anthropic API Key", type="password",
        placeholder="sk-ant-api03-…",
        help="Get from console.anthropic.com/account/keys",
    )
    bd_key = st.text_input(
        "Bright Data API Key", type="password",
        placeholder="From brightdata.com → Account",
    )
    bd_serp = st.text_input(
        "Bright Data SERP Key", type="password",
        placeholder="From brightdata.com → SERP API",
    )
    bd_customer = st.text_input("BD Customer ID", placeholder="hl_xxxxxxxx")
    bd_proxy_pass = st.text_input("BD Proxy Password", type="password")

    st.divider()
    st.markdown("### Settings")
    alert_threshold = st.slider("Alert threshold", 3.0, 10.0, 6.5, 0.5)
    st.markdown(
        "**All 6 Bright Data tools used:**\n"
        "- MCP Server\n- SERP API\n- Web Unlocker\n"
        "- Scraping Browser\n- Web Scraper API\n- Proxies"
    )

# ── Inject credentials into environment ─────────────────────────
if anthropic_key:  os.environ["ANTHROPIC_API_KEY"] = anthropic_key
if bd_key:         os.environ["BRIGHT_DATA_API_KEY"] = bd_key
if bd_serp:        os.environ["BRIGHT_DATA_SERP_KEY"] = bd_serp
if bd_customer:    os.environ["BRIGHT_DATA_CUSTOMER_ID"] = bd_customer
if bd_proxy_pass:  os.environ["BRIGHT_DATA_PROXY_PASS"] = bd_proxy_pass
if alert_threshold:
    from config import CONFIG
    CONFIG.temporal.alert_threshold = alert_threshold

# ── Main panel ──────────────────────────────────────────────────
st.title("🛰 ARGUS Sentinel")
st.caption("Autonomous Real-time Global Understanding System · Track 1: UNLOCKED — AGENT")

# Query examples
col1, col2, col3, col4 = st.columns(4)
examples = [
    "What is OpenAI planning to launch?",
    "Monitor Stripe M&A signals",
    "Anthropic vs DeepMind hiring",
    "Notion competitor pricing changes",
]
for col, ex in zip([col1, col2, col3, col4], examples):
    if col.button(ex[:28] + "…", use_container_width=True):
        st.session_state["query_text"] = ex

query = st.text_input(
    "Intelligence query",
    value=st.session_state.get("query_text", ""),
    placeholder='e.g. "What is OpenAI planning to launch in the next 30 days?"',
    label_visibility="collapsed",
)

run_col, _ = st.columns([1, 5])
run_clicked = run_col.button("⚡ Run Intelligence", use_container_width=True)

# ── Validate before running ──────────────────────────────────────
if run_clicked:
    if not query.strip():
        st.warning("Enter a query first.")
        st.stop()
    if not anthropic_key:
        st.error("Add your Anthropic API key in the sidebar to continue.")
        st.stop()

    # ── Run pipeline ────────────────────────────────────────────
    progress = st.progress(0, "Parsing intent…")
    status = st.empty()

    try:
        # Import here so env vars are set first
        from orchestrator import ArgusOrchestrator

        progress.progress(15, "Deploying agents…")
        status.info("🔍 News Agent (SERP API) · Finance Agent (Scraper API) · "
                    "Site Watcher (Scraping Browser) · Signal Miner (Web Unlocker)")

        t0 = time.time()
        report = run_async(ArgusOrchestrator().run(query))
        elapsed = time.time() - t0

        progress.progress(90, "Synthesising with Claude…")
        time.sleep(0.3)
        progress.progress(100, "Done")
        status.empty()

        # ── Report display ──────────────────────────────────────
        if report.alert_triggered:
            st.error("⚠️ **ALERT** — Velocity threshold crossed. Immediate review recommended.")

        st.success(f"Report complete in **{elapsed:.1f}s** | "
                   f"Entities: {', '.join(report.entities)}")

        # Per-entity profiles
        for profile in report.profiles:
            st.divider()
            vcol1, vcol2, vcol3, vcol4, vcol5 = st.columns(5)

            vcol1.metric(
                "Composite Velocity",
                f"{score_colour(profile.velocity_score)} {profile.velocity_score:.1f}/10",
            )
            for col, (src, vel) in zip(
                [vcol2, vcol3, vcol4, vcol5],
                list(profile.source_velocities.items())[:4],
            ):
                col.metric(src.capitalize(), f"{score_colour(vel)} {vel:.1f}")

            st.markdown(f"**Trajectory slope:** `{profile.trajectory_slope:+.3f}` "
                        f"{'↑ accelerating' if profile.trajectory_slope > 0.05 else '↓ decelerating' if profile.trajectory_slope < -0.05 else '→ stable'} | "
                        f"**Anomaly detected:** {'🔴 YES' if profile.anomaly_detected else '⚪ no'}")

            # Sparkline via st.line_chart
            if len(profile.trajectory) >= 2:
                import pandas as pd
                st.line_chart(
                    pd.DataFrame({"Velocity": profile.trajectory}),
                    height=80, use_container_width=True,
                )

            # Prediction
            conf_pct = int(profile.prediction_confidence * 100)
            st.info(f"**🔮 Prediction ({conf_pct}% confidence):** {profile.prediction}")
            st.progress(conf_pct / 100)

            # Top signals
            if profile.top_signals:
                st.markdown("**📡 Top signals**")
                for s in profile.top_signals[:6]:
                    st.markdown(
                        f"{badge(s['source'])} **[{s['source'].upper()}]** "
                        f"{s['content'][:140]}  `w={s['weight']}`"
                    )

        # Executive summary
        if report.executive_summary:
            st.divider()
            st.markdown("### 📋 Executive Summary")
            st.markdown(report.executive_summary)

            if report.key_findings:
                st.markdown("**Key findings**")
                for f in report.key_findings:
                    st.markdown(f"→ {f}")

            if report.recommended_actions:
                st.markdown("**Recommended actions**")
                for a in report.recommended_actions:
                    st.markdown(f"✓ {a}")

        # Download JSON
        st.download_button(
            "⬇ Download report (JSON)",
            data=json.dumps(report.to_dict(), indent=2, default=str),
            file_name=f"argus_{report.entities[0].lower().replace(' ','_')}_{int(report.timestamp)}.json",
            mime="application/json",
        )

        # Store in history
        if "history" not in st.session_state:
            st.session_state["history"] = []
        st.session_state["history"].insert(0, report.to_dict())

    except Exception as e:
        progress.empty()
        status.empty()
        st.error(f"**Error:** {e}")
        if "401" in str(e) or "authentication" in str(e).lower():
            st.info("💡 Check your Anthropic API key in the sidebar.")
        elif "bright" in str(e).lower() or "proxy" in str(e).lower():
            st.info("💡 Check your Bright Data credentials in the sidebar.")
        else:
            with st.expander("Full traceback"):
                import traceback
                st.code(traceback.format_exc())

# ── History ──────────────────────────────────────────────────────
if st.session_state.get("history"):
    st.divider()
    st.markdown("### History")
    for r in st.session_state["history"][:5]:
        p = r["profiles"][0] if r.get("profiles") else {}
        score = p.get("velocity_score", 0)
        with st.expander(
            f"{score_colour(score)} **{r['query'][:60]}** — score {score:.1f}  "
            f"{'🔔 ALERT' if r.get('alert_triggered') else ''}"
        ):
            st.json(r, expanded=False)
