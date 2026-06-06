"""
vtool_character_v2 — Character System para vtool_llama.

Maneja la arquitectura completa de personajes:
  - CharacterManager (DNA, memoria, estado, mods)
  - CharacterCompiler (compilación de system prompts)
  - Soul System (vida simulada persistente)
  - Psychology Engine (psicología runtime)

Depende de vtool_llama_v2 para inferencia LLM.

Uso básico:
    from vtool_character_v2 import CharacterManager, CharacterCompiler
    from vtool_character_v2.soul import SoulGenerator
    from vtool_character_v2.psychology import PsychologySynthesizer
"""

from __future__ import annotations

from .character import CharacterManager
from .compiler import CharacterCompiler
from .exceptions import (
    LoadCancelledError,
    VToolCharacterV2Error,
)
from .types import (
    ConfigSchema,
    CharacterLoadResult,
    CharacterMod,
    EpisodeSnapshot,
    IdentityDNA,
    MemoryEntry,
    PersonalityDNA,
    PersonalityState,
    RelationshipState,
    RulesDNA,
    RuntimeState,
    SpeechDNA,
    # Psychology types
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

__version__ = "0.1.0"

__all__ = [
    "CharacterManager",
    "ConfigSchema",
    "CharacterCompiler",
    "LoadCancelledError",
    "VToolCharacterV2Error",
    "CharacterLoadResult", "CharacterMod", "EpisodeSnapshot",
    "IdentityDNA", "MemoryEntry", "PersonalityDNA", "PersonalityState",
    "RelationshipState", "RulesDNA", "RuntimeState", "SpeechDNA",
    "BeliefEntry", "CoreIdentity", "DriftEntry", "EmotionalMemory",
    "EmotionalState", "Genome", "PersonaState", "PsychologyState",
    "SoulEvent", "TurningPoint",
    "__version__",
]
