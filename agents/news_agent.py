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

    FREE_RSS_FEEDS = [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://feeds.arstechnica.com/arstechnica/index",
        "https://www.wired.com/feed/rss",
        "https://feeds.feedburner.com/venturebeat/SZYF",
    ]

    async def _collect_free(self, entity: str, query: str) -> list[ArgusSignal]:
        """Collect from free public sources: Google News, HN, Reddit, RSS feeds."""
        import asyncio
        timeout = aiohttp.ClientTimeout(total=15)
        headers = {"User-Agent": "Mozilla/5.0 (compatible; argus-sentinel/1.0)"}

        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            tasks = [
                # Google News RSS — real-time, all sources, no key needed
                self._free_google_news(session, entity, query),
                self._free_google_news(session, entity, ""),   # entity-only search
                self._free_hn(session, entity, query),
                self._free_reddit(session, entity, query),
            ] + [self._free_rss(session, feed, entity) for feed in self.FREE_RSS_FEEDS]

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

    async def _free_hn(self, session: aiohttp.ClientSession, entity: str, query: str) -> list[ArgusSignal]:
        q = urllib.parse.quote(f"{entity} {query}")
        url = (
            f"https://hn.algolia.com/api/v1/search"
            f"?query={q}&tags=story&hitsPerPage=30"
            f"&numericFilters=created_at_i>{int(time.time() - 30 * 86400)}"
        )
        async with session.get(url) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

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

    async def _free_rss(self, session: aiohttp.ClientSession, feed_url: str, entity: str) -> list[ArgusSignal]:
        entity_lower = entity.lower()
        try:
            async with session.get(feed_url) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text()
        except Exception:
            return []

        signals = []
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        # Handle both RSS <item> and Atom <entry>
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        for item in items[:30]:
            title_el = item.find("title") or item.find("atom:title", ns)
            link_el = item.find("link") or item.find("atom:link", ns)
            desc_el = item.find("description") or item.find("atom:summary", ns)

            title = (title_el.text or "").strip() if title_el is not None else ""
            link = (link_el.text or link_el.get("href", "")).strip() if link_el is not None else ""
            desc = (desc_el.text or "").strip() if desc_el is not None else ""

            if not title or not link:
                continue
            if entity_lower not in title.lower() and entity_lower not in desc.lower():
                continue

            domain = self._extract_domain(link)
            weight = self._compute_weight(domain, (title + " " + desc).lower())
            signals.append(ArgusSignal(
                source="news",
                signal_type="mention",
                entity=entity,
                content=f"{title}",
                url=link,
                timestamp=time.time(),
                weight=weight,
                metadata={"platform": "rss", "feed": feed_url},
            ))
        return signals
