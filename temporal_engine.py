"""
ARGUS Sentinel — Temporal Velocity Engine
════════════════════════════════════════════════════════════════════════════════
This is the core innovation that makes ARGUS unique.

Traditional tools give you a snapshot: "X was mentioned 42 times today."
ARGUS measures VELOCITY: "X mentions are accelerating 3.4× faster than baseline."

The engine computes:
  1. Per-source velocity scores  (0–10 scale, 10 = maximum acceleration)
  2. Cross-domain correlation    (signals reinforcing each other = higher confidence)
  3. Temporal trajectory         (is velocity increasing, plateauing, or reversing?)
  4. Predictive confidence score (how likely is a major event in next N days?)
  5. Anomaly detection           (sudden spikes vs gradual builds)

Methodology:
  - We keep sliding windows of signal counts per source
  - Velocity = (recent_window_avg - baseline_avg) / baseline_avg
  - Trajectory = linear regression slope across velocity history
  - Cross-domain boost: if 3+ sources show velocity, multiply confidence
  - Prediction: trajectory extrapolation + pattern matching vs historical events
════════════════════════════════════════════════════════════════════════════════
"""

import asyncio
import json
import logging
import math
import statistics
import time
from dataclasses import dataclass, field
from typing import Optional

import google.generativeai as genai

from agents.base_agent import ArgusSignal, AgentSnapshot
from config import CONFIG

logger = logging.getLogger("argus.temporal")


@dataclass
class VelocityWindow:
    """Rolling window of signal counts for one source."""
    source: str
    counts: list[float] = field(default_factory=list)  # Most recent last
    timestamps: list[float] = field(default_factory=list)
    max_window: int = 10

    def push(self, count: float, ts: float = None):
        self.counts.append(count)
        self.timestamps.append(ts or time.time())
        if len(self.counts) > self.max_window:
            self.counts.pop(0)
            self.timestamps.pop(0)

    @property
    def baseline(self) -> float:
        if len(self.counts) < 3:
            return max(self.counts[-1], 1) if self.counts else 1.0
        return statistics.mean(self.counts[:-2]) or 1.0

    @property
    def recent(self) -> float:
        if not self.counts:
            return 0.0
        return statistics.mean(self.counts[-2:])

    @property
    def velocity(self) -> float:
        """Relative change: (recent - baseline) / baseline, clamped 0-10."""
        if self.baseline == 0:
            return 0.0
        raw = (self.recent - self.baseline) / self.baseline
        return round(min(max(raw * 5, 0), 10), 2)

    @property
    def slope(self) -> float:
        """Linear regression slope across recent counts (trajectory direction)."""
        if len(self.counts) < 3:
            return 0.0
        n = len(self.counts)
        xs = list(range(n))
        ys = self.counts
        x_mean = statistics.mean(xs)
        y_mean = statistics.mean(ys)
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
        denominator = sum((x - x_mean) ** 2 for x in xs) or 1e-9
        return numerator / denominator


@dataclass
class TemporalProfile:
    """Complete temporal intelligence profile for one entity."""
    entity: str
    timestamp: float
    velocity_score: float           # 0–10 composite
    source_velocities: dict         # source → velocity
    trajectory: list[float]         # history of composite velocity scores
    trajectory_slope: float         # positive = accelerating
    prediction: str                 # Natural language prediction
    prediction_confidence: float    # 0–1
    anomaly_detected: bool
    top_signals: list[dict]
    alert: bool

    def to_dict(self) -> dict:
        return {
            "entity": self.entity,
            "timestamp": self.timestamp,
            "velocity_score": self.velocity_score,
            "source_velocities": self.source_velocities,
            "trajectory": self.trajectory,
            "trajectory_slope": round(self.trajectory_slope, 3),
            "prediction": self.prediction,
            "prediction_confidence": round(self.prediction_confidence, 2),
            "anomaly_detected": self.anomaly_detected,
            "top_signals": self.top_signals,
            "alert": self.alert,
        }


