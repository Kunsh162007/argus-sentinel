"""
ARGUS Sentinel — Site Watcher Agent
Uses Bright Data Scraping Browser (Playwright over CDP) to:
  - Monitor competitor websites for content changes
  - Detect new pages, navigation restructuring, pricing changes
  - Track documentation additions (often precede product launches)
  - Screenshot diffs for visual change detection

Why Scraping Browser?
  - Modern SaaS sites are React/Next.js SPAs — raw HTTP gets shell HTML
  - Bright Data's browser is already logged in with rotating sessions
  - CAPTCHA solving and fingerprint spoofing built in
  - We get real rendered DOM, not SSR stub
"""

import asyncio
import difflib
import hashlib
import logging
import re
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# Playwright is optional — degrades gracefully on Streamlit Cloud
PLAYWRIGHT_AVAILABLE = False
try:
    import playwright  # noqa: F401
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass

from agents.base_agent import BaseAgent, ArgusSignal
from bright_data_client import BrightDataClient
from config import CONFIG

logger = logging.getLogger("argus.agent.site")

# Pages worth monitoring (appended to base domain)
WATCH_PATHS = [
    "/",
    "/pricing",
    "/docs",
    "/blog",
    "/changelog",
    "/release-notes",
    "/products",
    "/research",
    "/api",
    "/careers",
]

# Nav link patterns that suggest new product sections
PRODUCT_INDICATORS = [
    r"\bnew\b", r"\bbeta\b", r"\bpreview\b", r"\blaunch\b",
    r"api\s*v\d", r"models?", r"enterprise", r"agent", r"pro\b",
]


