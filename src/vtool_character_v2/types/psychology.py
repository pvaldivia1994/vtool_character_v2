"""
Tipos de Psychology Engine v2 y Soul System: genome, identidad, psicología.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


# ======================================================================
# Genome
# ======================================================================

@dataclass
class Genome:
    sociability: float = 0.5
    emotional_sensitivity: float = 0.5
    impulsivity: float = 0.5
    risk_aversion: float = 0.5
    empathy: float = 0.5
    curiosity: float = 0.5
    security_need: float = 0.5
    independence: float = 0.5
    creativity: float = 0.5
    aggression: float = 0.5
    emotional_regulation: float = 0.5
    persistence: float = 0.5
    playfulness: float = 0.5


# ======================================================================
# CoreIdentity (identidad profunda)
# ======================================================================

@dataclass
class CoreIdentity:
    core_fears: list[str] = field(default_factory=list)
    core_desires: list[str] = field(default_factory=list)
    shame_sources: list[str] = field(default_factory=list)
    emotional_needs: dict[str, float] = field(default_factory=lambda: {
        "safety": 0.5, "belonging": 0.5, "esteem": 0.5,
        "autonomy": 0.5, "meaning": 0.5,
    })
    self_narrative: str = ""
    meaning_system: dict[str, float] = field(default_factory=lambda: {
        "people_are_good": 0.5, "world_is_fair": 0.5,
        "i_have_control": 0.5, "life_has_purpose": 0.5,
    })
    interpretation_biases: dict[str, float] = field(default_factory=lambda: {
        "internalize_blame": 0.5,
        "externalize_blame": 0.5,
        "catastrophize": 0.5,
        "minimize": 0.5,
        "personalize": 0.5,
        "mind_read_negative": 0.5,
    })
    self_beliefs: dict[str, float] = field(default_factory=lambda: {
        "i_am_lovable": 0.5,
        "i_am_capable": 0.5,
        "i_am_safe": 0.5,
        "i_belong": 0.5,
        "i_am_good": 0.5,
        "must_appear_confident": 0.5,
    })
    memory_loss_start_age: int = 0

    def to_prompt_block(self) -> str:
        parts = ["[CORE IDENTITY — Identidad profunda del personaje]"]

        if self.core_fears:
            parts.append(f"Miedos fundamentales: {', '.join(self.core_fears[:3])}")
        if self.core_desires:
            parts.append(f"Deseos fundamentales: {', '.join(self.core_desires[:3])}")
        if self.self_narrative:
            parts.append(f"Auto-narrativa: {self.self_narrative}")
        if self.shame_sources:
            parts.append(f"Fuentes de vergüenza: {', '.join(self.shame_sources[:2])}")

        active_beliefs = {k: v for k, v in self.self_beliefs.items() if v < 0.35}
        if active_beliefs:
            parts.append("Creencias sobre sí mismo:")
            for k, v in active_beliefs.items():
                label = k.replace("_", " ").capitalize()
                parts.append(f"- {label}: Baja ({v:.2f})")

        return "\n".join(parts)

    def derive_contradictions(self) -> list[str]:
        conflicts = []

        if any("connection" in d.lower() or "love" in d.lower() or "belong" in d.lower() for d in self.core_desires):
            if any("abandonment" in f.lower() or "betrayal" in f.lower() or "hurt" in f.lower() for f in self.core_fears):
                conflicts.append("Wants intimacy but fears being hurt")

        if any("freedom" in d.lower() or "independence" in d.lower() or "autonomy" in d.lower() for d in self.core_desires):
            if any("instability" in f.lower() or "uncertainty" in f.lower() or "insecurity" in f.lower() for f in self.core_fears):
                conflicts.append("Craves freedom yet craves safety")

        if (self.self_beliefs.get("i_am_lovable", 0.5) < 0.35 or self.self_beliefs.get("i_am_capable", 0.5) < 0.35) and self.self_beliefs.get("must_appear_confident", 0.5) > 0.65:
            conflicts.append("Feels inadequate but forces themselves to appear confident and strong")

        elif self.self_beliefs.get("i_am_capable", 0.5) < 0.35 and self.self_beliefs.get("i_am_lovable", 0.5) < 0.35:
            if self.self_narrative and ("must" in self.self_narrative.lower() or "should" in self.self_narrative.lower()):
                conflicts.append("Feels inadequate but forces themselves to appear confident")

        if self.shame_sources:
            if any("humiliation" in d.lower() or "recognition" in d.lower() or "seen" in d.lower() for d in self.core_desires):
                conflicts.append("Wants to be seen yet fears being exposed")

        if self.meaning_system.get("i_have_control", 0.5) < 0.3 and self.interpretation_biases.get("catastrophize", 0.5) > 0.6:
            conflicts.append("Desperately needs control but expects disaster")

        return conflicts[:5]

    def interpret_event(self, event_type: str, description: str, importance: float) -> dict:
        severity = importance
        if self.interpretation_biases.get("catastrophize", 0.5) > 0.6:
            severity = min(1.0, severity * (1 + self.interpretation_biases["catastrophize"] * 0.3))
        if self.interpretation_biases.get("minimize", 0.5) > 0.6:
            severity = max(0.0, severity * (1 - self.interpretation_biases["minimize"] * 0.3))

        if self.interpretation_biases.get("internalize_blame", 0.5) > 0.6 and importance > 0.5:
            attribution = "self"
        elif self.interpretation_biases.get("externalize_blame", 0.5) > 0.6 and importance > 0.5:
            attribution = "others"
        else:
            attribution = "situation"

        if self.interpretation_biases.get("personalize", 0.5) > 0.6:
            attribution = "self" if importance > 0.4 else attribution

        emotion = self._derive_emotion(event_type, severity, attribution)

        return {
            "perceived_severity": severity,
            "attribution": attribution,
            "emotion": emotion,
            "belief_impact": {
                k: -severity * 0.1 for k in self.self_beliefs
                if attribution == "self" and severity > 0.5
            },
        }

    def _derive_emotion(self, event_type: str, severity: float, attribution: str) -> str:
        if attribution == "self" and severity > 0.6:
            return "shame"
        if attribution == "self" and severity > 0.3:
            return "guilt"
        if attribution == "others" and severity > 0.5:
            return "anger"
        if event_type in ("loss", "death") and severity > 0.4:
            return "grief"
        if severity > 0.7:
            return "fear"
        if severity > 0.4:
            return "sadness"
        return "neutral"


# ======================================================================
# Soul / Psychology types
# ======================================================================

@dataclass
class TurningPoint:
    age: int = 0
    event: str = ""
    intensity: float = 0.0
    positive: bool = True
    changed_traits: dict[str, float] = field(default_factory=dict)
    emotional_memory: str = ""
    meaning_assigned: str = ""


@dataclass
class EmotionalMemory:
    id: str = ""
    original_event: str = ""
    remembered_version: str = ""
    emotional_weight: float = 0.5
    confidence: float = 0.8
    distortion_level: float = 0.0
    event_month: int = 0
    last_recalled: str = ""

    def recall(self, current_month: int) -> str:
        months_since = current_month - self.event_month
        if months_since > 120:
            self.distortion_level = min(1.0, self.distortion_level + 0.05 * (months_since / 120))
        elif months_since > 60:
            self.distortion_level = min(1.0, self.distortion_level + 0.03 * (months_since / 60))

        if self.distortion_level > 0.5:
            return self.remembered_version
        return self.original_event


@dataclass
class SoulEvent:
    id: str = ""
    month: int = 0
    event_type: str = "unknown"
    description: str = ""
    importance: float = 0.5
    emotion: str = "neutral"
    people_involved: list[str] = field(default_factory=list)
    location: str = ""
    stage: str = ""
    psychological_impact: dict[str, float] = field(default_factory=dict)
    belief_formed: str = ""
    reflection: str = ""
    coping_strategy: str = ""

    def __post_init__(self):
        if not self.id:
            import uuid
            self.id = uuid.uuid4().hex[:12]


@dataclass
class BeliefEntry:
    id: str = ""
    content: str = ""
    source_event_id: str = ""
    strength: float = 0.5
    category: str = "general"
    formed_at_month: int = 0
    last_reinforced: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:8]


@dataclass
class PsychologyState:
    current_big_five: dict[str, float] = field(default_factory=lambda: {
        "openness": 0.5, "conscientiousness": 0.5,
        "extraversion": 0.5, "agreeableness": 0.5,
        "neuroticism": 0.5,
    })
    attachment_style: str = "secure"
    needs: dict[str, float] = field(default_factory=lambda: {
        "safety": 0.5, "belonging": 0.5, "esteem": 0.5,
        "autonomy": 0.5, "meaning": 0.5,
    })
    active_wounds: list[str] = field(default_factory=list)
    active_coping: list[str] = field(default_factory=list)
    active_conflicts: list[str] = field(default_factory=list)
    active_biases: list[str] = field(default_factory=list)
    worldview: dict[str, float] = field(default_factory=lambda: {
        "optimism": 0.5, "trust_in_people": 0.5,
        "sense_of_control": 0.5, "meaningfulness": 0.5,
    })
    version: int = 0


@dataclass
class EmotionalState:
    valence: float = 0.0
    arousal: float = 0.0
    dominant_emotion: str = "neutral"
    secondary_emotions: dict[str, float] = field(default_factory=dict)
    last_update: str = ""
    emotional_inertia: float = 0.3


@dataclass
class PersonaState:
    speech_style: str = "neutral"
    verbosity: float = 0.5
    sarcasm_tendency: float = 0.3
    warmth: float = 0.5
    defensiveness: float = 0.3
    uses_actions: bool = True
    self_disclosure: float = 0.5
    humor_style: str = "none"
    humor_frequency: float = 0.3
    emotional_distance: float = 0.5
    _synthesized_at: str = ""


@dataclass
class DriftEntry:
    timestamp: str = ""
    axis: str = ""
    old_value: float = 0.5
    new_value: float = 0.5
    reason: str = ""
    source: str = ""
