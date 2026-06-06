"""emotional_dynamics.py — Sistema emocional multi-eje con decaimiento, inercia y triggers."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Callable, Optional

from ..types import EmotionalState


class EmotionalDynamics:
    EMOTION_MAP: dict[str, tuple[float, float]] = {
        "joy": (0.8, 0.6), "excitement": (0.6, 0.8),
        "contentment": (0.6, -0.3), "serenity": (0.4, -0.7),
        "hope": (0.5, 0.3), "pride": (0.6, 0.4),
        "love": (0.9, 0.5), "gratitude": (0.7, -0.1),
        "sadness": (-0.7, -0.4), "grief": (-0.9, -0.5),
        "melancholy": (-0.4, -0.6), "nostalgia": (0.1, -0.3),
        "anger": (-0.7, 0.8), "frustration": (-0.5, 0.6),
        "rage": (-0.9, 0.9), "annoyance": (-0.3, 0.4),
        "fear": (-0.6, 0.8), "anxiety": (-0.4, 0.6),
        "terror": (-0.9, 0.9), "worry": (-0.3, 0.4),
        "surprise": (0.1, 0.8), "shock": (-0.3, 0.9),
        "disgust": (-0.6, 0.3), "contempt": (-0.5, 0.2),
        "guilt": (-0.5, -0.2), "shame": (-0.7, -0.3),
        "trust": (0.5, -0.2), "acceptance": (0.4, -0.4),
        "anticipation": (0.2, 0.6), "interest": (0.4, 0.5),
        "boredom": (-0.3, -0.6), "apathy": (-0.2, -0.7),
        "neutral": (0.0, 0.0),
    }

    DECAY_RATE: float = 0.15
    SECONDARY_DECAY: float = 0.10
    INERTIA_MIN: float = 0.1
    INERTIA_MAX: float = 0.8

    def __init__(
        self,
        inertia: float = 0.3,
        log_fn: Optional[Callable] = None,
    ):
        self._inertia = max(self.INERTIA_MIN, min(self.INERTIA_MAX, inertia))
        self._log = log_fn or (lambda msg: None)

    def create_default(self) -> EmotionalState:
        now = datetime.now(timezone.utc).isoformat()
        return EmotionalState(
            valence=0.0,
            arousal=0.0,
            dominant_emotion="neutral",
            secondary_emotions={},
            last_update=now,
            emotional_inertia=self._inertia,
        )

    def decay(self, state: EmotionalState) -> EmotionalState:
        if not state.last_update:
            return state

        try:
            last = datetime.fromisoformat(state.last_update)
            now = datetime.now(timezone.utc)
            delta_hours = (now - last).total_seconds() / 3600.0
        except (ValueError, TypeError):
            delta_hours = 0.0

        if delta_hours <= 0:
            return state

        decay_factor = math.exp(-self.DECAY_RATE * delta_hours)

        new_valence = state.valence * decay_factor
        new_arousal = state.arousal * decay_factor

        new_secondary = {}
        for k, v in state.secondary_emotions.items():
            new_v = v * math.exp(-self.SECONDARY_DECAY * delta_hours)
            if abs(new_v) > 0.05:
                new_secondary[k] = new_v

        if abs(new_valence) < 0.1 and abs(new_arousal) < 0.1:
            dominant = "neutral"
        else:
            dominant = self._valence_arousal_to_emotion(new_valence, new_arousal)

        state.valence = new_valence
        state.arousal = new_arousal
        state.dominant_emotion = dominant
        state.secondary_emotions = new_secondary
        state.last_update = datetime.now(timezone.utc).isoformat()

        return state

    def apply_trigger(
        self,
        state: EmotionalState,
        target_valence: float,
        target_arousal: float,
        trigger_emotion: Optional[str] = None,
    ) -> EmotionalState:
        inertia = state.emotional_inertia

        if inertia > 0:
            delta_v = target_valence - state.valence
            delta_a = target_arousal - state.arousal
            new_valence = state.valence + delta_v * (1 - inertia)
            new_arousal = state.arousal + delta_a * (1 - inertia)
        else:
            new_valence = target_valence
            new_arousal = target_arousal

        new_valence = max(-1.0, min(1.0, new_valence))
        new_arousal = max(-1.0, min(1.0, new_arousal))

        if trigger_emotion and trigger_emotion in self.EMOTION_MAP:
            dominant = trigger_emotion
        else:
            dominant = self._valence_arousal_to_emotion(new_valence, new_arousal)

        new_secondary = dict(state.secondary_emotions)
        if trigger_emotion and trigger_emotion != dominant:
            current = new_secondary.get(trigger_emotion, 0.0)
            coord = self.EMOTION_MAP.get(trigger_emotion, (0, 0))
            dist = math.sqrt(
                (coord[0] - new_valence) ** 2 +
                (coord[1] - new_arousal) ** 2
            )
            intensity = max(0.0, 1.0 - dist)
            new_secondary[trigger_emotion] = max(current, intensity * 0.5)

        state.valence = new_valence
        state.arousal = new_arousal
        state.dominant_emotion = dominant
        state.secondary_emotions = new_secondary
        state.last_update = datetime.now(timezone.utc).isoformat()

        return state

    def apply_text_trigger(
        self,
        state: EmotionalState,
        text: str,
    ) -> EmotionalState:
        lower = text.lower()

        positive_words = [
            "gracias", "te quiero", "te amo", "feliz", "hermoso",
            "maravilloso", "genial", "excelente", "bien", "alegre",
            "love", "happy", "wonderful", "great", "amazing",
            "thank", "beautiful", "cute", "adorable", "nice",
        ]
        negative_words = [
            "odio", "detesto", "triste", "enojado", "furioso",
            "horrible", "terrible", "miedo", "asustado", "pésimo",
            "hate", "angry", "sad", "terrible", "horrible",
            "afraid", "scared", "upset", "furious", "awful",
        ]
        loss_words = [
            "murió", "perdi", "terminó", "adios", "nunca más",
            "dead", "die", "lost", "gone", "forever", "never",
        ]
        aggressive_words = [
            "callate", "idiota", "estúpido", "imbécil", "vete",
            "shut up", "stupid", "idiot", "leave", "go away",
        ]

        positive_count = sum(1 for w in positive_words if w in lower)
        negative_count = sum(1 for w in negative_words if w in lower)
        loss_count = sum(1 for w in loss_words if w in lower)
        aggressive_count = sum(1 for w in aggressive_words if w in lower)

        if aggressive_count >= 2:
            target_v = -0.6
            target_a = 0.7
            trigger = "anger"
        elif loss_count >= 1:
            target_v = -0.7
            target_a = -0.3
            trigger = "sadness"
        elif negative_count > positive_count:
            intensity = min(1.0, negative_count * 0.15)
            target_v = -0.3 * intensity
            target_a = 0.2 * intensity
            trigger = "sadness" if negative_count > 3 else "anxiety"
        elif positive_count > negative_count:
            intensity = min(1.0, positive_count * 0.12)
            target_v = 0.4 * intensity
            target_a = 0.1 * intensity
            trigger = "joy" if positive_count > 3 else "contentment"
        else:
            return state

        return self.apply_trigger(state, target_v, target_a, trigger)

    def _valence_arousal_to_emotion(self, v: float, a: float) -> str:
        best = "neutral"
        best_dist = float("inf")
        for emotion, (ev, ea) in self.EMOTION_MAP.items():
            dist = math.sqrt((v - ev) ** 2 + (a - ea) ** 2)
            if dist < best_dist:
                best_dist = dist
                best = emotion
        return best
