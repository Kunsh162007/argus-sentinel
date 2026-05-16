"""
ARGUS Sentinel — Signal Miner Agent
Uses Bright Data Web Unlocker to bypass bot detection on:
  - Reddit (r/MachineLearning, r/technology, r/programming, etc.)
  - Hacker News (Y Combinator discussion)
  - Twitter/X (trending mentions)
  - GitHub (commit activity, star velocity, issue patterns)
  - Product Hunt (pre-launch teaser detection)

Why Web Unlocker?
  - Reddit blocks datacenter IPs in ~2 requests
  - GitHub rate-limits API for scraping at scale
  - X requires auth + fingerprint that changes daily
  - Web Unlocker handles ALL of this: residential IPs, cookie injection,
    TLS fingerprinting, browser headers — fully automatic
"""

import asyncio
import json
import logging
import re
import time
from typing import Optional

from bs4 import BeautifulSoup

from agents.base_agent import BaseAgent, ArgusSignal
from bright_data_client import BrightDataClient
from config import CONFIG

logger = logging.getLogger("argus.agent.signal")


REDDIT_SUBS = [
    "MachineLearning", "technology", "programming", "artificial",
    "singularity", "OpenAI", "ChatGPT", "LanguageModel",
]

# Excitement/signal keywords from community discussions
HYPE_WORDS = {
    "leaked", "leak", "rumour", "rumor", "spotted", "exclusive",
    "breaking", "just dropped", "just shipped", "announced", "launching",
    "dropping", "imminent", "confirmed", "insider", "early access",
}

CONCERN_WORDS = {
    "bug", "broken", "regression", "outage", "down", "deprecated",
    "dead", "failed", "mistake", "disaster", "warning",
}


