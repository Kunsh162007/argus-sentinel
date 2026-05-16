"""
ARGUS Sentinel — Test Suite
Tests temporal engine math, signal normalisation, and agent mocking.
Run with: pytest tests/ -v
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agents.base_agent import ArgusSignal, AgentSnapshot
from temporal_engine import TemporalVelocityEngine, VelocityWindow


# ------------------------------------------------------------------ #
#  VelocityWindow tests                                               #
# ------------------------------------------------------------------ #

class TestVelocityWindow:
    def test_baseline_from_history(self):
        w = VelocityWindow(source="news")
        for v in [2.0, 3.0, 4.0, 2.0, 3.0]:
            w.push(v)
        # baseline = mean of all but last 2 = mean([2,3,4]) = 3.0
        assert abs(w.baseline - 3.0) < 0.01

    def test_velocity_zero_at_baseline(self):
        w = VelocityWindow(source="news")
        for v in [5.0, 5.0, 5.0, 5.0, 5.0]:
            w.push(v)
        # recent ≈ baseline → velocity ≈ 0
        assert w.velocity < 1.0

    def test_velocity_high_on_spike(self):
        w = VelocityWindow(source="news")
        for v in [2.0, 2.0, 2.0, 2.0, 2.0]:
            w.push(v)
        w.push(10.0)
        # recent avg ≈ 6, baseline = 2 → velocity should be > 5
        assert w.velocity > 5.0

    def test_velocity_capped_at_10(self):
        w = VelocityWindow(source="news")
        for _ in range(5):
            w.push(0.1)
        w.push(1000.0)
        assert w.velocity <= 10.0

    def test_slope_positive_on_growth(self):
        w = VelocityWindow(source="news")
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            w.push(v)
        assert w.slope > 0

    def test_slope_negative_on_decline(self):
        w = VelocityWindow(source="news")
        for v in [5.0, 4.0, 3.0, 2.0, 1.0]:
            w.push(v)
        assert w.slope < 0

    def test_window_bounded(self):
        w = VelocityWindow(source="news", max_window=5)
        for v in range(20):
            w.push(float(v))
        assert len(w.counts) == 5


# ------------------------------------------------------------------ #
#  Temporal velocity engine tests                                     #
# ------------------------------------------------------------------ #

class TestTemporalEngine:
    def _make_signals(self, source: str, count: int, weight: float = 0.7) -> list[ArgusSignal]:
        return [
            ArgusSignal(
                source=source,
                signal_type="mention",
                entity="TestCo",
                content=f"Signal {i}",
                url=f"https://example.com/{i}",
                timestamp=time.time(),
                weight=weight,
            )
            for i in range(count)
        ]

    @pytest.mark.asyncio
    async def test_low_velocity_on_baseline(self):
        engine = TemporalVelocityEngine()
        signals = (
            self._make_signals("news", 5) +
            self._make_signals("finance", 2) +
            self._make_signals("site", 1) +
            self._make_signals("social", 3)
        )
        # Seed 6 identical snapshots to establish baseline
        for _ in range(6):
            with patch.object(engine, '_generate_prediction', return_value=("Test prediction", 0.4)):
                profile = await engine.process("TestCo", signals, signals)

        # Velocity should be near zero (no change from baseline)
        assert profile.velocity_score < 3.0

    @pytest.mark.asyncio
    async def test_high_velocity_on_surge(self):
        engine = TemporalVelocityEngine()
        baseline = self._make_signals("news", 3, weight=0.5)

        # Seed baseline
        for _ in range(5):
            with patch.object(engine, '_generate_prediction', return_value=("baseline", 0.3)):
                await engine.process("TestCo", baseline, [])

        # Simulate a surge
        surge = self._make_signals("news", 50, weight=0.9) + self._make_signals("finance", 20)
        with patch.object(engine, '_generate_prediction', return_value=("High activity", 0.85)):
            profile = await engine.process("TestCo", surge, surge)

        assert profile.velocity_score > 3.0

    @pytest.mark.asyncio
    async def test_anomaly_detection_on_spike(self):
        engine = TemporalVelocityEngine()

        # Seed stable history
        stable = self._make_signals("news", 4)
        for _ in range(7):
            with patch.object(engine, '_generate_prediction', return_value=("stable", 0.3)):
                await engine.process("TestCo", stable, [])

        # Force a spike into composite history
        engine._composite_history["TestCo"] = [1.0, 1.1, 0.9, 1.0, 1.2, 0.8, 1.0, 9.5]

        spike = self._make_signals("news", 100, weight=1.0)
        with patch.object(engine, '_generate_prediction', return_value=("Spike!", 0.9)):
            profile = await engine.process("TestCo", spike, spike)

        assert profile.anomaly_detected is True

    def test_slope_computation(self):
        engine = TemporalVelocityEngine()
        ascending = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert engine._compute_slope(ascending) > 0
        assert engine._compute_slope(ascending[::-1]) < 0
        assert engine._compute_slope([3.0] * 5) == pytest.approx(0.0, abs=0.01)


# ------------------------------------------------------------------ #
#  Signal fingerprinting / deduplication tests                        #
# ------------------------------------------------------------------ #

class TestSignalDeduplication:
    def test_same_url_same_content_deduped(self):
        s1 = ArgusSignal("news", "mention", "Co", "Content A", "https://x.com/1", time.time())
        s2 = ArgusSignal("news", "mention", "Co", "Content A", "https://x.com/1", time.time())
        assert s1.fingerprint() == s2.fingerprint()

    def test_different_url_not_deduped(self):
        s1 = ArgusSignal("news", "mention", "Co", "Content A", "https://x.com/1", time.time())
        s2 = ArgusSignal("news", "mention", "Co", "Content A", "https://x.com/2", time.time())
        assert s1.fingerprint() != s2.fingerprint()

    def test_different_source_not_deduped(self):
        s1 = ArgusSignal("news", "mention", "Co", "Content A", "https://x.com/1", time.time())
        s2 = ArgusSignal("social", "mention", "Co", "Content A", "https://x.com/1", time.time())
        assert s1.fingerprint() != s2.fingerprint()


# ------------------------------------------------------------------ #
#  Intent extraction test (mocked LLM)                               #
# ------------------------------------------------------------------ #

class TestIntentExtraction:
    @pytest.mark.asyncio
    async def test_extract_entity_from_query(self):
        from orchestrator import ArgusOrchestrator
        orch = ArgusOrchestrator()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"entities":["OpenAI"],"intent":"predict","domain":"product","timeframe_days":14,"urgency":"immediate"}')]

        with patch.object(orch.anthropic.messages, 'create', new=AsyncMock(return_value=mock_response)):
            intent = await orch._extract_intent("What will OpenAI launch next?")

        assert "OpenAI" in intent.entities
        assert intent.intent == "predict"
        assert intent.domain == "product"

    @pytest.mark.asyncio
    async def test_fallback_on_bad_json(self):
        from orchestrator import ArgusOrchestrator
        orch = ArgusOrchestrator()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="this is not json")]

        with patch.object(orch.anthropic.messages, 'create', new=AsyncMock(return_value=mock_response)):
            intent = await orch._extract_intent("Monitor Stripe M&A")

        # Should fall back gracefully
        assert len(intent.entities) >= 1
        assert intent.urgency in ("immediate", "scheduled", "background")


# ------------------------------------------------------------------ #
#  News agent weight computation tests                                 #
# ------------------------------------------------------------------ #

class TestNewsAgentWeights:
    def setup_method(self):
        from agents.news_agent import NewsAgent
        mock_client = MagicMock()
        self.agent = NewsAgent(mock_client)

    def test_tier1_source_gets_high_weight(self):
        w = self.agent._compute_weight("bloomberg.com", "company launches new product")
        assert w >= 0.9

    def test_unknown_source_gets_low_weight(self):
        w = self.agent._compute_weight("randomsite.xyz", "article about something")
        assert w < 0.6

    def test_high_signal_keyword_boosts_weight(self):
        w_base = self.agent._compute_weight("example.com", "article about a company")
        w_boost = self.agent._compute_weight("example.com", "company announces new launch funding")
        assert w_boost > w_base

    def test_sentiment_positive(self):
        s = self.agent._detect_sentiment("company announces record revenue growth")
        assert s == "positive"

    def test_sentiment_negative(self):
        s = self.agent._detect_sentiment("company faces massive lawsuit investigation")
        assert s == "negative"

    def test_sentiment_neutral(self):
        s = self.agent._detect_sentiment("company releases quarterly report")
        assert s == "neutral"