class SiteWatcherAgent(BaseAgent):
    """
    Monitors competitor and target websites for structural + content changes.
    
    Core technique: Content-hash comparison across snapshots.
    When a page's text hash changes by more than diff_threshold (default 8%),
    we extract the changed sections and emit them as signals.
    
    Navigation changes (new menu items, removed pages) are weighted highest —
    they reliably precede product announcements by 1–7 days.
    """

    name = "site"
    source = "site"

    def __init__(self, client: BrightDataClient):
        super().__init__(client)
        self.cfg = CONFIG.agent
        self._page_hashes: dict[str, str] = {}      # url → content hash
        self._nav_cache: dict[str, set[str]] = {}    # domain → nav links

    async def collect(self, entity: str, query: str) -> list[ArgusSignal]:
        """
        Discovers the entity's main domain, then monitors key pages.
        """
        domain = await self._resolve_domain(entity)
        if not domain:
            logger.warning("SiteWatcher: could not resolve domain for '%s'", entity)
            return []

        # Watch all key paths in parallel (Scraping Browser handles concurrency)
        watch_urls = [urljoin(domain, path) for path in WATCH_PATHS]

        tasks = [self._watch_url(url, entity) for url in watch_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        signals: list[ArgusSignal] = []
        for batch in results:
            if isinstance(batch, Exception):
                logger.debug("SiteWatcher URL failed: %s", batch)
                continue
            signals.extend(batch)

        logger.info("SiteWatcher: %d signals for '%s' (%s)", len(signals), entity, domain)
        return signals

    async def _watch_url(self, url: str, entity: str) -> list[ArgusSignal]:
        """Fetch a page via Scraping Browser, diff against last snapshot."""
        if not PLAYWRIGHT_AVAILABLE:
            logger.debug("Playwright not available — skipping Scraping Browser for %s", url)
            return []
        try:
            page_data = await self.client.scraping_browser_fetch(
                url=url,
                scroll=True,
                screenshot=self.cfg.site_screenshot,
            )
        except Exception as e:
            logger.debug("Scraping Browser failed for %s: %s", url, e)
            return []

        html = page_data.get("html", "")
        if not html:
            return []

        signals = []
        soup = BeautifulSoup(html, "lxml")

        # 1. Content hash diff
        text_content = soup.get_text(separator=" ", strip=True)
        content_hash = hashlib.md5(text_content.encode()).hexdigest()

        if url in self._page_hashes:
            old_hash = self._page_hashes[url]
            if old_hash != content_hash:
                # Compute similarity ratio to measure magnitude of change
                old_text = getattr(self, "_page_text_cache", {}).get(url, "")
                ratio = difflib.SequenceMatcher(None, old_text, text_content).ratio()
                change_pct = 1.0 - ratio

                if change_pct >= self.cfg.site_diff_threshold:
                    weight = min(0.4 + change_pct * 2, 0.95)
                    signals.append(ArgusSignal(
                        source="site",
                        signal_type="change",
                        entity=entity,
                        content=f"Page content changed {change_pct:.0%} at {url}",
                        url=url,
                        timestamp=time.time(),
                        weight=round(weight, 2),
                        metadata={
                            "change_pct": round(change_pct, 3),
                            "has_screenshot": bool(page_data.get("screenshot_b64")),
                        },
                    ))

        self._page_hashes[url] = content_hash
        if not hasattr(self, "_page_text_cache"):
            self._page_text_cache = {}
        self._page_text_cache[url] = text_content

        # 2. Navigation structure change
        nav_signals = self._check_nav_changes(soup, url, entity)
        signals.extend(nav_signals)

        # 3. Changelog / blog new entry detection
        if any(p in url for p in ["/blog", "/changelog", "/release"]):
            entry_signals = self._detect_new_entries(soup, url, entity)
            signals.extend(entry_signals)

        # 4. Pricing page — detect tier/price changes
        if "/pricing" in url:
            pricing_signals = self._detect_pricing_changes(soup, url, entity)
            signals.extend(pricing_signals)

        return signals

    def _check_nav_changes(self, soup: BeautifulSoup, url: str, entity: str) -> list[ArgusSignal]:
        """Detect new navigation links — highest-value pre-launch signal."""
        domain = urlparse(url).netloc
        nav_links: set[str] = set()

        for tag in soup.find_all(["nav", "header"]):
            for a in tag.find_all("a", href=True):
                text = a.get_text(strip=True).lower()
                if text and len(text) > 1:
                    nav_links.add(text)

        signals = []
        if domain in self._nav_cache:
            old_nav = self._nav_cache[domain]
            new_items = nav_links - old_nav
            removed_items = old_nav - nav_links

            for item in new_items:
                # Check if new nav item matches product-launch patterns
                is_product_signal = any(
                    re.search(p, item) for p in PRODUCT_INDICATORS
                )
                weight = 0.85 if is_product_signal else 0.65
                signals.append(ArgusSignal(
                    source="site",
                    signal_type="change",
                    entity=entity,
                    content=f"New navigation item added: '{item}' on {domain}",
                    url=url,
                    timestamp=time.time(),
                    weight=weight,
                    metadata={"nav_item": item, "signal_class": "nav_addition"},
                ))

            for item in removed_items:
                signals.append(ArgusSignal(
                    source="site",
                    signal_type="change",
                    entity=entity,
                    content=f"Navigation item removed: '{item}' from {domain}",
                    url=url,
                    timestamp=time.time(),
                    weight=0.7,
                    metadata={"nav_item": item, "signal_class": "nav_removal"},
                ))

        self._nav_cache[domain] = nav_links
        return signals

    def _detect_new_entries(
        self, soup: BeautifulSoup, url: str, entity: str
    ) -> list[ArgusSignal]:
        """Detect new blog posts or changelog entries."""
        signals = []
        entries = soup.find_all(["article", "li"], class_=re.compile(r"post|entry|item|changelog"))
        for entry in entries[:5]:  # Top 5 most recent
            title_tag = entry.find(["h1", "h2", "h3", "h4"])
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            entry_hash = hashlib.md5(title.encode()).hexdigest()
            if not hasattr(self, "_entry_cache"):
                self._entry_cache = set()
            if entry_hash not in self._entry_cache:
                self._entry_cache.add(entry_hash)
                signals.append(ArgusSignal(
                    source="site",
                    signal_type="change",
                    entity=entity,
                    content=f"New entry detected: '{title}'",
                    url=url,
                    timestamp=time.time(),
                    weight=0.75,
                    metadata={"entry_title": title},
                ))
        return signals

    def _detect_pricing_changes(
        self, soup: BeautifulSoup, url: str, entity: str
    ) -> list[ArgusSignal]:
        """Look for price text changes on pricing pages."""
        signals = []
        price_texts = []
        for el in soup.find_all(string=re.compile(r"\$\d+|per\s+month|per\s+seat|free\s+tier")):
            price_texts.append(el.strip()[:80])

        if not price_texts:
            return signals

        price_hash = hashlib.md5(str(sorted(price_texts)).encode()).hexdigest()
        cache_key = f"pricing:{url}"
        if not hasattr(self, "_pricing_cache"):
            self._pricing_cache = {}

        if cache_key in self._pricing_cache and self._pricing_cache[cache_key] != price_hash:
            signals.append(ArgusSignal(
                source="site",
                signal_type="change",
                entity=entity,
                content=f"Pricing page changed at {url}",
                url=url,
                timestamp=time.time(),
                weight=0.8,
                metadata={"price_samples": price_texts[:5], "signal_class": "pricing"},
            ))

        self._pricing_cache[cache_key] = price_hash
        return signals

    async def _resolve_domain(self, entity: str) -> Optional[str]:
        """
        Try to resolve the main website for an entity.
        First checks common patterns, falls back to SERP API search.
        """
        # Common domain guesses
        clean = entity.lower().replace(" ", "").replace(".", "")
        guesses = [
            f"https://www.{clean}.com",
            f"https://{clean}.ai",
            f"https://{clean}.io",
        ]
        for url in guesses:
            try:
                result = await self.client.scraping_browser_fetch(url)
                if result.get("html"):
                    return url
            except Exception:
                continue

        # Fallback: SERP search
        results = await self.client.serp_search(
            query=f"{entity} official website",
            engine="google",
            num_results=3,
        )
        if isinstance(results, dict):
            items = results.get("organic_results", [])
        else:
            items = results if isinstance(results, list) else []

        for item in items:
            url = item.get("link", "")
            if url.startswith("http"):
                return url

        return None
