"""belief_manager.py — BeliefManager: formación, refuerzo y decaimiento de creencias."""

from __future__ import annotations

from typing import Callable, Optional

from ..types import BeliefEntry


class BeliefManager:
    def __init__(self, log_fn: Optional[Callable] = None):
        self._log = log_fn or (lambda msg: None)

    def form_belief(
        self,
        content: str,
        source_event_id: str = "",
        category: str = "general",
        strength: float = 0.5,
        month: int = 0,
    ) -> BeliefEntry:
        return BeliefEntry(
            content=content,
            source_event_id=source_event_id,
            strength=strength,
            category=category,
            formed_at_month=month,
        )

    def reinforce(self, belief: BeliefEntry, amount: float = 0.1) -> BeliefEntry:
        belief.strength = max(0.05, min(1.0, belief.strength + amount))
        return belief

    def weaken(self, belief: BeliefEntry, amount: float = 0.1) -> BeliefEntry:
        belief.strength = max(0.05, min(1.0, belief.strength - amount))
        if belief.strength < 0.1:
            belief.content = f"(weakened) {belief.content}"
        return belief

    def decay_all(self, beliefs: list[BeliefEntry], factor: float = 0.02) -> list[BeliefEntry]:
        for b in beliefs:
            b.strength = max(0.05, b.strength - factor)
        return [b for b in beliefs if b.strength > 0.05]
