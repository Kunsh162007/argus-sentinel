"""
ARGUS Sentinel — Configuration
All settings, model names, and Bright Data endpoints in one place.
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class BrightDataConfig:
    api_key: str = field(default_factory=lambda: os.getenv("BRIGHT_DATA_API_KEY", ""))
    serp_key: str = field(default_factory=lambda: os.getenv("BRIGHT_DATA_SERP_KEY", ""))
    mcp_url: str = "https://mcp.brightdata.com/sse"

    # Endpoint base URLs
    serp_base: str = "https://api.brightdata.com/serp"
    scraper_api_base: str = "https://api.brightdata.com/datasets/v3"
    web_unlocker_base: str = "https://api.brightdata.com/request"
    scraping_browser_ws: str = "wss://brd.superproxy.io:9222"

    # Proxy config (residential for social, datacenter for news)
    residential_proxy: str = field(
        default_factory=lambda: (
            f"http://brd-customer-{os.getenv('BRIGHT_DATA_CUSTOMER_ID','')}"
            f"-zone-residential:{os.getenv('BRIGHT_DATA_PROXY_PASS','')}@brd.superproxy.io:22225"
        )
    )
    datacenter_proxy: str = field(
        default_factory=lambda: (
            f"http://brd-customer-{os.getenv('BRIGHT_DATA_CUSTOMER_ID','')}"
            f"-zone-datacenter:{os.getenv('BRIGHT_DATA_PROXY_PASS','')}@brd.superproxy.io:22225"
        )
    )


@dataclass
class ModelConfig:
    orchestrator_model: str = "claude-sonnet-4-20250514"
    analysis_model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    temperature: float = 0.1  # Low temp for factual analysis


@dataclass
class TemporalConfig:
    # How many historical snapshots to compare for velocity
    snapshot_window: int = 5
    # Minimum velocity score to trigger an alert (0-10)
    alert_threshold: float = 6.5
    # How often to re-poll each source (seconds)
    poll_interval_news: int = 300       # 5 min
    poll_interval_finance: int = 1800   # 30 min
    poll_interval_site: int = 3600      # 1 hour
    poll_interval_social: int = 600     # 10 min
    # Confidence threshold for predictions
    prediction_confidence_min: float = 0.55


@dataclass
class AgentConfig:
    # News Agent
    news_max_results: int = 20
    news_engines: list = field(default_factory=lambda: ["google", "bing", "yandex"])
    news_lookback_days: int = 7

    # Finance Agent — Bright Data dataset IDs
    linkedin_dataset_id: str = "gd_l1viktl72bvl7bjuj"    # LinkedIn company
    crunchbase_dataset_id: str = "gd_l1vikfnt16wg0b9pe"  # Crunchbase funding
    sec_edgar_dataset_id: str = "gd_lxfe4bnt1ikf3bm0x6" # SEC filings

    # Site Watcher
    site_screenshot: bool = True
    site_diff_threshold: float = 0.08  # 8% content change triggers signal

    # Signal Miner — social platforms (via Web Unlocker)
    social_sources: list = field(default_factory=lambda: [
        "https://www.reddit.com",
        "https://news.ycombinator.com",
        "https://x.com",        # Unlocker handles auth bypass
    ])


@dataclass
class DashboardConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    ws_ping_interval: int = 20
    max_history_entries: int = 500


@dataclass
class ArgusConfig:
    bright_data: BrightDataConfig = field(default_factory=BrightDataConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    temporal: TemporalConfig = field(default_factory=TemporalConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)

    # Output
    output_dir: str = "./reports"
    log_level: str = "INFO"


# Singleton
CONFIG = ArgusConfig()
