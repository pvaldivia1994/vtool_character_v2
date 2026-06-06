"""
psychology — Motor psicológico runtime.

Síntesis runtime de psicología emergente para personajes.
Cada clase en su propio archivo.
"""

from .synthesizer import PsychologySynthesizer
from .emotional_dynamics import EmotionalDynamics
from .drift_detector import DriftDetector
from .belief_manager import BeliefManager
from .runtime_manager import RuntimeSoulManager
from .dna_adapter import dna_traits_to_genome

__all__ = [
    "PsychologySynthesizer",
    "EmotionalDynamics",
    "DriftDetector",
    "BeliefManager",
    "RuntimeSoulManager",
    "dna_traits_to_genome",
]