class TemporalVelocityEngine:
    """
    Computes velocity, trajectories, and predictions from multi-agent signals.
    
    Source weights (how much each source contributes to the composite score):
      news    = 0.28   (high volume, early signal)
      finance = 0.32   (low volume, very high precision)
      site    = 0.22   (medium precision, structural changes)
      social  = 0.18   (high noise, but fastest to react)
    
    Cross-domain multiplier: if ≥3 sources show velocity > 3, multiply by 1.4
    """

    SOURCE_WEIGHTS = {
        "news": 0.28,
        "finance": 0.32,
        "site": 0.22,
        "social": 0.18,
    }

    CROSS_DOMAIN_MULTIPLIER = 1.4
    CROSS_DOMAIN_THRESHOLD = 3.0
    ANOMALY_ZSCORE_THRESHOLD = 2.5

    def __init__(self):
        self._windows: dict[str, dict[str, VelocityWindow]] = {}
        self._composite_history: dict[str, list[float]] = {}
        genai.configure(api_key=CONFIG.model.google_api_key)
        self._model = genai.GenerativeModel(CONFIG.model.analysis_model)

    def _get_window(self, entity: str, source: str) -> VelocityWindow:
        if entity not in self._windows:
            self._windows[entity] = {}
        if source not in self._windows[entity]:
            self._windows[entity][source] = VelocityWindow(source=source)
        return self._windows[entity][source]

    async def process(
        self,
        entity: str,
        all_signals: list[ArgusSignal],
        new_signals: list[ArgusSignal],
    ) -> TemporalProfile:
        """
        Main entry: given a batch of signals for an entity,
        compute velocity, trajectory, and prediction.
        """
        ts = time.time()

        # --- 1. Update velocity windows per source ---
        source_counts: dict[str, float] = {}
        for source in self.SOURCE_WEIGHTS:
            source_sigs = [s for s in all_signals if s.source == source]
            weighted_count = sum(s.weight for s in source_sigs)
            source_counts[source] = weighted_count

            window = self._get_window(entity, source)
            window.push(weighted_count, ts)

        # --- 2. Per-source velocity ---
        source_velocities = {}
        for source, window in self._windows.get(entity, {}).items():
            source_velocities[source] = window.velocity

        # --- 3. Composite velocity (weighted sum) ---
        composite = sum(
            source_velocities.get(src, 0) * weight
            for src, weight in self.SOURCE_WEIGHTS.items()
        )

        # --- 4. Cross-domain amplification ---
        active_sources = sum(
            1 for v in source_velocities.values()
            if v >= self.CROSS_DOMAIN_THRESHOLD
        )
        if active_sources >= 3:
            composite *= self.CROSS_DOMAIN_MULTIPLIER
            logger.info("Cross-domain amplification: %d sources hot → score ×%.1f",
                        active_sources, self.CROSS_DOMAIN_MULTIPLIER)

        composite = round(min(composite, 10), 2)

        # --- 5. Trajectory history ---
        if entity not in self._composite_history:
            self._composite_history[entity] = []
        self._composite_history[entity].append(composite)
        if len(self._composite_history[entity]) > 20:
            self._composite_history[entity].pop(0)

        history = self._composite_history[entity]

        # --- 6. Trajectory slope (is it accelerating?) ---
        slope = self._compute_slope(history)

        # --- 7. Anomaly detection (z-score spike) ---
        anomaly = self._detect_anomaly(history)

        # --- 8. Sort top signals by weight ---
        top_signals = sorted(
            [s.to_dict() for s in (new_signals or all_signals)],
            key=lambda x: x["weight"],
            reverse=True,
        )[:8]

        # --- 9. LLM prediction (Claude Sonnet) ---
        prediction, confidence = await self._generate_prediction(
            entity=entity,
            composite=composite,
            slope=slope,
            source_velocities=source_velocities,
            top_signals=top_signals,
            anomaly=anomaly,
        )

        alert = (
            composite >= CONFIG.temporal.alert_threshold
            or anomaly
            or confidence >= 0.80
        )

        profile = TemporalProfile(
            entity=entity,
            timestamp=ts,
            velocity_score=composite,
            source_velocities=source_velocities,
            trajectory=history[-10:],
            trajectory_slope=slope,
            prediction=prediction,
            prediction_confidence=confidence,
            anomaly_detected=anomaly,
            top_signals=top_signals,
            alert=alert,
        )

        logger.info(
            "Temporal profile for '%s': score=%.1f slope=%.2f confidence=%.0f%% alert=%s",
            entity, composite, slope, confidence * 100, alert,
        )
        return profile

    # ------------------------------------------------------------------ #
    #  Prediction via Claude Sonnet                                        #
    # ------------------------------------------------------------------ #

    async def _generate_prediction(
        self,
        entity: str,
        composite: float,
        slope: float,
        source_velocities: dict,
        top_signals: list[dict],
        anomaly: bool,
    ) -> tuple[str, float]:
        """
        Ask Claude to synthesise the signals into a natural-language prediction
        with a probability estimate.
        
        Claude is given the velocity data and top signals — it acts as a
        senior analyst who has seen hundreds of similar patterns.
        """
        signals_summary = "\n".join(
            f"  [{s['source'].upper()}] {s['content'][:120]} (weight={s['weight']})"
            for s in top_signals[:6]
        )

        source_breakdown = "\n".join(
            f"  {src}: velocity={v:.1f}/10"
            for src, v in source_velocities.items()
        )

        prompt = f"""You are ARGUS Sentinel's predictive analysis engine.
        
Analyse the following temporal web intelligence data for the entity: **{entity}**

COMPOSITE VELOCITY SCORE: {composite:.1f}/10
TRAJECTORY SLOPE: {slope:+.3f} ({'accelerating' if slope > 0 else 'decelerating'})
ANOMALY DETECTED: {anomaly}
CROSS-DOMAIN VELOCITY BREAKDOWN:
{source_breakdown}

TOP SIGNALS (most recent collection):
{signals_summary}

Based on this data:
1. What is the MOST LIKELY major event or development for {entity} in the next 7-21 days?
2. What is the probability (0.0–1.0) that a significant announcement or development occurs?
3. Keep the prediction to 1-2 sentences, specific and actionable.

Respond ONLY with a JSON object:
{{"prediction": "...", "confidence": 0.XX, "timeframe_days": N, "event_category": "product|funding|partnership|regulatory|personnel|other"}}"""

        try:
            response = await self._model.generate_content_async(prompt)
            raw = response.text.strip()
            raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(raw)
            return parsed.get("prediction", "Insufficient signal for prediction."), \
                   float(parsed.get("confidence", 0.5))
        except Exception as e:
            logger.warning("Prediction LLM call failed: %s", e)
            # Fallback heuristic
            if composite >= 8:
                return f"High-velocity signal surge detected for {entity}. Likely major announcement imminent.", 0.78
            elif composite >= 5:
                return f"Elevated activity around {entity}. Monitor closely for developments.", 0.55
            else:
                return f"Baseline activity for {entity}. No imminent events detected.", 0.35

    # ------------------------------------------------------------------ #
    #  Math helpers                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _compute_slope(series: list[float]) -> float:
        if len(series) < 3:
            return 0.0
        n = len(series)
        xs = list(range(n))
        x_mean = statistics.mean(xs)
        y_mean = statistics.mean(series)
        numer = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, series))
        denom = sum((x - x_mean) ** 2 for x in xs) or 1e-9
        return numer / denom

    @staticmethod
    def _detect_anomaly(series: list[float], threshold: float = 2.5) -> bool:
        """Z-score anomaly: is the latest value a statistical outlier?"""
        if len(series) < 5:
            return False
        history = series[:-1]
        mean = statistics.mean(history)
        stdev = statistics.stdev(history) if len(history) >= 2 else 0
        if stdev < 0.001:
            return False
        z = (series[-1] - mean) / stdev
        return z > threshold
