"""
ARGUS Sentinel — News Agent
Uses Bright Data SERP API to collect real-time news signals
across Google, Bing, and Yandex simultaneously.

Tracks:
  - Mention frequency (raw signal volume)
  - Sentiment direction (positive/negative/neutral)
  - Source authority (tier-1 press vs blogs)
  - Geographic spread (US/EU/APAC coverage delta)
"""

import logging
import time
from typing import Optional

from agents.base_agent import BaseAgent, ArgusSignal
from bright_data_client import BrightDataClient
from config import CONFIG

logger = logging.getLogger("argus.agent.news")

# Source authority tiers for weighting
TIER_1_SOURCES = {
    "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "nytimes.com",
    "techcrunch.com", "theverge.com", "wired.com", "arstechnica.com",
    "forbes.com", "cnbc.com", "bbc.com", "axios.com", "apnews.com",
}

TIER_2_SOURCES = {
    "venturebeat.com", "zdnet.com", "engadget.com", "9to5mac.com",
    "the-information.com", "semafor.com", "platformer.news",
}

NEGATIVE_KEYWORDS = {
    "lawsuit", "fine", "investigation", "layoff", "layoffs", "fired",
    "resign", "loss", "decline", "drop", "fail", "breach", "hack",
    "scandal", "controversy", "ban", "blocked", "rejected",
}

POSITIVE_KEYWORDS = {
    "launch", "funding", "raises", "partnership", "breakthrough",
    "growth", "record", "milestone", "acquires", "expands", "wins",
    "profit", "revenue", "new", "announces", "release", "ships",
}


class NewsAgent(BaseAgent):
    """
    Collects and processes news signals via Bright Data SERP API.
    
    SERP API is used because:
      - Direct Google scraping is blocked within seconds
      - Bright Data maintains rotating IPs + CAPTCHA solving
      - We get structured JSON (not raw HTML to parse)
      - Multi-engine fan-out runs in parallel
    """

    name = "news"
    source = "news"

    def __init__(self, client: BrightDataClient):
        super().__init__(client)
        self.cfg = CONFIG.agent

    async def collect(self, entity: str, query: str) -> list[ArgusSignal]:
        """
        Collects news signals for an entity across multiple search engines
        and time ranges to detect velocity.
        """
        if not self.client.cfg.api_key:
            logger.info("NewsAgent: no Bright Data API key — skipping")
            return []
        # Primary search: entity + query
        primary_results = await self.client.serp_news_multi_engine(
            query=f"{entity} {query}",
            lookback_days=self.cfg.news_lookback_days,
        )

        # Secondary search: entity alone (broader context)
        secondary_results = await self.client.serp_news_multi_engine(
            query=entity,
            lookback_days=1,  # Last 24h for recency pulse
        )

        all_results = primary_results + secondary_results
        signals = [self._result_to_signal(r, entity) for r in all_results]
        signals = [s for s in signals if s is not None]

        logger.info("NewsAgent: %d signals for '%s'", len(signals), entity)
        return signals

    def _result_to_signal(self, result: dict, entity: str) -> Optional[ArgusSignal]:
        url = result.get("url", "")
        title = result.get("title", "")
        snippet = result.get("snippet", "")
        date_str = result.get("date", "")
        source_domain = self._extract_domain(url)

        if not title or not url:
            return None

        content_lower = (title + " " + snippet).lower()
        weight = self._compute_weight(source_domain, content_lower)
        sentiment = self._detect_sentiment(content_lower)

        return ArgusSignal(
            source="news",
            signal_type="mention",
            entity=entity,
            content=f"{title} — {snippet[:120]}",
            url=url,
            timestamp=self._parse_date(date_str),
            weight=weight,
            metadata={
                "source_domain": source_domain,
                "sentiment": sentiment,
                "date_str": date_str,
            },
        )

    def _compute_weight(self, domain: str, content: str) -> float:
        base = 0.4
        if any(d in domain for d in TIER_1_SOURCES):
            base = 0.9
        elif any(d in domain for d in TIER_2_SOURCES):
            base = 0.7

        # Boost for high-signal keywords
        high_signal = {"launch", "funding", "acquires", "announces", "new model"}
        if any(k in content for k in high_signal):
            base = min(base + 0.1, 1.0)
        return round(base, 2)

    def _detect_sentiment(self, content: str) -> str:
        neg_hits = sum(1 for k in NEGATIVE_KEYWORDS if k in content)
        pos_hits = sum(1 for k in POSITIVE_KEYWORDS if k in content)
        if pos_hits > neg_hits:
            return "positive"
        if neg_hits > pos_hits:
            return "negative"
        return "neutral"

    @staticmethod
    def _extract_domain(url: str) -> str:
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc.replace("www.", "")
        except Exception:
            return ""

    @staticmethod
    def _parse_date(date_str: str) -> float:
        """Best-effort parse of various date formats → Unix timestamp."""
        import dateutil.parser
        if not date_str:
            return time.time()
        try:
            return dateutil.parser.parse(date_str, fuzzy=True).timestamp()
        except Exception:
            return time.time()
