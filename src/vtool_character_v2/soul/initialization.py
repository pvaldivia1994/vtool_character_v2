"""initialization.py — Fase 1: Inicialización del alma desde DNA/Genome."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .soul_generator import SoulGenerator, _SoulState
from ..types import Genome


def _init_soul_state(
    self: SoulGenerator,
    identity, personality, speech, rules,
    age_months: int,
    genome: Optional[Genome] = None,
) -> _SoulState:
    state = _SoulState(age_months=age_months)

    core_id = getattr(self._cm, "_core_identity", None)
    if core_id:
        state.memory_loss_start_age = getattr(core_id, "memory_loss_start_age", 0)
    else:
        state.memory_loss_start_age = getattr(identity, "memory_loss_start_age", 0)

    if genome is not None:
        if isinstance(genome, dict):
            genome = Genome(**genome)
    else:
        from ..psychology import dna_traits_to_genome
        genome = dna_traits_to_genome(personality)

    from ..psychology import PsychologySynthesizer
    ps_synth = PsychologySynthesizer()
    trait_dict = ps_synth._genome_to_big_five(genome)
    state.core_traits = trait_dict

    state.worldview["optimism"] = 0.3 + genome.playfulness * 0.4
    state.worldview["individualism"] = genome.independence
    state.worldview["morality"] = genome.empathy * 0.5 + (1.0 - genome.aggression) * 0.5

    state.mental_state = {
        "happiness": 0.5 + (genome.playfulness - 0.5) * 0.3,
        "anxiety": 0.5 - (genome.emotional_regulation - 0.5) * 0.3,
        "trust": genome.empathy * 0.6 + (1.0 - genome.aggression) * 0.2,
        "self_esteem": genome.persistence * 0.4 + (1.0 - genome.emotional_sensitivity) * 0.3,
        "resilience": genome.emotional_regulation * 0.5 + genome.persistence * 0.3,
    }

    for m in personality.motivations:
        state.values.append(m)

    for f in personality.flaws:
        lower = f.lower()
        if "miedo" in lower or "temor" in lower or "fear" in lower:
            state.fears.append(f)
    if genome.risk_aversion > 0.7:
        state.fears.append("innate caution")

    return state

SoulGenerator._init_soul_state = _init_soul_state


def _load_genome(self: SoulGenerator, char_dir: Path, personality) -> Genome:
    genome_path = char_dir / "genome.json"
    if genome_path.exists():
        try:
            with open(genome_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._log_info(f"Genome cargado desde {genome_path}")
            return Genome(**data)
        except Exception as e:
            self._log_warning(f"Error cargando genome.json: {e}")

    from ..psychology import dna_traits_to_genome
    genome = dna_traits_to_genome(personality)
    self._log_info("Genome derivado desde PersonalityDNA (backward compat)")
    return genome

SoulGenerator._load_genome = _load_genome
