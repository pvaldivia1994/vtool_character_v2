"""reflection.py — Fase 6: Reflection Engine + Fase 8: Identity Drift."""

from __future__ import annotations

import json
import random
from typing import Optional

from .soul_generator import SoulGenerator, _SoulState


def _process_reflection(self: SoulGenerator, event: dict, state: _SoulState) -> None:
    importance = event.get("importance", 0.5)

    if self._has_llm and importance > 0.75:
        reflection = self._generate_reflection_with_llm(event, state)
    else:
        reflection = self._generate_reflection_rule_based(event, state)

    if reflection:
        state.internal_conflicts.append(reflection)

        belief_change = reflection.get("belief_change", "")
        if belief_change:
            key = f"belief_{len(state.beliefs)}"
            state.beliefs[key] = belief_change

        emotional_shift = reflection.get("emotional_shift", {})
        if isinstance(emotional_shift, dict):
            for k, v in emotional_shift.items():
                if k in state.mental_state:
                    delta = float(v) if isinstance(v, (int, float)) else 0.1
                    state.mental_state[k] = max(0.0, min(1.0, state.mental_state[k] + delta))

        coping = reflection.get("coping_strategy", "")
        if coping:
            state.skills[coping] = state.skills.get(coping, 0) + 0.1

SoulGenerator._process_reflection = _process_reflection


def _generate_reflection_with_llm(self: SoulGenerator, event: dict, state: _SoulState) -> dict:
    prompt = (
        f"Eres un psicologo analizando el impacto de un evento en la psique de un personaje.\n\n"
        f"Evento: {event.get('description', '')}\n"
        f"Tipo: {event.get('type', '')}\n"
        f"Importancia: {event.get('importance', 0.5)}\n"
        f"Emocion: {event.get('emotion', '')}\n\n"
        f"Estado actual del personaje:\n"
        f"- Autoestima: {state.mental_state.get('self_esteem', 0.5):.2f}\n"
        f"- Ansiedad: {state.mental_state.get('anxiety', 0.3):.2f}\n"
        f"- Confianza: {state.mental_state.get('trust', 0.5):.2f}\n"
        f"- Valores: {', '.join(state.values) if state.values else 'en formacion'}\n\n"
        "Genera una reflexion interna realista en formato JSON:\n"
        "{\n"
        '  "thought": "aprendizaje interno del evento",\n'
        '  "belief_change": "nueva creencia formada",\n'
        '  "emotional_shift": {"trust": -0.1, "anxiety": 0.2},\n'
        '  "coping_strategy": "mecanismo de defensa"\n'
        "}\n"
        "Importante: los cambios emocionales deben ser sutiles (0.0 a 0.3), no extremos."
    )

    try:
        result = self._llm_client.generate(
            messages=[
                {"role": "system", "content": "Eres un psicologo narrativo. Responde SOLO con JSON valido."},
                {"role": "user", "content": prompt},
            ],
            stream=False,
            max_tokens=256,
            temperature=0.7,
        )
        text = result["choices"][0]["message"].get("content", "")
        reflection = self._parse_reflection_from_json(text)
        if reflection:
            return reflection
    except Exception:
        pass

    return self._generate_reflection_rule_based(event, state)

SoulGenerator._generate_reflection_with_llm = _generate_reflection_with_llm


def _generate_reflection_rule_based(self: SoulGenerator, event: dict, state: _SoulState) -> dict:
    ev_type = event.get("type", "")

    reflection_map = {
        "loss": {
            "thought": "Learned that nothing lasts forever.",
            "belief_change": "Attachment leads to pain.",
            "emotional_shift": {"trust": -0.05, "anxiety": 0.05},
            "coping_strategy": "emotional_guarding",
        },
        "trauma": {
            "thought": "Some experiences leave permanent marks.",
            "belief_change": "The world can be dangerous.",
            "emotional_shift": {"trust": -0.1, "anxiety": 0.15, "self_esteem": -0.05},
            "coping_strategy": "hypervigilance",
        },
        "betrayal": {
            "thought": "Trust is a fragile thing.",
            "belief_change": "People are ultimately self-interested.",
            "emotional_shift": {"trust": -0.15, "self_esteem": -0.05},
            "coping_strategy": "hyper_independence",
        },
        "success": {
            "thought": "Hard work pays off.",
            "belief_change": "I am capable of achieving things.",
            "emotional_shift": {"self_esteem": 0.1, "happiness": 0.1},
            "coping_strategy": "self_affirmation",
        },
        "failure": {
            "thought": "Not everything works out, and that is okay.",
            "belief_change": "Failure is part of growth.",
            "emotional_shift": {"self_esteem": -0.05, "resilience": 0.05},
            "coping_strategy": "reframing",
        },
        "romantic": {
            "thought": "Love changes everything.",
            "belief_change": "Connection with others defines life.",
            "emotional_shift": {"happiness": 0.1, "trust": 0.05},
            "coping_strategy": "vulnerability",
        },
    }

    base = reflection_map.get(ev_type, {
        "thought": f"This {ev_type} experience was impactful.",
        "belief_change": "Experiences shape who we become.",
        "emotional_shift": {},
        "coping_strategy": "reflection",
    })

    return dict(base)

SoulGenerator._generate_reflection_rule_based = _generate_reflection_rule_based


def _parse_reflection_from_json(self: SoulGenerator, text: str) -> Optional[dict]:
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end <= start:
            return None
        data = json.loads(text[start:end])
        required = ["thought"]
        if all(k in data for k in required):
            return data
        return None
    except Exception:
        return None

SoulGenerator._parse_reflection_from_json = _parse_reflection_from_json


def _apply_identity_drift(self: SoulGenerator, current_month: int, state: _SoulState) -> None:
    años_vividos = current_month // 12

    for trait in state.core_traits:
        drift = random.uniform(-0.03, 0.03)
        state.core_traits[trait] = max(0.05, min(0.95, state.core_traits[trait] + drift))

    num_conflicts = len(state.internal_conflicts)
    if num_conflicts > 5:
        state.core_traits["neuroticism"] = min(0.95, state.core_traits["neuroticism"] + 0.02)
    if num_conflicts > 10:
        state.core_traits["neuroticism"] = min(0.95, state.core_traits["neuroticism"] + 0.01)

    trauma_count = sum(
        1 for c in state.internal_conflicts
        if "trauma" in c.get("coping_strategy", "") or "guarding" in c.get("coping_strategy", "")
    )
    if trauma_count > 3:
        state.core_traits["agreeableness"] = max(0.05, state.core_traits["agreeableness"] - 0.02)

    if años_vividos > 25:
        state.core_traits["conscientiousness"] = min(0.95, state.core_traits["conscientiousness"] + 0.01)

    self._log_debug("SOUL", f"Identity drift applied at age {años_vividos}")

SoulGenerator._apply_identity_drift = _apply_identity_drift
