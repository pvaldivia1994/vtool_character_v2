"""synthesizer.py — PsychologySynthesizer: síntesis runtime de psicología."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from ..types import (
    BeliefEntry,
    EmotionalMemory,
    EmotionalState,
    Genome,
    PersonaState,
    PsychologyState,
    TurningPoint,
)

from .emotional_dynamics import EmotionalDynamics
from .belief_manager import BeliefManager


class PsychologySynthesizer:
    def __init__(
        self,
        log_debug_fn: Optional[Callable] = None,
        log_info_fn: Optional[Callable] = None,
    ):
        self._log_debug = log_debug_fn or (lambda t, m: None)
        self._log_info = log_info_fn or (lambda m: None)
        self._emotion = EmotionalDynamics(log_fn=log_debug_fn)

    @property
    def emotion(self) -> EmotionalDynamics:
        return self._emotion

    @property
    def belief_manager(self) -> BeliefManager:
        if not hasattr(self, '_belief_mgr'):
            self._belief_mgr = BeliefManager()
        return self._belief_mgr

    # ==================================================================
    # Full synthesis
    # ==================================================================

    def synthesize(
        self,
        genome: Genome,
        soul_events: list[dict],
        beliefs: list[BeliefEntry],
        runtime_emotional: Optional[EmotionalState] = None,
    ) -> PsychologyState:
        big_five = self._genome_to_big_five(genome)

        for event in soul_events:
            impact = event.get("psychological_impact", {}) or {}
            for axis, delta in impact.items():
                if axis in big_five:
                    big_five[axis] = max(0.05, min(0.95, big_five[axis] + delta))

        attachment = self._compute_attachment(soul_events, beliefs)
        worldview = self._compute_worldview(genome, beliefs, soul_events)
        needs = self._compute_needs(genome, big_five, worldview)
        wounds = self._compute_active_wounds(soul_events, beliefs)
        coping = self._compute_coping(soul_events)
        conflicts = self._compute_conflicts(beliefs, big_five, worldview)
        biases = self._compute_biases(genome, beliefs, soul_events)

        ps = PsychologyState(
            current_big_five=big_five,
            attachment_style=attachment,
            needs=needs,
            active_wounds=wounds,
            active_coping=coping,
            active_conflicts=conflicts,
            active_biases=biases,
            worldview=worldview,
            version=1,
        )

        self._log_debug("PSY", f"Psychology synthesized: big_five={big_five}, attachment={attachment}")

        return ps

    # ==================================================================
    # Tick synthesis (runtime, cheaper)
    # ==================================================================

    def tick(
        self,
        current: PsychologyState,
        genome: Genome,
        recent_interactions: list[dict],
        beliefs: list[BeliefEntry],
    ) -> PsychologyState:
        new = PsychologyState(**{
            k: (dict(v) if isinstance(v, dict) else
                list(v) if isinstance(v, list) else v)
            for k, v in asdict(current).items()
        })
        new.version = current.version + 1

        if recent_interactions:
            valence_sum = 0
            arousal_sum = 0
            count = 0

            for interaction in recent_interactions[-10:]:
                text = interaction.get("response", "") or ""
                lower = text.lower()
                pos = sum(1 for w in ["gracias", "feliz", "bien", "mejor", "amo", "encanta"] if w in lower)
                neg = sum(1 for w in ["triste", "mal", "peor", "odio", "temo", "duele"] if w in lower)
                if pos > neg:
                    valence_sum += 0.05 * min(pos, 3)
                    arousal_sum += 0.02 * min(pos, 3)
                elif neg > pos:
                    valence_sum -= 0.05 * min(neg, 3)
                    arousal_sum += 0.03 * min(neg, 3)
                count += 1

            if count > 0:
                avg_valence = valence_sum / count

                new.worldview["optimism"] = max(
                    0.05, min(0.95,
                        new.worldview["optimism"] + avg_valence * 0.1
                    )
                )
                new.worldview["trust_in_people"] = max(
                    0.05, min(0.95,
                        new.worldview["trust_in_people"] + avg_valence * 0.05
                    )
                )

                if abs(avg_valence) > 0.1:
                    new.current_big_five["neuroticism"] = max(
                        0.05, min(0.95,
                            new.current_big_five["neuroticism"] - avg_valence * 0.05
                        )
                    )

        self._log_debug("PSY", f"Psychology tick: version={new.version}")

        return new

    # ==================================================================
    # Event-based synthesis
    # ==================================================================

    def process_event(
        self,
        current: PsychologyState,
        event: dict,
        genome: Genome,
        core_identity: Optional[Any] = None,
        beliefs: Optional[list] = None,
        age_months: int = 0,
    ) -> dict:
        new = PsychologyState(**{
            k: (dict(v) if isinstance(v, dict) else
                list(v) if isinstance(v, list) else v)
            for k, v in asdict(current).items()
        })
        new.version = current.version + 1

        ev_type = event.get("event_type", "unknown")
        ev_desc = event.get("description", "")
        importance = event.get("importance", 0.5)
        raw_impact = event.get("psychological_impact", {}) or {}

        # 1. PERCEPTION FILTER
        interpretation = None
        if core_identity is not None and hasattr(core_identity, 'interpret_event'):
            interpretation = core_identity.interpret_event(ev_type, ev_desc, importance)
            perceived = interpretation.get("perceived_severity", importance)
            attribution = interpretation.get("attribution", "situation")
            generated_emotion = interpretation.get("emotion", event.get("emotion", "neutral"))
            belief_impact = interpretation.get("belief_impact", {})
        else:
            perceived = importance
            attribution = "situation"
            generated_emotion = event.get("emotion", "neutral")
            belief_impact = {}
            interpretation = {
                "perceived_severity": perceived,
                "attribution": attribution,
                "emotion": generated_emotion,
            }

        # 2. TURNING POINT DETECTION
        is_turning_point = False
        turning_point_multiplier = 1.0
        turning_point_obj = None

        if perceived > 0.8 and ev_type in (
            "trauma", "loss", "betrayal", "violence",
            "romantic", "success", "accident", "discovery",
            "existential", "responsibility",
        ):
            is_turning_point = True
            turning_point_multiplier = 2.0 + (perceived - 0.8) * 5.0

            if attribution == "self":
                meaning = "I am responsible for what happened"
            elif attribution == "others":
                meaning = "Others cannot be trusted to protect me"
            else:
                meaning = "Life is unpredictable and cruel"
            if generated_emotion == "shame":
                meaning = "There is something fundamentally wrong with me"
            elif generated_emotion == "anger":
                meaning = "The world is unfair and I must defend myself"

            turning_point_obj = TurningPoint(
                age=max(0, age_months // 12),
                event=ev_desc[:200],
                intensity=perceived,
                positive=generated_emotion in ("joy", "love", "pride", "hope", "gratitude"),
                changed_traits=dict(raw_impact),
                emotional_memory=ev_desc[:200],
                meaning_assigned=meaning,
            )

            if core_identity is not None and hasattr(core_identity, 'self_narrative'):
                if attribution == "self" and not core_identity.self_narrative:
                    old = core_identity.self_narrative
                    if perceived > 0.85:
                        core_identity.self_narrative = meaning[:100]
                    elif old and "must" in old:
                        core_identity.self_narrative = old + " But now I know better."

            if core_identity is not None and hasattr(core_identity, 'self_beliefs'):
                if attribution == "self" and generated_emotion in ("shame", "guilt", "fear"):
                    for k in core_identity.self_beliefs:
                        drop = 0.15 * turning_point_multiplier
                        core_identity.self_beliefs[k] = max(0.05, core_identity.self_beliefs[k] - drop)
                elif attribution == "others" and generated_emotion == "anger":
                    if hasattr(core_identity, 'meaning_system'):
                        core_identity.meaning_system["people_are_good"] = max(
                            0.05, core_identity.meaning_system.get("people_are_good", 0.5) - 0.2
                        )

            if core_identity is not None:
                fear_map = {
                    "betrayal": "trusting others",
                    "loss": "abandonment",
                    "trauma": "being hurt again",
                    "violence": "physical harm",
                }
                new_fear = fear_map.get(ev_type, "")
                if new_fear and new_fear not in getattr(core_identity, 'core_fears', []):
                    core_identity.core_fears.append(new_fear)
                    if len(getattr(core_identity, 'core_fears', [])) > 6:
                        core_identity.core_fears = core_identity.core_fears[-6:]

        # 3. PSYCHOLOGY UPDATE
        impact = dict(raw_impact)
        for axis, delta in impact.items():
            adjusted = delta * turning_point_multiplier
            if axis in new.current_big_five:
                new.current_big_five[axis] = max(
                    0.05, min(0.95,
                        new.current_big_five[axis] + adjusted
                    )
                )
            if axis in new.worldview:
                new.worldview[axis] = max(
                    0.05, min(0.95,
                        new.worldview[axis] + adjusted
                    )
                )

        if belief_impact and core_identity is not None:
            for k, delta in belief_impact.items():
                if hasattr(core_identity, 'self_beliefs') and k in core_identity.self_beliefs:
                    adjusted = delta * turning_point_multiplier
                    core_identity.self_beliefs[k] = max(
                        0.05, min(0.95,
                            core_identity.self_beliefs[k] + adjusted
                        )
                    )

        # 4. EMOTIONAL TRIGGER
        emotion_trigger = generated_emotion

        # 5. BELIEF CREATION
        belief_added = None
        belief_content = event.get("belief_formed", "")
        if not belief_content and perceived > 0.65 and attribution != "situation":
            if attribution == "self":
                belief_content = "I am responsible for bad things happening"
            elif attribution == "others":
                belief_content = "Others cannot be trusted"
            belief_content = belief_content or ""

        if belief_content:
            belief_added = BeliefEntry(
                content=belief_content,
                source_event_id=event.get("id", ""),
                strength=min(1.0, perceived * 0.8),
                category=self._event_type_to_belief_category(ev_type),
            )

        # 6. WOUND CREATION
        wound_added = None
        if ev_type in ("trauma", "loss", "betrayal", "violence", "discrimination") and perceived > 0.65:
            wound_text = ev_desc[:100] if ev_desc else f"Deep wound from {ev_type}"
            if wound_text and wound_text not in new.active_wounds:
                new.active_wounds.append(wound_text)
                wound_added = wound_text
                if len(new.active_wounds) > 10:
                    new.active_wounds = new.active_wounds[-10:]

        # 7. TURNING POINT identity narrative shift
        if is_turning_point and core_identity is not None:
            if attribution == "self" and perceived > 0.85:
                if hasattr(core_identity, 'self_beliefs'):
                    for k in core_identity.self_beliefs:
                        core_identity.self_beliefs[k] = max(
                            0.05, core_identity.self_beliefs[k] - 0.15 * turning_point_multiplier
                        )
            elif attribution == "others" and perceived > 0.85:
                if hasattr(core_identity, 'meaning_system'):
                    core_identity.meaning_system["people_are_good"] = max(
                        0.05, core_identity.meaning_system.get("people_are_good", 0.5) - 0.2
                    )
                    core_identity.meaning_system["world_is_fair"] = max(
                        0.05, core_identity.meaning_system.get("world_is_fair", 0.5) - 0.15
                    )

            if ev_type in ("trauma", "betrayal", "loss"):
                from ..types import CoreIdentity as CID
                if isinstance(core_identity, CID):
                    fear_map = {
                        "betrayal": "trusting others",
                        "loss": "abandonment",
                        "trauma": "being hurt",
                        "violence": "physical harm",
                    }
                    new_fear = fear_map.get(ev_type, "")
                    if new_fear and new_fear not in core_identity.core_fears:
                        core_identity.core_fears.append(new_fear)
                        core_identity.core_fears = core_identity.core_fears[:5]

        # 8. EMOTIONAL MEMORY CREATION
        emotional_memory = None
        memory_loss_age = getattr(core_identity, 'memory_loss_start_age', 0) if core_identity else 0
        event_age_years = age_months // 12

        if importance > 0.4 and (memory_loss_age == 0 or event_age_years >= memory_loss_age):
            remembered = ev_desc[:200]
            if attribution == "self" and generated_emotion in ("shame", "guilt"):
                remembered = f"I remember failing. {ev_desc[:120]}"
            elif attribution == "others" and generated_emotion == "anger":
                remembered = f"They did this to me. {ev_desc[:120]}"
            elif importance > 0.8:
                remembered = ev_desc[:200]

            emotional_memory = EmotionalMemory(
                original_event=ev_desc[:200],
                remembered_version=remembered,
                emotional_weight=importance,
                confidence=0.9 if importance > 0.7 else 0.6,
                distortion_level=0.3 if attribution != "situation" else 0.1,
                event_month=age_months,
            )

        return {
            "psychology": new,
            "interpretation": interpretation,
            "belief_added": belief_added,
            "is_turning_point": is_turning_point,
            "turning_point": turning_point_obj,
            "emotional_memory": emotional_memory,
            "emotion_trigger": emotion_trigger,
            "wound_added": wound_added,
        }

    apply_runtime_event = process_event

    # ==================================================================
    # Persona Compiler
    # ==================================================================

    def compile_persona(
        self,
        psychology: PsychologyState,
        emotional: EmotionalState,
        genome: Genome,
    ) -> PersonaState:
        bf = psychology.current_big_five
        v = emotional.valence
        a = emotional.arousal

        persona = PersonaState()

        persona.verbosity = max(0.0, min(1.0,
            0.3
            + bf.get("extraversion", 0.5) * 0.3
            + (1.0 - bf.get("neuroticism", 0.5)) * 0.2
            + (1.0 - abs(a)) * 0.2
        ))

        sarcasm = (
            genome.playfulness * 0.3
            + genome.aggression * 0.2
            + (1.0 - bf.get("agreeableness", 0.5)) * 0.3
            + max(0, v * -0.2)
        )
        persona.sarcasm_tendency = max(0.0, min(1.0, sarcasm))

        warmth = (
            bf.get("agreeableness", 0.5) * 0.4
            + genome.empathy * 0.3
            - (bf.get("neuroticism", 0.5) - 0.5) * 0.2
            + max(0, v * 0.1)
        )
        persona.warmth = max(0.0, min(1.0, warmth))

        defensiveness = (
            bf.get("neuroticism", 0.5) * 0.3
            + genome.risk_aversion * 0.2
            + (1.0 - psychology.worldview.get("trust_in_people", 0.5)) * 0.3
            + max(0, a * 0.1)
        )
        persona.defensiveness = max(0.0, min(1.0, defensiveness))

        if bf.get("extraversion", 0.5) > 0.65 and a > 0.2:
            persona.speech_style = "animated"
        elif bf.get("extraversion", 0.5) < 0.35:
            persona.speech_style = "quiet"
        elif (1.0 - bf.get("conscientiousness", 0.5)) > 0.6 and genome.playfulness > 0.6:
            persona.speech_style = "casual"
        elif v < -0.3:
            persona.speech_style = "somber"
        elif v > 0.5 and a < 0:
            persona.speech_style = "warm"
        elif a > 0.5:
            persona.speech_style = "intense"
        else:
            persona.speech_style = "neutral"

        if genome.playfulness > 0.6 and v > 0.2:
            if bf.get("agreeableness", 0.5) > 0.6:
                persona.humor_style = "witty"
                persona.humor_frequency = genome.playfulness * 0.6
            elif bf.get("neuroticism", 0.5) > 0.6:
                persona.humor_style = "dark"
                persona.humor_frequency = genome.playfulness * 0.4
            else:
                persona.humor_style = "self_deprecating"
                persona.humor_frequency = genome.playfulness * 0.5
        elif v < -0.4:
            persona.humor_style = "none"
            persona.humor_frequency = 0.1

        persona.emotional_distance = max(0.0, min(1.0,
            1.0 - persona.warmth * 0.5 + persona.defensiveness * 0.4
        ))

        self_disc = (
            bf.get("extraversion", 0.5) * 0.3
            + psychology.worldview.get("trust_in_people", 0.5) * 0.3
            - persona.defensiveness * 0.3
            + genome.independence * -0.1
        )
        persona.self_disclosure = max(0.0, min(1.0, self_disc))

        persona.uses_actions = True
        persona._synthesized_at = datetime.now(timezone.utc).isoformat()

        return persona

    # ==================================================================
    # Internals
    # ==================================================================

    def _genome_to_big_five(self, genome: Genome) -> dict[str, float]:
        return {
            "openness": (
                genome.curiosity * 0.3
                + genome.creativity * 0.3
                + (1.0 - genome.risk_aversion) * 0.2
                + genome.independence * 0.2
            ),
            "conscientiousness": (
                genome.persistence * 0.4
                + (1.0 - genome.impulsivity) * 0.3
                + genome.emotional_regulation * 0.3
            ),
            "extraversion": (
                genome.sociability * 0.4
                + (1.0 - genome.security_need) * 0.2
                + genome.playfulness * 0.2
                + (1.0 - genome.emotional_sensitivity) * 0.2
            ),
            "agreeableness": (
                genome.empathy * 0.4
                + (1.0 - genome.aggression) * 0.3
                + genome.sociability * 0.3
            ),
            "neuroticism": (
                (1.0 - genome.emotional_regulation) * 0.3
                + genome.emotional_sensitivity * 0.3
                + genome.risk_aversion * 0.2
                + (1.0 - genome.independence) * 0.2
            ),
        }

    def _compute_attachment(
        self,
        soul_events: list[dict],
        beliefs: list[BeliefEntry],
    ) -> str:
        early_events = [e for e in soul_events if e.get("month", 999) < 60]
        if not early_events:
            return "secure"

        loss_count = sum(1 for e in early_events if e.get("event_type") in ("loss", "trauma", "betrayal"))
        neglect_count = sum(1 for e in early_events if e.get("event_type") == "family" and e.get("importance", 0) > 0.6)
        love_count = sum(1 for e in early_events if e.get("event_type") in ("family", "friendship") and e.get("emotion") in ("joy", "love", "trust"))

        if loss_count >= 3:
            return "disorganized"
        if loss_count >= 2 or (neglect_count >= 2 and love_count == 0):
            return "avoidant"
        if loss_count >= 1 and love_count < 2:
            return "anxious"

        return "secure"

    def _compute_worldview(
        self,
        genome: Genome,
        beliefs: list[BeliefEntry],
        soul_events: list[dict],
    ) -> dict[str, float]:
        optimism = genome.playfulness * 0.3 + 0.3
        trust = genome.empathy * 0.3 + 0.3
        control = genome.independence * 0.2 + 0.4
        meaning = genome.curiosity * 0.3 + 0.3

        for b in beliefs:
            if b.category == "trust":
                trust += (b.strength - 0.5) * 0.2
            elif b.category == "worldview":
                if "optimism" in b.content.lower() or "hope" in b.content.lower():
                    optimism += (b.strength - 0.5) * 0.2
                if "control" in b.content.lower() or "powerless" in b.content.lower():
                    control -= (b.strength - 0.5) * 0.2

        trauma_count = sum(1 for e in soul_events if e.get("event_type") in ("trauma", "betrayal", "violence"))
        if trauma_count > 2:
            trust = max(0.05, trust - trauma_count * 0.05)
            optimism = max(0.05, optimism - trauma_count * 0.03)
            control = max(0.05, control - trauma_count * 0.02)

        return {
            "optimism": max(0.05, min(0.95, optimism)),
            "trust_in_people": max(0.05, min(0.95, trust)),
            "sense_of_control": max(0.05, min(0.95, control)),
            "meaningfulness": max(0.05, min(0.95, meaning)),
        }

    def _compute_needs(
        self,
        genome: Genome,
        big_five: dict[str, float],
        worldview: dict[str, float],
    ) -> dict[str, float]:
        return {
            "safety": max(0.05, min(0.95,
                1.0 - genome.risk_aversion * 0.3
                + worldview.get("sense_of_control", 0.5) * 0.3
                - big_five.get("neuroticism", 0.5) * 0.3
            )),
            "belonging": max(0.05, min(0.95,
                genome.sociability * 0.4
                + (1.0 - genome.independence) * 0.3
                - big_five.get("extraversion", 0.5) * 0.2
            )),
            "esteem": max(0.05, min(0.95,
                big_five.get("conscientiousness", 0.5) * 0.3
                + (1.0 - big_five.get("neuroticism", 0.5)) * 0.3
                + worldview.get("optimism", 0.5) * 0.2
            )),
            "autonomy": max(0.05, min(0.95,
                genome.independence * 0.5
                + big_five.get("openness", 0.5) * 0.3
            )),
            "meaning": max(0.05, min(0.95,
                genome.curiosity * 0.4
                + worldview.get("meaningfulness", 0.5) * 0.3
                + (1.0 - big_five.get("neuroticism", 0.5)) * 0.2
            )),
        }

    def _compute_active_wounds(
        self,
        soul_events: list[dict],
        beliefs: list[BeliefEntry],
    ) -> list[str]:
        wounds = []
        for e in soul_events:
            if e.get("importance", 0) > 0.75:
                ev_type = e.get("event_type", "")
                if ev_type in ("trauma", "loss", "betrayal", "violence", "discrimination"):
                    desc = e.get("description", "")[:100]
                    if desc:
                        wounds.append(desc)
        return wounds[:5]

    def _compute_coping(self, soul_events: list[dict]) -> list[str]:
        coping_set: set[str] = set()
        for e in soul_events:
            strategy = e.get("coping_strategy", "")
            if strategy:
                coping_set.add(strategy)
        return list(coping_set)

    def _compute_conflicts(
        self,
        beliefs: list[BeliefEntry],
        big_five: dict[str, float],
        worldview: dict[str, float],
    ) -> list[str]:
        conflicts = []

        if worldview.get("trust_in_people", 0.5) < 0.3 and big_five.get("agreeableness", 0.5) > 0.6:
            conflicts.append("Wants to trust but experience says otherwise")

        if worldview.get("trust_in_people", 0.5) < 0.4 and big_five.get("extraversion", 0.5) > 0.6:
            conflicts.append("Craves connection yet fears vulnerability")

        if big_five.get("conscientiousness", 0.5) > 0.7 and big_five.get("neuroticism", 0.5) > 0.6:
            conflicts.append("Driven by high standards paralyzed by fear of failure")

        return conflicts[:3]

    def _compute_biases(
        self,
        genome: Genome,
        beliefs: list[BeliefEntry],
        soul_events: list[dict],
    ) -> list[str]:
        biases = []
        trauma_count = sum(1 for e in soul_events if e.get("event_type") in ("trauma", "betrayal", "violence"))

        if trauma_count > 2:
            biases.append("hypervigilance")
        if genome.risk_aversion > 0.7:
            biases.append("loss_aversion")
        if genome.emotional_sensitivity > 0.7:
            biases.append("emotional_amplification")
        worldview_val = self._compute_worldview(genome, beliefs, soul_events)
        if genome.aggression > 0.6 and worldview_val.get("trust_in_people", 0.5) < 0.35:
            biases.append("cynicism")

        return biases[:5]

    def _event_type_to_belief_category(self, ev_type: str) -> str:
        mapping = {
            "trauma": "self", "betrayal": "trust",
            "loss": "trust", "family": "trust",
            "romantic": "trust", "friendship": "trust",
            "success": "self", "failure": "self",
            "discrimination": "worldview", "violence": "worldview",
            "crime": "worldview", "political": "worldview",
        }
        return mapping.get(ev_type, "general")
