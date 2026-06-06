"""psychology_init.py — Inicialización de Soul Accessor y Psychology Engine v2."""

from __future__ import annotations

import json
from typing import Any

from .base import CharacterManager
from ..types import CoreIdentity, Genome


def _init_soul_accessor(self: CharacterManager) -> None:
    if not self._char_dir:
        self._soul_accessor = None
        return

    from ..soul import RuntimeSoulAccessor, SoulGenerator

    dummy_gen = SoulGenerator(
        character_manager=self,
        config=None,
        llm_client=None,
        log_debug_fn=self._logger_fn,
    )
    accessor = RuntimeSoulAccessor(
        char_dir=self._char_dir,
        soul_generator=dummy_gen,
        log_debug_fn=self._logger_fn,
    )
    soul_active = accessor.initialize()
    if soul_active:
        self._soul_accessor = accessor
        self._log("SOUL", "Soul System activado para este personaje.")
    else:
        self._soul_accessor = None

    self._init_psychology_engine()

CharacterManager._init_soul_accessor = _init_soul_accessor


def _init_psychology_engine(self: CharacterManager) -> None:
    if not self._char_dir:
        return

    genome_path = self._char_dir / "genome.json"
    if genome_path.exists():
        try:
            with open(genome_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._genome = Genome(**data)
            self._log("SOUL", "Genome cargado desde genome.json")
        except Exception as e:
            self._log("SOUL", f"Error cargando genome.json: {e}")
            self._genome = None

    if self._genome is None:
        from ..psychology import dna_traits_to_genome
        self._genome = dna_traits_to_genome(self.personality_dna)
        self._log("SOUL", "Genome derivado desde PersonalityDNA (backward compat)")

    self._load_core_identity()

    if self._genome:
        from ..psychology import PsychologySynthesizer, RuntimeSoulManager

        synthesizer = PsychologySynthesizer(
            log_debug_fn=lambda t, m: self._logger_fn(t, m) if self._logger_fn else None,
            log_info_fn=lambda m: self._logger_fn("PSY", m) if self._logger_fn else None,
        )
        try:
            self._psychology_manager = RuntimeSoulManager(
                char_dir=self._char_dir,
                genome=self._genome,
                synthesizer=synthesizer,
                log_debug_fn=lambda t, m: self._logger_fn(t, m) if self._logger_fn else None,
                log_info_fn=lambda m: self._logger_fn("PSY", m) if self._logger_fn else None,
            )
            self._psychology_manager._core_identity = self._core_identity
            self._psychology_manager.load()
            self._psychology_manager.synthesize_psychology()
            self._psychology_manager.synthesize_persona()
            self._log("PSY", "Psychology Engine v2 inicializado")
        except Exception as e:
            self._log("PSY", f"Error inicializando Psychology Engine: {e}")
            self._psychology_manager = None

CharacterManager._init_psychology_engine = _init_psychology_engine


def _load_core_identity(self: CharacterManager) -> None:
    if not self._char_dir:
        return

    ci_path = self._char_dir / "psychology" / "core_identity.json"
    if ci_path.exists():
        try:
            with open(ci_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._core_identity = CoreIdentity(**data)
            self._log("PSY", "CoreIdentity cargado desde disco")
            return
        except Exception as e:
            self._log("PSY", f"Error cargando CoreIdentity: {e}")

    self._core_identity = self._derive_core_identity_from_genome()

CharacterManager._load_core_identity = _load_core_identity


def _derive_core_identity_from_genome(self: CharacterManager) -> Any:
    from ..types import CoreIdentity
    ci = CoreIdentity()

    if not self._genome:
        return ci

    if self._genome.risk_aversion > 0.6:
        ci.core_fears.append("uncertainty")
    if self._genome.emotional_sensitivity > 0.7:
        ci.core_fears.append("being overwhelmed")
    if self._genome.security_need > 0.7:
        ci.core_fears.append("instability")

    if self._genome.sociability > 0.6:
        ci.core_desires.append("connection")
    if self._genome.curiosity > 0.6:
        ci.core_desires.append("understanding")
    if self._genome.independence > 0.6:
        ci.core_desires.append("freedom")
    if self._genome.creativity > 0.6:
        ci.core_desires.append("expression")

    if self._genome.emotional_sensitivity > 0.7:
        ci.interpretation_biases["catastrophize"] = min(1.0, 0.5 + self._genome.emotional_sensitivity * 0.3)
    if self._genome.aggression > 0.6:
        ci.interpretation_biases["externalize_blame"] = min(1.0, 0.5 + self._genome.aggression * 0.3)
    if self._genome.emotional_sensitivity > 0.6 and self._genome.independence < 0.4:
        ci.interpretation_biases["internalize_blame"] = min(1.0, 0.5 + (1 - self._genome.independence) * 0.3)

    return ci

CharacterManager._derive_core_identity_from_genome = _derive_core_identity_from_genome


def save_psychology_state(self: CharacterManager) -> None:
    if self._psychology_manager:
        try:
            self._psychology_manager.save()
        except Exception as e:
            self._log("PSY", f"Error guardando psychology state: {e}")

    if self._core_identity and self._char_dir:
        from ..types import CoreIdentity
        if isinstance(self._core_identity, CoreIdentity):
            try:
                (self._char_dir / "psychology").mkdir(parents=True, exist_ok=True)
                with open(self._char_dir / "psychology" / "core_identity.json", "w", encoding="utf-8") as f:
                    import json
                    json.dump(self._core_identity.__dict__, f, ensure_ascii=False, indent=2)
            except Exception as e:
                self._log("PSY", f"Error guardando CoreIdentity: {e}")

CharacterManager.save_psychology_state = save_psychology_state