class SignalMinerAgent(BaseAgent):
    """
    Extracts weak signals from community platforms that often surface
    product developments before official announcements.
    
    The insight: Engineers and researchers talk on Hacker News, Reddit,
    and Discord 48-72 hours before press releases. Web Unlocker lets us
    read these platforms at scale without getting blocked.
    """

    name = "signal"
    source = "social"

    def __init__(self, client: BrightDataClient):
        super().__init__(client)
        self.cfg = CONFIG.agent

    async def collect(self, entity: str, query: str) -> list[ArgusSignal]:
        """Parallel collection from Reddit, HN, GitHub, and Product Hunt."""
        results = await asyncio.gather(
            self._collect_reddit(entity, query),
            self._collect_hn(entity, query),
            self._collect_github(entity),
            self._collect_producthunt(entity),
            return_exceptions=True,
        )

        signals: list[ArgusSignal] = []
        for batch in results:
            if isinstance(batch, Exception):
                logger.debug("Signal miner sub-collector failed: %s", batch)
                continue
            signals.extend(batch)

        logger.info("SignalMiner: %d signals for '%s'", len(signals), entity)
        return signals

    # ------------------------------------------------------------------ #
    #  Reddit                                                              #
    # ------------------------------------------------------------------ #

    async def _collect_reddit(self, entity: str, query: str) -> list[ArgusSignal]:
        """
        Searches Reddit via JSON API endpoints, unlocked by Web Unlocker.
        Reddit's old.reddit.com JSON format is much easier to parse.
        """
        signals = []
        search_term = quote_url(f"{entity} {query}")

        # Search across relevant subreddits
        search_url = (
            f"https://www.reddit.com/search.json"
            f"?q={search_term}&sort=new&t=week&limit=25"
        )

        html = await self.client.unlock(
            url=search_url,
            render_js=False,
            headers={"Accept": "application/json"},
        )

        try:
            data = json.loads(html)
            posts = data.get("data", {}).get("children", [])
        except (json.JSONDecodeError, AttributeError):
            posts = []

        for post in posts:
            p = post.get("data", {})
            title = p.get("title", "")
            score = p.get("score", 0)
            comments = p.get("num_comments", 0)
            url = f"https://reddit.com{p.get('permalink', '')}"
            sub = p.get("subreddit", "")

            # Weight by engagement
            engagement = min((score + comments * 3) / 1000, 1.0)
            text_lower = title.lower()
            has_hype = any(w in text_lower for w in HYPE_WORDS)
            weight = round(min(0.4 + engagement + (0.2 if has_hype else 0), 0.95), 2)

            signals.append(ArgusSignal(
                source="social",
                signal_type="mention",
                entity=entity,
                content=f"Reddit r/{sub}: {title} (↑{score} 💬{comments})",
                url=url,
                timestamp=p.get("created_utc", time.time()),
                weight=weight,
                metadata={
                    "platform": "reddit",
                    "subreddit": sub,
                    "score": score,
                    "comments": comments,
                    "has_hype_keywords": has_hype,
                },
            ))

        return signals

    # ------------------------------------------------------------------ #
    #  Hacker News                                                         #
    # ------------------------------------------------------------------ #

    async def _collect_hn(self, entity: str, query: str) -> list[ArgusSignal]:
        """
        HN Algolia search API — Web Unlocker bypasses IP limits.
        HN discussions are excellent pre-signal for tech company events.
        """
        import urllib.parse
        q = urllib.parse.quote(f"{entity} {query}")
        url = (
            f"https://hn.algolia.com/api/v1/search"
            f"?query={q}&tags=story&hitsPerPage=20&numericFilters=created_at_i>%s"
            % int(time.time() - 7 * 86400)  # Last 7 days
        )

        html = await self.client.unlock(url=url, render_js=False)
        signals = []

        try:
            data = json.loads(html)
            hits = data.get("hits", [])
        except (json.JSONDecodeError, AttributeError):
            hits = []

        for hit in hits:
            title = hit.get("title", "")
            points = hit.get("points", 0)
            num_comments = hit.get("num_comments", 0)
            story_url = hit.get("url", f"https://news.ycombinator.com/item?id={hit.get('objectID','')}")
            hn_url = f"https://news.ycombinator.com/item?id={hit.get('objectID','')}"
            created = hit.get("created_at_i", time.time())

            engagement = min((points + num_comments * 4) / 1500, 1.0)
            text_lower = title.lower()
            has_hype = any(w in text_lower for w in HYPE_WORDS)
            weight = round(min(0.45 + engagement + (0.2 if has_hype else 0), 0.95), 2)

            signals.append(ArgusSignal(
                source="social",
                signal_type="mention",
                entity=entity,
                content=f"HN: {title} (↑{points} 💬{num_comments})",
                url=hn_url,
                timestamp=created,
                weight=weight,
                metadata={
                    "platform": "hackernews",
                    "points": points,
                    "num_comments": num_comments,
                    "story_url": story_url,
                },
            ))

        return signals

    # ------------------------------------------------------------------ #
    #  GitHub — commit velocity, star velocity, issues                    #
    # ------------------------------------------------------------------ #

    async def _collect_github(self, entity: str) -> list[ArgusSignal]:
        """
        GitHub activity is a leading indicator for open-source entities.
        Commit surges in private repos often leak through related public activity.
        Web Unlocker handles GitHub's aggressive bot detection.
        """
        # Search for repos matching entity
        q = entity.lower().replace(" ", "+")
        search_url = f"https://github.com/search?q={q}&type=repositories&s=stars&o=desc"

        html = await self.client.unlock(url=search_url, render_js=True)
        signals = []
        soup = BeautifulSoup(html, "lxml")

        # Extract top repos
        repos = []
        for item in soup.select("li.repo-list-item, div[data-testid='results-list'] > div")[:5]:
            a_tag = item.find("a", attrs={"itemprop": "name codeRepository"}) or item.find("a", href=re.compile(r"^/[^/]+/[^/]+$"))
            if not a_tag:
                continue
            repos.append({
                "name": a_tag.get_text(strip=True),
                "url": f"https://github.com{a_tag.get('href','')}",
            })

        # For each repo, check commit activity (last week vs month trend)
        for repo in repos[:3]:
            activity_url = repo["url"] + "/graphs/commit-activity"
            activity_html = await self.client.unlock(url=activity_url, render_js=True)

            # Look for commit counts in the page
            commit_numbers = re.findall(r"(\d+)\s+commits?\s+(?:this|last)\s+week", activity_html, re.I)
            if commit_numbers:
                count = int(commit_numbers[0])
                weight = min(0.3 + count / 100, 0.85)
                signals.append(ArgusSignal(
                    source="social",
                    signal_type="mention",
                    entity=entity,
                    content=f"GitHub {repo['name']}: {count} commits this week",
                    url=repo["url"],
                    timestamp=time.time(),
                    weight=round(weight, 2),
                    metadata={"platform": "github", "repo": repo["name"], "commits": count},
                ))

        return signals

    # ------------------------------------------------------------------ #
    #  Product Hunt                                                        #
    # ------------------------------------------------------------------ #

    async def _collect_producthunt(self, entity: str) -> list[ArgusSignal]:
        """
        Product Hunt upcoming / just-launched section.
        Companies sometimes tease launches here 24-48h before public announcement.
        """
        url = f"https://www.producthunt.com/search?q={quote_url(entity)}"
        html = await self.client.unlock(url=url, render_js=True)
        signals = []
        soup = BeautifulSoup(html, "lxml")

        for item in soup.find_all("div", attrs={"data-test": "post-item"})[:10]:
            name_tag = item.find(["h3", "h2"])
            tagline_tag = item.find("p")
            votes_tag = item.find(string=re.compile(r"^\d+$"))

            if not name_tag:
                continue

            name = name_tag.get_text(strip=True)
            tagline = tagline_tag.get_text(strip=True) if tagline_tag else ""
            votes = int(votes_tag) if votes_tag else 0
            entity_lower = entity.lower()

            if entity_lower in name.lower() or entity_lower in tagline.lower():
                weight = min(0.5 + votes / 500, 0.9)
                signals.append(ArgusSignal(
                    source="social",
                    signal_type="mention",
                    entity=entity,
                    content=f"Product Hunt: '{name}' — {tagline[:80]} (▲{votes})",
                    url=url,
                    timestamp=time.time(),
                    weight=round(weight, 2),
                    metadata={"platform": "producthunt", "votes": votes},
                ))

        return signals


def quote_url(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")
