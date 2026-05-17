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
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Optional

import aiohttp

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
            logger.info("NewsAgent: no Bright Data key — using free public sources")
            return await self._collect_free(entity, query)
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

    # ------------------------------------------------------------------ #
    #  Free fallback (no Bright Data key required)                         #
    # ------------------------------------------------------------------ #

    async def _collect_free(self, entity: str, query: str) -> list[ArgusSignal]:
        """Collect from free public sources that work from datacenter IPs."""
        import asyncio
        timeout = aiohttp.ClientTimeout(total=10)
        headers = {"User-Agent": "Mozilla/5.0 (compatible; argus-sentinel/1.0)"}

        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            tasks = [
                self._free_guardian(session, entity, query),  # no key needed, works everywhere
                self._free_hn(session, entity),
                self._free_newsapi(session, entity, query),   # optional: add NEWSAPI_KEY in Render
            ]

            batches = await asyncio.gather(*tasks, return_exceptions=True)

        signals: list[ArgusSignal] = []
        for batch in batches:
            if isinstance(batch, Exception):
                logger.debug("Free source failed: %s", batch)
                continue
            signals.extend(batch)

        logger.info("NewsAgent (free): %d signals for '%s'", len(signals), entity)
        return signals

    async def _free_google_news(self, session: aiohttp.ClientSession, entity: str, query: str) -> list[ArgusSignal]:
        """Google News RSS — real-time results from all major news sources, completely free."""
        search_term = f"{entity} {query}".strip()
        q = urllib.parse.quote(search_term)
        url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"

        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text()
        except Exception as e:
            logger.debug("Google News RSS failed: %s", e)
            return []

        signals = []
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []

        for item in root.findall(".//item"):
            title_el = item.find("title")
            link_el = item.find("link")
            pub_el = item.find("pubDate")
            source_el = item.find("source")

            title = (title_el.text or "").strip() if title_el is not None else ""
            link = (link_el.text or "").strip() if link_el is not None else ""
            pub_date = (pub_el.text or "").strip() if pub_el is not None else ""
            source_name = (source_el.text or "").strip() if source_el is not None else ""

            if not title or not link:
                continue

            domain = self._extract_domain(link)
            weight = self._compute_weight(domain, title.lower())
            ts = self._parse_date(pub_date)

            signals.append(ArgusSignal(
                source="news",
                signal_type="mention",
                entity=entity,
                content=f"{title}" + (f" — {source_name}" if source_name else ""),
                url=link,
                timestamp=ts,
                weight=weight,
                metadata={"platform": "google_news", "source": source_name, "pub_date": pub_date},
            ))

        logger.info("Google News: %d articles for '%s'", len(signals), search_term)
        return signals

    async def _free_guardian(self, session: aiohttp.ClientSession, entity: str, query: str) -> list[ArgusSignal]:
        """The Guardian Open Platform — free 'test' key works from any IP, no signup needed."""
        import os
        api_key = os.getenv("GUARDIAN_API_KEY", "test")  # 'test' key is public and rate-limited but works
        q = urllib.parse.quote(f"{entity} {query}".strip())
        url = (
            f"https://content.guardianapis.com/search"
            f"?q={q}&api-key={api_key}&show-fields=headline,trailText"
            f"&order-by=newest&page-size=30"
        )
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.debug("Guardian returned %d", resp.status)
                    return []
                data = await resp.json()
        except Exception as e:
            logger.debug("Guardian failed: %s", e)
            return []

        signals = []
        results = data.get("response", {}).get("results", [])
        for item in results:
            fields = item.get("fields", {})
            title = fields.get("headline") or item.get("webTitle", "")
            url_ = item.get("webUrl", "")
            description = fields.get("trailText", "")
            published = item.get("webPublicationDate", "")

            if not title or not url_:
                continue

            weight = self._compute_weight("theguardian.com", (title + " " + description).lower())
            signals.append(ArgusSignal(
                source="news",
                signal_type="mention",
                entity=entity,
                content=f"{title}" + (f" — {description[:80]}" if description else ""),
                url=url_,
                timestamp=self._parse_date(published),
                weight=weight,
                metadata={"platform": "guardian"},
            ))
        logger.info("Guardian: %d articles for '%s'", len(signals), entity)
        return signals

    async def _free_hn(self, session: aiohttp.ClientSession, entity: str) -> list[ArgusSignal]:
        """Hacker News Algolia search — open API, works from any IP."""
        q = urllib.parse.quote(entity)
        url = f"https://hn.algolia.com/api/v1/search?query={q}&tags=story&hitsPerPage=30"
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except Exception as e:
            logger.debug("HN failed: %s", e)
            return []

        signals = []
        for hit in data.get("hits", []):
            title = hit.get("title", "")
            if not title:
                continue
            points = hit.get("points", 0) or 0
            comments = hit.get("num_comments", 0) or 0
            hn_url = f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
            weight = round(min(0.45 + (points + comments * 4) / 1500, 0.95), 2)
            signals.append(ArgusSignal(
                source="news",
                signal_type="mention",
                entity=entity,
                content=f"HN: {title} (↑{points} 💬{comments})",
                url=hn_url,
                timestamp=hit.get("created_at_i", time.time()),
                weight=weight,
                metadata={"platform": "hackernews", "points": points},
            ))
        logger.info("HN: %d results for '%s'", len(signals), entity)
        return signals

    async def _free_newsapi(self, session: aiohttp.ClientSession, entity: str, query: str) -> list[ArgusSignal]:
        """NewsAPI.org — free 100 req/day, works from datacenter IPs. Key: newsapi.org/register"""
        api_key = self.cfg.newsapi_key if hasattr(self.cfg, "newsapi_key") else ""
        # Fallback: read directly from env
        if not api_key:
            import os
            api_key = os.getenv("NEWSAPI_KEY", "")
        if not api_key:
            return []

        q = urllib.parse.quote(f"{entity} {query}".strip())
        url = (
            f"https://newsapi.org/v2/everything"
            f"?q={q}&sortBy=publishedAt&pageSize=30&language=en"
        )
        try:
            async with session.get(url, headers={"X-Api-Key": api_key}) as resp:
                if resp.status != 200:
                    logger.debug("NewsAPI returned %d", resp.status)
                    return []
                data = await resp.json()
        except Exception as e:
            logger.debug("NewsAPI failed: %s", e)
            return []

        signals = []
        for article in data.get("articles", []):
            title = article.get("title") or ""
            url_ = article.get("url") or ""
            source_name = (article.get("source") or {}).get("name", "")
            description = article.get("description") or ""
            published = article.get("publishedAt") or ""

            if not title or not url_ or title == "[Removed]":
                continue

            domain = self._extract_domain(url_)
            weight = self._compute_weight(domain, (title + " " + description).lower())
            signals.append(ArgusSignal(
                source="news",
                signal_type="mention",
                entity=entity,
                content=f"{title}" + (f" — {source_name}" if source_name else ""),
                url=url_,
                timestamp=self._parse_date(published),
                weight=weight,
                metadata={"platform": "newsapi", "source": source_name},
            ))
        logger.info("NewsAPI: %d articles for '%s'", len(signals), entity)
        return signals

    async def _free_reddit(self, session: aiohttp.ClientSession, entity: str, query: str) -> list[ArgusSignal]:
        q = urllib.parse.quote(f"{entity} {query}")
        url = f"https://www.reddit.com/search.json?q={q}&sort=new&t=month&limit=25"
        async with session.get(url) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

        signals = []
        for post in data.get("data", {}).get("children", []):
            p = post.get("data", {})
            title = p.get("title", "")
            if not title:
                continue
            score = p.get("score", 0) or 0
            comments = p.get("num_comments", 0) or 0
            sub = p.get("subreddit", "")
            reddit_url = f"https://reddit.com{p.get('permalink', '')}"
            weight = round(min(0.4 + (score + comments * 3) / 1000, 0.9), 2)
            signals.append(ArgusSignal(
                source="news",
                signal_type="mention",
                entity=entity,
                content=f"Reddit r/{sub}: {title} (↑{score} 💬{comments})",
                url=reddit_url,
                timestamp=p.get("created_utc", time.time()),
                weight=weight,
                metadata={"platform": "reddit", "subreddit": sub},
            ))
        return signals

