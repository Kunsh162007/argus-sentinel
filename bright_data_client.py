"""
ARGUS Sentinel — Bright Data Client
Unified interface for all Bright Data products:
  - SERP API
  - Web Scraper API (datasets)
  - Web Unlocker
  - Scraping Browser (Playwright over CDP)
  - Proxies
"""

import asyncio
import json
import logging
import time
from typing import Any, Optional
from urllib.parse import quote_plus

import aiohttp
import async_timeout
from playwright.async_api import async_playwright, Browser, Page

from config import CONFIG

logger = logging.getLogger("argus.bright_data")


class BrightDataClient:
    """
    Single client that wraps all Bright Data products with:
      - Automatic retry on rate-limit / block (exponential backoff)
      - Geo-routing via proxy pool
      - Unified response normalisation
    """

    def __init__(self):
        self.cfg = CONFIG.bright_data
        self._session: Optional[aiohttp.ClientSession] = None
        self._browser: Optional[Browser] = None

    # ------------------------------------------------------------------ #
    #  Session management                                                  #
    # ------------------------------------------------------------------ #

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self.cfg.api_key}"},
            timeout=aiohttp.ClientTimeout(total=60),
        )
        return self

    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()
        if self._browser:
            await self._browser.close()

    # ------------------------------------------------------------------ #
    #  SERP API — real-time search engine results                         #
    # ------------------------------------------------------------------ #

    async def serp_search(
        self,
        query: str,
        engine: str = "google",
        num_results: int = 20,
        country: str = "us",
        time_range: Optional[str] = "w",  # d/w/m/y
    ) -> list[dict]:
        """
        Returns structured SERP results from Google/Bing/Yandex.
        Uses Bright Data's SERP API — handles JS rendering, CAPTCHAs, IP bans.
        """
        params = {
            "engine": engine,
            "q": query,
            "num": num_results,
            "gl": country,
            "tbm": "nws",  # news tab
            "tbs": f"qdr:{time_range}" if time_range else None,
            "output": "json",
        }
        params = {k: v for k, v in params.items() if v is not None}

        url = f"{self.cfg.serp_base}/search"
        return await self._request_with_retry(url, params=params, tool="SERP API")

    async def serp_news_multi_engine(
        self, query: str, lookback_days: int = 7
    ) -> list[dict]:
        """Fan out to Google + Bing + Yandex concurrently, deduplicate by URL."""
        time_map = {1: "d", 7: "w", 30: "m", 365: "y"}
        tbs = time_map.get(lookback_days, "w")

        tasks = [
            self.serp_search(query, engine=engine, time_range=tbs)
            for engine in CONFIG.agent.news_engines
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten and deduplicate by URL
        seen_urls: set[str] = set()
        merged: list[dict] = []
        for batch in results:
            if isinstance(batch, Exception):
                logger.warning("SERP engine failed: %s", batch)
                continue
            if isinstance(batch, dict):
                items = batch.get("organic_results", batch.get("news_results", []))
            else:
                items = batch if isinstance(batch, list) else []
            for item in items:
                url = item.get("link", item.get("url", ""))
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    merged.append({
                        "title": item.get("title", ""),
                        "url": url,
                        "snippet": item.get("snippet", ""),
                        "date": item.get("date", ""),
                        "source": item.get("source", ""),
                    })
        logger.info("SERP: collected %d deduplicated results for '%s'", len(merged), query)
        return merged

    # ------------------------------------------------------------------ #
    #  Web Scraper API — 660+ pre-built structured scrapers               #
    # ------------------------------------------------------------------ #

    async def scraper_api_trigger(
        self,
        dataset_id: str,
        inputs: list[dict],
        notify_url: Optional[str] = None,
    ) -> str:
        """
        Trigger an async Bright Data dataset collection job.
        Returns the snapshot_id to poll for results.
        """
        url = f"{self.cfg.scraper_api_base}/trigger"
        params = {"dataset_id": dataset_id, "format": "json"}
        if notify_url:
            params["notify"] = notify_url

        result = await self._request_with_retry(
            url, method="POST", json=inputs, params=params, tool="Scraper API"
        )
        snapshot_id = result.get("snapshot_id") if isinstance(result, dict) else None
        logger.info("Scraper API: triggered dataset %s → snapshot %s", dataset_id, snapshot_id)
        return snapshot_id

    async def scraper_api_get_snapshot(
        self, snapshot_id: str, poll_interval: int = 10, max_wait: int = 300
    ) -> list[dict]:
        """Poll until snapshot is ready, then return structured records."""
        url = f"{self.cfg.scraper_api_base}/snapshot/{snapshot_id}"
        deadline = time.monotonic() + max_wait

        while time.monotonic() < deadline:
            result = await self._request_with_retry(
                url, params={"format": "json"}, tool="Scraper API"
            )
            if isinstance(result, list):
                logger.info("Scraper API: snapshot %s ready, %d records", snapshot_id, len(result))
                return result
            status = result.get("status") if isinstance(result, dict) else "unknown"
            if status in ("failed", "error"):
                raise RuntimeError(f"Scraper API snapshot failed: {result}")
            logger.debug("Scraper API: snapshot %s status=%s, waiting…", snapshot_id, status)
            await asyncio.sleep(poll_interval)

        raise TimeoutError(f"Scraper API snapshot {snapshot_id} timed out after {max_wait}s")

    async def scraper_api_fetch(self, dataset_id: str, inputs: list[dict]) -> list[dict]:
        """Convenience: trigger + poll in one call."""
        snap_id = await self.scraper_api_trigger(dataset_id, inputs)
        return await self.scraper_api_get_snapshot(snap_id)

    # ------------------------------------------------------------------ #
    #  Web Unlocker — bypass bot detection on any public URL              #
    # ------------------------------------------------------------------ #

    async def unlock(
        self,
        url: str,
        country: Optional[str] = None,
        render_js: bool = False,
        headers: Optional[dict] = None,
    ) -> str:
        """
        Fetches a URL through Web Unlocker.
        Handles: CAPTCHAs, fingerprinting, Cloudflare, geo-blocks, JS rendering.
        Returns raw HTML.
        """
        payload = {
            "zone": "web_unlocker1",
            "url": url,
            "format": "raw",
        }
        if render_js:
            payload["render"] = "html"
        if country:
            payload["country"] = country
        if headers:
            payload["headers"] = headers

        result = await self._request_with_retry(
            self.cfg.web_unlocker_base,
            method="POST",
            json=payload,
            tool="Web Unlocker",
        )
        # Web Unlocker returns the page HTML directly as a string
        if isinstance(result, str):
            return result
        return result.get("html", "") if isinstance(result, dict) else ""

    # ------------------------------------------------------------------ #
    #  Scraping Browser — full Playwright automation via CDP              #
    # ------------------------------------------------------------------ #

    async def get_scraping_browser(self) -> Browser:
        """Return a Playwright Browser connected to Bright Data's Scraping Browser."""
        if self._browser is None:
            pw = await async_playwright().start()
            cdp_url = (
                f"{self.cfg.scraping_browser_ws}"
                f"?auth={self.cfg.api_key}"
                f"&browser=chrome"
            )
            self._browser = await pw.chromium.connect_over_cdp(cdp_url)
            logger.info("Scraping Browser: connected via CDP")
        return self._browser

    async def scraping_browser_fetch(
        self,
        url: str,
        wait_selector: Optional[str] = None,
        scroll: bool = False,
        screenshot: bool = False,
    ) -> dict:
        """
        Navigate to a URL in the Scraping Browser.
        Returns: {"html": str, "screenshot_b64": str|None, "title": str}
        Bright Data handles CAPTCHA solving, fingerprint rotation, IP rotation.
        """
        browser = await self.get_scraping_browser()
        page: Page = await browser.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=45_000)
            if wait_selector:
                await page.wait_for_selector(wait_selector, timeout=10_000)
            if scroll:
                await self._auto_scroll(page)

            html = await page.content()
            title = await page.title()
            screenshot_b64 = None
            if screenshot:
                img_bytes = await page.screenshot(full_page=True, type="jpeg", quality=60)
                import base64
                screenshot_b64 = base64.b64encode(img_bytes).decode()

            return {"html": html, "title": title, "screenshot_b64": screenshot_b64, "url": url}
        finally:
            await page.close()

    @staticmethod
    async def _auto_scroll(page: Page):
        """Scroll to bottom to trigger lazy-loaded content."""
        await page.evaluate("""
            () => new Promise(resolve => {
                let total = 0;
                const step = 300;
                const timer = setInterval(() => {
                    window.scrollBy(0, step);
                    total += step;
                    if (total >= document.body.scrollHeight) {
                        clearInterval(timer);
                        resolve();
                    }
                }, 100);
            })
        """)
        await asyncio.sleep(1)

    # ------------------------------------------------------------------ #
    #  Internal retry logic                                               #
    # ------------------------------------------------------------------ #

    async def _request_with_retry(
        self,
        url: str,
        method: str = "GET",
        max_retries: int = 4,
        tool: str = "Bright Data",
        **kwargs,
    ) -> Any:
        """
        Wrapper for all HTTP calls with exponential backoff.
        Bright Data's infrastructure handles most blocking, but we still
        retry on transient 429/5xx errors.
        """
        for attempt in range(1, max_retries + 1):
            try:
                async with async_timeout.timeout(60):
                    if method == "GET":
                        async with self._session.get(url, **kwargs) as resp:
                            return await self._parse_response(resp, tool)
                    elif method == "POST":
                        async with self._session.post(url, **kwargs) as resp:
                            return await self._parse_response(resp, tool)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                wait = 2 ** attempt
                logger.warning("%s attempt %d/%d failed: %s. Retrying in %ds…",
                               tool, attempt, max_retries, e, wait)
                if attempt == max_retries:
                    raise
                await asyncio.sleep(wait)

    @staticmethod
    async def _parse_response(resp: aiohttp.ClientResponse, tool: str) -> Any:
        if resp.status == 429:
            retry_after = int(resp.headers.get("Retry-After", 15))
            logger.warning("%s rate limited. Sleeping %ds…", tool, retry_after)
            await asyncio.sleep(retry_after)
            raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=429)

        if resp.status >= 500:
            raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=resp.status)

        content_type = resp.headers.get("Content-Type", "")
        if "json" in content_type:
            return await resp.json()
        return await resp.text()
