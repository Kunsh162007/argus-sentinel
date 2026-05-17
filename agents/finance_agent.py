"""
ARGUS Sentinel — Finance Agent
Uses Bright Data Web Scraper API (pre-built datasets) to collect:
  - SEC EDGAR filings (10-K, 10-Q, 8-K, S-1)
  - LinkedIn company data (headcount, hiring velocity, exec changes)
  - Crunchbase funding rounds and investor signals

Why Web Scraper API?
  - LinkedIn, SEC, Crunchbase all have aggressive anti-bot measures
  - Bright Data maintains scrapers for 660+ sites — we get JSON, not HTML
  - Zero maintenance: if a site redesigns, Bright Data updates the scraper
"""

import logging
import time
from typing import Optional

from agents.base_agent import BaseAgent, ArgusSignal
from bright_data_client import BrightDataClient
from config import CONFIG

logger = logging.getLogger("argus.agent.finance")

# Filing types and their signal importance
FILING_WEIGHTS = {
    "S-1": 1.0,    # IPO filing — maximum signal
    "8-K": 0.9,    # Material event — very high
    "SC 13G": 0.8, # Large stake acquisition
    "SC 13D": 0.9, # Activist position
    "4":    0.7,   # Insider transaction
    "10-Q": 0.5,   # Quarterly — baseline
    "10-K": 0.6,   # Annual
    "DEFM14A": 0.85, # Merger proxy — M&A signal
}


