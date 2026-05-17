"""
ARGUS Sentinel — Orchestrator Agent (fixed for Python 3.14 + LangChain 0.3+)
Uses Anthropic SDK directly for MCP integration — no LangChain agent executor.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

import google.generativeai as genai

from agents.news_agent import NewsAgent
from agents.finance_agent import FinanceAgent
from agents.site_watcher import SiteWatcherAgent
from agents.signal_miner import SignalMinerAgent
from bright_data_client import BrightDataClient
from temporal_engine import TemporalVelocityEngine, TemporalProfile
from config import CONFIG

logger = logging.getLogger("argus.orchestrator")


@dataclass
class QueryIntent:
    entities: list
    intent: str
    domain: str
    timeframe_days: int
    urgency: str
    raw_query: str


@dataclass
class ArgusReport:
    query: str
    entities: list
    timestamp: float
    profiles: list
    executive_summary: str
    key_findings: list
    recommended_actions: list
    alert_triggered: bool
    processing_time_s: float

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "entities": self.entities,
            "timestamp": self.timestamp,
            "profiles": [p.to_dict() for p in self.profiles],
            "executive_summary": self.executive_summary,
            "key_findings": self.key_findings,
            "recommended_actions": self.recommended_actions,
            "alert_triggered": self.alert_triggered,
            "processing_time_s": round(self.processing_time_s, 2),
        }


ORCHESTRATOR_SYSTEM_PROMPT = """You are ARGUS Sentinel's master intelligence orchestrator.
You receive temporal web intelligence data collected by specialised agents and synthesise
it into actionable predictions. Be specific, cite signal sources, quantify confidence."""


async def _gemini_with_retry(model, prompt: str, max_retries: int = 3) -> str:
    """Call Gemini with automatic retry on 429 rate-limit errors."""
    for attempt in range(1, max_retries + 1):
        try:
            resp = await model.generate_content_async(prompt)
            return resp.text
        except Exception as e:
            msg = str(e)
            if "429" in msg and attempt < max_retries:
                # Parse retry delay from error message if present
                import re as _re
                m = _re.search(r"retry[^\d]*(\d+)", msg, _re.I)
                wait = int(m.group(1)) if m else 30 * attempt
                wait = min(wait, 60)
                logger.warning("Gemini 429 — waiting %ds before retry %d/%d", wait, attempt, max_retries)
                await asyncio.sleep(wait)
            else:
                raise
    raise RuntimeError("Gemini retries exhausted")


class ArgusOrchestrator:
    def __init__(self):
        genai.configure(api_key=CONFIG.model.google_api_key)
        self._model = genai.GenerativeModel(CONFIG.model.orchestrator_model)
        self.temporal_engine = TemporalVelocityEngine()

    async def run(self, query: str) -> ArgusReport:
        t0 = time.time()
        logger.info("ARGUS: processing '%s'", query)

        intent = await self._extract_intent(query)
        logger.info("Intent: entities=%s domain=%s", intent.entities, intent.domain)

        async with BrightDataClient() as bd_client:
            agents = [
                NewsAgent(bd_client),
                FinanceAgent(bd_client),
                SiteWatcherAgent(bd_client),
                SignalMinerAgent(bd_client),
            ]
            entity_tasks = [
                self._process_entity(entity, query, agents)
                for entity in intent.entities
            ]
            profiles = await asyncio.gather(*entity_tasks)

        summary, findings, actions = await self._synthesise(query, intent, list(profiles))

        elapsed = time.time() - t0
        alert = any(p.alert for p in profiles)

        return ArgusReport(
            query=query,
            entities=intent.entities,
            timestamp=time.time(),
            profiles=list(profiles),
            executive_summary=summary,
            key_findings=findings,
            recommended_actions=actions,
            alert_triggered=alert,
            processing_time_s=elapsed,
        )

    async def _extract_intent(self, query: str) -> QueryIntent:
        prompt = (
            f'Extract intelligence query intent from: "{query}"\n\n'
            'Return ONLY a JSON object:\n'
            '{"entities":["Company"],"intent":"monitor|investigate|predict|compare",'
            '"domain":"product|financial|competitive|general","timeframe_days":14,'
            '"urgency":"immediate|scheduled|background"}\n\n'
            'entities: companies/topics to investigate (max 3)\n'
            'timeframe_days: how far ahead the user cares about'
        )
        try:
            raw = (await _gemini_with_retry(self._model, prompt)).strip()
            raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(raw)
            return QueryIntent(
                entities=data.get("entities", [query.split()[0]])[:3],
                intent=data.get("intent", "investigate"),
                domain=data.get("domain", "general"),
                timeframe_days=int(data.get("timeframe_days", 14)),
                urgency=data.get("urgency", "immediate"),
                raw_query=query,
            )
        except Exception as e:
            logger.warning("Intent parse failed: %s", e)
            entity = " ".join(query.split()[:2])
            return QueryIntent(
                entities=[entity], intent="investigate",
                domain="general", timeframe_days=14,
                urgency="immediate", raw_query=query,
            )

    async def _process_entity(self, entity: str, query: str, agents: list) -> TemporalProfile:
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*[a.run_and_snapshot(entity, query) for a in agents],
                               return_exceptions=True),
                timeout=20,
            )
        except asyncio.TimeoutError:
            logger.warning("Agents timed out for '%s' after 20s — continuing with empty signals", entity)
            results = []
        all_signals, new_signals = [], []
        for r in results:
            if isinstance(r, Exception):
                logger.warning("Agent failed for '%s': %s", entity, r)
                continue
            a, n = r
            all_signals.extend(a)
            new_signals.extend(n)

        logger.info("Entity '%s': %d signals (%d new)", entity, len(all_signals), len(new_signals))
        return await self.temporal_engine.process(entity, all_signals, new_signals)

    async def _synthesise(
        self,
        query: str,
        intent: QueryIntent,
        profiles: list,
    ) -> tuple:
        return await self._synthesise_direct(query, profiles)

    async def _synthesise_direct(self, query: str, profiles: list) -> tuple:
        """Synthesis via Gemini Flash (free)."""
        context = self._build_context(profiles)
        prompt = (
            f"{ORCHESTRATOR_SYSTEM_PROMPT}\n\n"
            f'Intelligence query: "{query}"\n\n'
            f'Temporal data:\n{context}\n\n'
            'Return JSON only: {"executive_summary":"...","key_findings":[...],'
            '"recommended_actions":[...]}'
        )
        text = await _gemini_with_retry(self._model, prompt)
        return self._parse_synthesis(text)

    @staticmethod
    def _build_context(profiles: list) -> str:
        lines = []
        for p in profiles:
            lines.append(
                f"Entity: {p.entity}\n"
                f"  Velocity: {p.velocity_score}/10 | slope: {p.trajectory_slope:+.3f}\n"
                f"  Prediction: {p.prediction} ({p.prediction_confidence:.0%})\n"
                f"  Anomaly: {p.anomaly_detected}\n"
                f"  Top signals:\n" +
                "\n".join(
                    f"    [{s['source'].upper()}] {s['content'][:100]}"
                    for s in p.top_signals[:4]
                )
            )
        return "\n\n".join(lines)

    @staticmethod
    def _parse_synthesis(text: str) -> tuple:
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            data = json.loads(text)
            return (
                data.get("executive_summary", "Analysis complete."),
                data.get("key_findings", []),
                data.get("recommended_actions", []),
            )
        except Exception:
            return (text[:400] if text else "Analysis complete.", [], [])
