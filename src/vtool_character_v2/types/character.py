"""
Tipos del Character System: DNA, estado, memoria y modificadores.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


# ======================================================================
# DNA (Inmutable)
# ======================================================================

@dataclass
class IdentityDNA:
    name: str = ""
    role: str = ""
    age: str = "Desconocida"
    background: str = ""
    scenario: str = "Una IA creada para ayudar."


@dataclass
class PersonalityDNA:
    traits: list[str] = field(default_factory=list)
    flaws: list[str] = field(default_factory=list)
    motivations: list[str] = field(default_factory=list)
    inner_conflict: str = ""
    emotional_triggers: list[str] = field(default_factory=list)


@dataclass
class SpeechDNA:
    style: str = ""
    verbosity: str = ""
    tone: str = ""
    emotions: list[str] = field(default_factory=list)
    speech_patterns: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)


@dataclass
class RulesDNA:
    core_rules: list[str] = field(default_factory=list)
    never_do: list[str] = field(default_factory=list)
    response_style: list[str] = field(default_factory=list)
    roleplay_mode: bool = False


# ======================================================================
# Memory
# ======================================================================

@dataclass
class MemoryEntry:
    id: str = ""
    content: str = ""
    priority: float = 0.5
    always_include: bool = False
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:8]


@dataclass
class ContextSummary:
    session_id: str = ""
    summary: str = ""
    summarized_message_count: int = 0
    summary_version: int = 1
    character_name: str = ""
    title: str = ""
    model_name: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class EpisodeSnapshot:
    episode_id: int | str = 0
    timestamp: str = ""
    summary: str = ""
    messages: list[dict] = field(default_factory=list)
    title: str = ""
    character_name: str = ""
    source: str = "legacy"  # "sqlite" | "legacy"

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


# ======================================================================
# State (Runtime Cache)
# ======================================================================

@dataclass
class RuntimeState:
    current_emotion: str = "neutral"
    active_context: str = ""
    version: int = 0


@dataclass
class RelationshipState:
    trust_level: float = 0.5
    familiarity: float = 0.0
    affective_memory: list[str] = field(default_factory=list)
    dynamics: list[str] = field(default_factory=list)
    version: int = 0


@dataclass
class PersonalityState:
    base_personality: str = ""
    emotional_signature: dict[str, str] = field(default_factory=lambda: {"default": "neutral"})
    user_model: dict[str, float] = field(default_factory=lambda: {"trust_level": 0.5})
    behavior_summary: str = ""
    memory_summary: str = ""
    tool_affinity: list[str] = field(default_factory=list)
    version: int = 0


# ======================================================================
# Mods
# ======================================================================

@dataclass
class CharacterMod:
    id: str = "mood_mod"
    target_layer: str = "speech"
    override_value: str = ""
    intensity: float = 1.0


# ======================================================================
# Load Result
# ======================================================================

@dataclass
class CharacterLoadResult:
    success: bool = True
    character_name: str = ""
    soul_active: bool = False
    psychology_active: bool = False
    logs: list[str] = field(default_factory=list)
    error: str = ""