class FinanceAgent(BaseAgent):
    """
    Collects financial and corporate intelligence signals using
    Bright Data's pre-built dataset scrapers.
    
    Key insight: SEC 8-K filings, LinkedIn headcount changes,
    and Crunchbase funding rounds often appear 24-72 hours
    BEFORE mainstream news coverage — giving ARGUS predictive edge.
    """

    name = "finance"
    source = "finance"

    def __init__(self, client: BrightDataClient):
        super().__init__(client)
        self.cfg = CONFIG.agent

    async def collect(self, entity: str, query: str) -> list[ArgusSignal]:
        """Parallel collection from LinkedIn, Crunchbase, and SEC EDGAR."""
        if not self.client.cfg.api_key:
            logger.info("FinanceAgent: no Bright Data API key — skipping")
            return []
        import asyncio
        results = await asyncio.gather(
            self._collect_linkedin(entity),
            self._collect_crunchbase(entity),
            self._collect_sec_filings(entity),
            return_exceptions=True,
        )

        signals: list[ArgusSignal] = []
        for batch in results:
            if isinstance(batch, Exception):
                logger.warning("Finance sub-collector failed: %s", batch)
                continue
            signals.extend(batch)

        logger.info("FinanceAgent: %d signals for '%s'", len(signals), entity)
        return signals

    # ------------------------------------------------------------------ #
    #  LinkedIn — headcount, hiring velocity, executive changes           #
    # ------------------------------------------------------------------ #

    async def _collect_linkedin(self, entity: str) -> list[ArgusSignal]:
        """
        Uses Bright Data's LinkedIn Company dataset.
        Tracks: employee count, open roles, department changes.
        Hiring surge in AI/ML roles is one of the strongest pre-announcement signals.
        """
        try:
            records = await self.client.scraper_api_fetch(
                dataset_id=self.cfg.linkedin_dataset_id,
                inputs=[{"company_name": entity}],
            )
        except Exception as e:
            logger.warning("LinkedIn scraper failed for %s: %s", entity, e)
            return []

        signals = []
        for rec in records:
            if not isinstance(rec, dict):
                continue

            # Employee count signal
            headcount = rec.get("employee_count") or rec.get("followers")
            if headcount:
                signals.append(ArgusSignal(
                    source="finance",
                    signal_type="hiring",
                    entity=entity,
                    content=f"LinkedIn headcount: {headcount:,} employees",
                    url=rec.get("url", f"https://linkedin.com/company/{entity.lower().replace(' ','-')}"),
                    timestamp=time.time(),
                    weight=0.6,
                    metadata={"headcount": headcount, "platform": "linkedin"},
                ))

            # Open roles signal (hiring velocity proxy)
            open_roles = rec.get("open_jobs") or rec.get("job_count", 0)
            if open_roles:
                weight = min(0.4 + (open_roles / 1000), 0.95)
                signals.append(ArgusSignal(
                    source="finance",
                    signal_type="hiring",
                    entity=entity,
                    content=f"LinkedIn open roles: {open_roles} postings",
                    url=rec.get("jobs_url", ""),
                    timestamp=time.time(),
                    weight=round(weight, 2),
                    metadata={"open_roles": open_roles},
                ))

            # Recent executive hires (C-suite = very high signal)
            for person in rec.get("recent_hires", []):
                title = person.get("title", "").lower()
                if any(t in title for t in ["cto", "ceo", "vp", "chief", "head of", "director"]):
                    signals.append(ArgusSignal(
                        source="finance",
                        signal_type="hiring",
                        entity=entity,
                        content=f"Executive hire: {person.get('name','')} as {person.get('title','')}",
                        url=person.get("profile_url", ""),
                        timestamp=time.time(),
                        weight=0.88,
                        metadata={"person": person, "signal_class": "exec_hire"},
                    ))

        return signals

    # ------------------------------------------------------------------ #
    #  Crunchbase — funding rounds, investors, valuations                 #
    # ------------------------------------------------------------------ #

    async def _collect_crunchbase(self, entity: str) -> list[ArgusSignal]:
        """
        Crunchbase dataset: funding rounds, lead investors, valuation.
        A new funding round appearing in Crunchbase often precedes
        the press release by days.
        """
        try:
            records = await self.client.scraper_api_fetch(
                dataset_id=self.cfg.crunchbase_dataset_id,
                inputs=[{"company": entity}],
            )
        except Exception as e:
            logger.warning("Crunchbase scraper failed for %s: %s", entity, e)
            return []

        signals = []
        for rec in records:
            if not isinstance(rec, dict):
                continue

            # Latest funding round
            rounds = rec.get("funding_rounds", [])
            for r in rounds[-3:]:  # Last 3 rounds
                amount = r.get("raised_amount_usd", 0) or 0
                rtype = r.get("funding_type", "funding")
                date = r.get("announced_on", "")
                investors = ", ".join(r.get("lead_investors", [])[:3])
                weight = min(0.5 + (amount / 1_000_000_000), 0.98) if amount else 0.7

                signals.append(ArgusSignal(
                    source="finance",
                    signal_type="filing",
                    entity=entity,
                    content=(
                        f"Crunchbase: {rtype.upper()} ${amount/1e6:.0f}M "
                        f"from {investors or 'undisclosed'} ({date})"
                    ),
                    url=rec.get("url", ""),
                    timestamp=time.time(),
                    weight=round(weight, 2),
                    metadata={"round": r, "signal_class": "funding"},
                ))

            # Total raised
            total_raised = rec.get("total_funding_usd", 0) or 0
            if total_raised:
                signals.append(ArgusSignal(
                    source="finance",
                    signal_type="filing",
                    entity=entity,
                    content=f"Crunchbase: total raised ${total_raised/1e9:.1f}B",
                    url=rec.get("url", ""),
                    timestamp=time.time(),
                    weight=0.5,
                    metadata={"total_raised_usd": total_raised},
                ))

        return signals

    # ------------------------------------------------------------------ #
    #  SEC EDGAR — material event filings                                 #
    # ------------------------------------------------------------------ #

    async def _collect_sec_filings(self, entity: str) -> list[ArgusSignal]:
        """
        SEC EDGAR dataset: 8-K (material events), S-1 (IPO), DEFM14A (M&A proxy).
        These are legally mandated and often the FIRST structured data source
        to confirm a major corporate event.
        """
        try:
            records = await self.client.scraper_api_fetch(
                dataset_id=self.cfg.sec_edgar_dataset_id,
                inputs=[{"company": entity, "filing_types": ["8-K", "S-1", "DEFM14A", "SC 13D"]}],
            )
        except Exception as e:
            logger.warning("SEC EDGAR scraper failed for %s: %s", entity, e)
            return []

        signals = []
        for rec in records:
            if not isinstance(rec, dict):
                continue

            form_type = rec.get("form_type", "")
            description = rec.get("description", rec.get("items", "material event"))
            filed_date = rec.get("filed_date", rec.get("date", ""))
            url = rec.get("url", rec.get("filing_url", ""))
            weight = FILING_WEIGHTS.get(form_type, 0.5)

            signals.append(ArgusSignal(
                source="finance",
                signal_type="filing",
                entity=entity,
                content=f"SEC {form_type}: {description} (filed {filed_date})",
                url=url,
                timestamp=time.time(),
                weight=weight,
                metadata={
                    "form_type": form_type,
                    "filed_date": filed_date,
                    "signal_class": "sec_filing",
                },
            ))

        return signals
