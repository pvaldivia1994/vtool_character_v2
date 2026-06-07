"""
types — Subpackage con las dataclasses del Character System.
"""

from .config import ConfigSchema
from .character import (
    CharacterLoadResult,
    CharacterMod,
    EpisodeSnapshot,
    ContextSummary,
    IdentityDNA,
    MemoryEntry,
    PersonalityDNA,
    PersonalityState,
    RelationshipState,
    RulesDNA,
    RuntimeState,
    SpeechDNA,
)
from .psychology import (
    BeliefEntry,
    CoreIdentity,
    DriftEntry,
    EmotionalMemory,
    EmotionalState,
    Genome,
    PersonaState,
    PsychologyState,
    SoulEvent,
    TurningPoint,
)

__all__ = [
    "ConfigSchema",
    "CharacterLoadResult", "CharacterMod", "ContextSummary", "EpisodeSnapshot",
    "IdentityDNA", "MemoryEntry", "PersonalityDNA", "PersonalityState",
    "RelationshipState", "RulesDNA", "RuntimeState", "SpeechDNA",
    "BeliefEntry", "CoreIdentity", "DriftEntry", "EmotionalMemory",
    "EmotionalState", "Genome", "PersonaState", "PsychologyState",
    "SoulEvent", "TurningPoint",
]
