"""
ARGUS Sentinel — Base Agent
All agents inherit from this. Defines the contract:
  - collect() → raw signals
  - normalise() → ArgusSignal list
  - snapshot history management
"""

import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from bright_data_client import BrightDataClient

logger = logging.getLogger("argus.agent")


@dataclass
class ArgusSignal:
    """A single intelligence signal from any source."""
    source: str           # "news" | "finance" | "site" | "social"
    signal_type: str      # "mention" | "sentiment" | "change" | "filing" | "hiring"
    entity: str           # e.g. "OpenAI" — who/what this is about
    content: str          # brief description of the signal
    url: str              # source URL
    timestamp: float      # Unix timestamp
    weight: float = 1.0   # 0–1 importance weighting
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "signal_type": self.signal_type,
            "entity": self.entity,
            "content": self.content,
            "url": self.url,
            "timestamp": self.timestamp,
            "weight": self.weight,
            "metadata": self.metadata,
        }

    def fingerprint(self) -> str:
        """Content hash for deduplication."""
        return hashlib.md5(
            f"{self.source}:{self.url}:{self.content[:80]}".encode()
        ).hexdigest()


@dataclass
class AgentSnapshot:
    """
    One round of collection from an agent.
    Stored in history to compute velocity (delta between snapshots).
    """
    agent_name: str
    entity: str
    timestamp: float
    signals: list[ArgusSignal]
    signal_count: int = 0
    fingerprints: set = field(default_factory=set)

    def __post_init__(self):
        self.signal_count = len(self.signals)
        self.fingerprints = {s.fingerprint() for s in self.signals}


class BaseAgent(ABC):
    """
    Abstract base for all ARGUS agents.
    
    Subclasses implement:
      - async collect(entity, query) → list[ArgusSignal]
    
    BaseAgent provides:
      - Snapshot history (for velocity calculation)
      - New-signal detection (delta vs last snapshot)
      - Logging, error handling
    """

    name: str = "base"
    source: str = "unknown"

    def __init__(self, client: BrightDataClient):
        self.client = client
        self._history: dict[str, list[AgentSnapshot]] = {}  # entity → snapshots
        self._seen_fingerprints: dict[str, set] = {}        # entity → seen set

    @abstractmethod
    async def collect(self, entity: str, query: str) -> list[ArgusSignal]:
        """
        Collect signals for the given entity and search query.
        Returns a flat list of ArgusSignal objects.
        """

    async def run_and_snapshot(
        self, entity: str, query: str
    ) -> tuple[list[ArgusSignal], list[ArgusSignal]]:
        """
        Run collect(), snapshot the result, return:
          (all_signals, new_signals_since_last_snapshot)
        """
        t0 = time.time()
        try:
            signals = await self.collect(entity, query)
        except Exception as e:
            logger.error("%s agent failed for '%s': %s", self.name, entity, e)
            signals = []

        elapsed = time.time() - t0
        logger.info("%s collected %d signals for '%s' in %.1fs",
                    self.name, len(signals), entity, elapsed)

        snapshot = AgentSnapshot(
            agent_name=self.name,
            entity=entity,
            timestamp=time.time(),
            signals=signals,
        )

        if entity not in self._history:
            self._history[entity] = []
            self._seen_fingerprints[entity] = set()

        # New signals = those whose fingerprint wasn't seen before
        new_signals = [
            s for s in signals
            if s.fingerprint() not in self._seen_fingerprints[entity]
        ]
        self._seen_fingerprints[entity].update(snapshot.fingerprints)

        # Keep last 10 snapshots per entity
        self._history[entity].append(snapshot)
        if len(self._history[entity]) > 10:
            self._history[entity].pop(0)

        return signals, new_signals

    def get_snapshot_series(self, entity: str) -> list[AgentSnapshot]:
        """Return historical snapshots for velocity computation."""
        return self._history.get(entity, [])

    def last_snapshot(self, entity: str) -> Optional[AgentSnapshot]:
        history = self._history.get(entity, [])
        return history[-1] if history else None
