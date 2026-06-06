"""runtime_manager.py — RuntimeSoulManager: evolución del alma en tiempo de conversación."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Optional

from ..types import BeliefEntry, EmotionalState, Genome, PersonaState, PsychologyState

from .synthesizer import PsychologySynthesizer


class RuntimeSoulManager:
    def __init__(
        self,
        char_dir: Path,
        genome: Genome,
        synthesizer: PsychologySynthesizer,
        log_debug_fn: Optional[Callable] = None,
        log_info_fn: Optional[Callable] = None,
    ):
        self._char_dir = char_dir
        self._genome = genome
        self._synth = synthesizer
        self._log_debug = log_debug_fn or (lambda t, m: None)
        self._log_info = log_info_fn or (lambda m: None)

        self._soul_events: list[dict] = []
        self._beliefs: list[BeliefEntry] = []
        self._psychology: Optional[PsychologyState] = None
        self._persona: Optional[PersonaState] = None
        self._emotional: Optional[EmotionalState] = None
        self._core_identity: Optional[Any] = None
        self._turning_points: list[Any] = []
        self._emotional_memories: list[Any] = []
        self._version: int = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def psychology(self) -> Optional[PsychologyState]:
        return self._psychology

    @property
    def persona(self) -> Optional[PersonaState]:
        return self._persona

    @property
    def emotional(self) -> Optional[EmotionalState]:
        return self._emotional

    @property
    def genome(self) -> Genome:
        return self._genome

    @property
    def is_loaded(self) -> bool:
        return self._psychology is not None

    @property
    def active(self) -> bool:
        return self._psychology is not None and self._persona is not None

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def load(self) -> None:
        soul_path = self._char_dir / "soul" / "soul.json"
        psych_path = self._char_dir / "psychology" / "current_state.json"
        beliefs_path = self._char_dir / "soul" / "beliefs.json"
        emotional_path = self._char_dir / "psychology" / "emotional_state.json"

        if soul_path.exists():
            try:
                with open(soul_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._soul_events = data.get("events", [])
                self._log_debug("SOUL", f"Loaded {len(self._soul_events)} soul events")
            except Exception as e:
                self._log_debug("SOUL", f"Error loading soul: {e}")

        if beliefs_path.exists():
            try:
                with open(beliefs_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._beliefs = [BeliefEntry(**b) for b in data.get("beliefs", [])]
                self._log_debug("SOUL", f"Loaded {len(self._beliefs)} beliefs")
            except Exception as e:
                self._log_debug("SOUL", f"Error loading beliefs: {e}")

        if psych_path.exists():
            try:
                with open(psych_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._psychology = PsychologyState(**data)
            except Exception:
                self._psychology = None

        if emotional_path.exists():
            try:
                with open(emotional_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._emotional = EmotionalState(**data)
            except Exception:
                self._emotional = None

    def save(self) -> None:
        (self._char_dir / "soul").mkdir(parents=True, exist_ok=True)
        (self._char_dir / "psychology").mkdir(parents=True, exist_ok=True)

        beliefs_data = {
            "beliefs": [asdict(b) for b in self._beliefs],
            "version": self._version,
        }
        with open(self._char_dir / "soul" / "beliefs.json", "w", encoding="utf-8") as f:
            json.dump(beliefs_data, f, ensure_ascii=False, indent=2)

        if self._psychology:
            with open(self._char_dir / "psychology" / "current_state.json", "w", encoding="utf-8") as f:
                json.dump(asdict(self._psychology), f, ensure_ascii=False, indent=2)

        if self._emotional:
            with open(self._char_dir / "psychology" / "emotional_state.json", "w", encoding="utf-8") as f:
                json.dump(asdict(self._emotional), f, ensure_ascii=False, indent=2)

        self._log_debug("SOUL", "Runtime soul state saved")

    # ------------------------------------------------------------------
    # Psychology synthesis
    # ------------------------------------------------------------------

    def synthesize_psychology(self) -> PsychologyState:
        self._psychology = self._synth.synthesize(
            genome=self._genome,
            soul_events=self._soul_events,
            beliefs=self._beliefs,
        )
        self._version += 1
        return self._psychology

    def synthesize_persona(self) -> PersonaState:
        if not self._psychology:
            self.synthesize_psychology()
        if not self._emotional:
            self._emotional = self._synth.emotion.create_default()

        self._emotional = self._synth.emotion.decay(self._emotional)

        self._persona = self._synth.compile_persona(
            psychology=self._psychology,
            emotional=self._emotional,
            genome=self._genome,
        )
        return self._persona

    def tick(self, recent_interactions: list[dict]) -> None:
        if self._psychology:
            self._psychology = self._synth.tick(
                current=self._psychology,
                genome=self._genome,
                recent_interactions=recent_interactions,
                beliefs=self._beliefs,
            )
        self._version += 1

    # ------------------------------------------------------------------
    # Runtime evolution
    # ------------------------------------------------------------------

    def add_runtime_event(self, event: dict) -> dict:
        event["id"] = f"runtime_{len(self._soul_events)}_{event.get('month', 0)}"
        self._soul_events.append(event)

        result = {"event_id": event["id"]}

        if self._psychology:
            proc_result = self._synth.process_event(
                current=self._psychology,
                event=event,
                genome=self._genome,
                core_identity=self._core_identity,
                beliefs=self._beliefs,
            )
            self._psychology = proc_result["psychology"]

            belief_added = proc_result.get("belief_added")
            if belief_added:
                self._beliefs.append(belief_added)
                result["belief_added"] = belief_added.content

            if proc_result.get("emotion_trigger"):
                emo = proc_result["emotion_trigger"]
                emotion_coords = self._synth.emotion.EMOTION_MAP.get(emo, (0, 0))
                if self._emotional:
                    self._emotional = self._synth.emotion.apply_trigger(
                        self._emotional, emotion_coords[0], emotion_coords[1], emo,
                    )

            tp = proc_result.get("turning_point")
            if tp:
                self._turning_points.append(tp)

            em = proc_result.get("emotional_memory")
            if em:
                self._emotional_memories.append(em)

            result["is_turning_point"] = proc_result.get("is_turning_point", False)
            result["interpretation"] = proc_result.get("interpretation", {})

        self._version += 1
        desc = event.get('description', '')[:60]
        tp_label = " [TURNING POINT]" if result.get("is_turning_point") else ""
        self._log_debug("SOUL", f"Runtime event added: {desc}{tp_label}")
        return result

    def add_belief(self, content: str, category: str = "general", strength: float = 0.5) -> BeliefEntry:
        belief = self._synth.belief_manager.form_belief(
            content=content,
            category=category,
            strength=strength,
        )
        self._beliefs.append(belief)
        self._version += 1
        return belief

    def apply_emotional_trigger(self, text: str) -> EmotionalState:
        if not self._emotional:
            self._emotional = self._synth.emotion.create_default()
        self._emotional = self._synth.emotion.apply_text_trigger(self._emotional, text)
        return self._emotional

    # ------------------------------------------------------------------
    # Prompt block generation
    # ------------------------------------------------------------------

    def get_psychology_block(self) -> str:
        if not self._psychology:
            return ""

        bf = self._psychology.current_big_five
        parts = ["[PSYCHOLOGY STATE — Estado psicológico actual]"]

        parts.append(
            f"Personalidad: "
            f"Apertura={bf.get('openness', 0.5):.1f}, "
            f"Escrupulosidad={bf.get('conscientiousness', 0.5):.1f}, "
            f"Extraversión={bf.get('extraversion', 0.5):.1f}, "
            f"Amabilidad={bf.get('agreeableness', 0.5):.1f}, "
            f"Neuroticismo={bf.get('neuroticism', 0.5):.1f}"
        )

        parts.append(f"Apego: {self._psychology.attachment_style.capitalize()}")

        unsatisfied = [k for k, v in self._psychology.needs.items() if v < 0.35]
        if unsatisfied:
            parts.append("Necesidades activas: " + ", ".join(unsatisfied))

        if self._psychology.active_wounds:
            wounds = self._psychology.active_wounds[:3]
            parts.append("Heridas emocionales activas:")
            for w in wounds:
                parts.append(f"- {w[:120]}")

        if self._psychology.active_conflicts:
            parts.append("Conflictos internos:")
            for c in self._psychology.active_conflicts[:2]:
                parts.append(f"- {c}")

        if self._psychology.active_coping:
            parts.append(f"Mecanismos de afrontamiento: {', '.join(self._psychology.active_coping[:3])}")

        return "\n".join(parts)

    def get_persona_block(self) -> str:
        if not self._persona:
            if not self._psychology:
                self.synthesize_psychology()
            self.synthesize_persona()

        parts = ["[EXPRESSION STATE — Cómo se expresa actualmente]"]

        style_map = {
            "animated": "Animado, expresivo",
            "quiet": "Tranquilo, reservado",
            "casual": "Relajado, informal",
            "somber": "Serio, sobrio",
            "warm": "Cálido, acogedor",
            "intense": "Intenso, apasionado",
            "neutral": "Neutral, directo",
        }

        style_desc = style_map.get(self._persona.speech_style, "Neutral")
        parts.append(f"Estilo de habla: {style_desc} ({self._persona.speech_style})")

        parts.append(f"Verbosidad: {'Alta' if self._persona.verbosity > 0.65 else 'Media' if self._persona.verbosity > 0.35 else 'Baja'}")
        parts.append(f"Sarcasmo: {'Frecuente' if self._persona.sarcasm_tendency > 0.6 else 'Ocasional' if self._persona.sarcasm_tendency > 0.3 else 'Raro'}")
        parts.append(f"Calidez: {'Alta' if self._persona.warmth > 0.6 else 'Media' if self._persona.warmth > 0.35 else 'Baja'}")
        parts.append(f"Defensividad: {'Alta' if self._persona.defensiveness > 0.6 else 'Media' if self._persona.defensiveness > 0.35 else 'Baja'}")

        if self._persona.humor_style != "none":
            parts.append(f"Humor: {self._persona.humor_style.replace('_', ' ')} ({self._persona.humor_frequency:.0%} del tiempo)")

        if self._persona.emotional_distance > 0.6:
            parts.append("Distancia emocional: Mantiene distancia")
        elif self._persona.emotional_distance < 0.3:
            parts.append("Distancia emocional: Cercano, accesible")

        if self._emotional:
            em = self._emotional.dominant_emotion
            parts.append(f"Estado de ánimo actual: {em.capitalize()}")

        return "\n".join(parts)

    def get_timeline_block(self) -> str:
        parts = ["[TIMELINE — Línea de vida del personaje]"]

        memory_loss = getattr(self._core_identity, 'memory_loss_start_age', 0) if self._core_identity else 0
        if memory_loss > 0:
            parts.append(f"(No recuerda nada antes de los {memory_loss} años)")

        tps = sorted(self._turning_points, key=lambda t: getattr(t, 'age', 0))
        for tp in tps:
            age = getattr(tp, 'age', '?')
            event = getattr(tp, 'event', '')[:100]
            intensity = getattr(tp, 'intensity', 0)
            meaning = getattr(tp, 'meaning_assigned', '')
            bar = "█" * int(intensity * 20) + "░" * (20 - int(intensity * 20))
            parts.append(f"\n  Age {age} [{bar}]")
            if event:
                parts.append(f"  {event}")
            if meaning:
                parts.append(f"  → {meaning}")

        if self._emotional_memories:
            parts.append("\n  Recuerdos (pueden estar distorsionados por el tiempo):")
            for em in self._emotional_memories[-3:]:
                original = getattr(em, 'original_event', '')[:80]
                remembered = getattr(em, 'remembered_version', '')[:80]
                distortion = getattr(em, 'distortion_level', 0)
                if distortion > 0.4:
                    parts.append(f"  ∼ Recuerda: {remembered}")
                    parts.append(f"    (Realidad: {original})")
                else:
                    parts.append(f"  • {original}")

        return "\n".join(parts)

    def get_why_block(self, trigger_context: str = "") -> str:
        if not self._psychology or not self._genome:
            return ""

        psych = self._psychology
        bf = psych.current_big_five

        parts = ["[RAZÓN DE SER — Por qué soy como soy]"]

        if self._turning_points:
            parts.append("Momentos que me cambiaron:")
            for tp in self._turning_points[-3:]:
                sign = "+" if getattr(tp, 'positive', True) else "-"
                age = getattr(tp, 'age', '?')
                meaning = getattr(tp, 'meaning_assigned', '')
                emo_mem = getattr(tp, 'emotional_memory', '')[:80]
                parts.append(f"  [{sign}] Age {age}: {emo_mem}")
                if meaning:
                    parts.append(f"      → {meaning}")

        elif self._soul_events:
            important_events = sorted(
                [e for e in self._soul_events if e.get("importance", 0) > 0.7],
                key=lambda e: e.get("importance", 0), reverse=True,
            )
            if important_events:
                parts.append("Experiencias que me marcaron:")
                for ev in important_events[:2]:
                    desc = ev.get("description", "")[:120]
                    imp = ev.get("importance", 0)
                    parts.append(f"- [{imp:.0%}] {desc}")

        if self._beliefs:
            strong_beliefs = [b for b in self._beliefs if b.strength > 0.6]
            if strong_beliefs:
                parts.append("Creencias que aprendí:")
                for b in strong_beliefs[:2]:
                    parts.append(f"- {b.content[:100]}")

        if self._core_identity:
            narrative = getattr(self._core_identity, 'self_narrative', '')
            if narrative:
                parts.append(f"Lo que pienso de mí mismo: {narrative}")

        if psych.active_conflicts:
            parts.append("Mis contradicciones:")
            for c in psych.active_conflicts[:2]:
                parts.append(f"- {c}")

        unsatisfied = [k for k, v in psych.needs.items() if v < 0.35]
        if unsatisfied:
            parts.append(f"Lo que necesito y no tengo: {', '.join(unsatisfied)}")

        if bf.get("neuroticism", 0.5) > 0.65:
            parts.append("Vivo con mucha intensidad emocional. Las cosas me afectan profundamente.")
        elif bf.get("neuroticism", 0.5) < 0.35:
            parts.append("Soy emocionalmente estable. Cuesta sacarme de mis casillas.")
        if bf.get("extraversion", 0.5) < 0.35:
            parts.append("Necesito mi espacio. La gente me agota si no tengo tiempo a solas.")
        elif bf.get("extraversion", 0.5) > 0.65:
            parts.append("Me energiza estar con gente. La soledad me pesa.")

        if psych.active_wounds and trigger_context:
            for w in psych.active_wounds:
                if any(word in trigger_context.lower() for word in w.lower().split()[:3]):
                    parts.append(f"(Esto me toca una herida: {w[:80]})")
                    break

        return "\n".join(parts)
