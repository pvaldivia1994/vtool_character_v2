"""compression.py — Fase 9: Compresión semántica + Checkpoints + Persistencia."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .soul_generator import SoulGenerator, _SoulState


def _compress_soul(self: SoulGenerator, total_events: int) -> dict:
    state = self._soul_state

    if self._has_llm and self._chroma and self._chroma.is_available:
        return self._compress_with_llm(state, total_events)

    return self._compress_heuristic(state, total_events)

SoulGenerator._compress_soul = _compress_soul


def _compress_with_llm(self: SoulGenerator, state: _SoulState, total_events: int) -> dict:
    events_sample = []
    if self._chroma and self._chroma.is_available:
        try:
            sample = self._chroma.search("most important life events", top_k=20)
            events_sample = [s["description"] for s in sample if s.get("description")]
        except Exception:
            events_sample = []

    traits_str = json.dumps(state.core_traits, indent=2)
    mental_str = json.dumps(state.mental_state, indent=2)
    values_str = ", ".join(state.values) if state.values else "developing"
    conflicts_str = json.dumps([
        c.get("thought", "") for c in state.internal_conflicts[-10:]
    ], indent=2) if state.internal_conflicts else "none yet"

    events_str = "\n".join(events_sample[:15]) if events_sample else "varied life experiences"

    prompt = (
        "Eres un escritor de ficcion especializado en crear perfiles psicologicos "
        "profundos y realistas. Analiza la siguiente vida simulada y genera un "
        "nucleo psicologico COMPRIMIDO pero RICO en matices.\n\n"
        f"Rasgos de personalidad actuales:\n{traits_str}\n\n"
        f"Estado mental:\n{mental_str}\n\n"
        f"Valores: {values_str}\n\n"
        f"Conflictos internos:\n{conflicts_str}\n\n"
        f"Eventos de vida representativos:\n{events_str}\n\n"
        "Genera un JSON con el siguiente esquema EXACTO:\n"
        "{\n"
        '  "core_identity": {"summary": "quien es, en 2-3 oraciones", "archetype": "arquetipo"},'
        '  "emotional_scars": ["herida 1", "herida 2"],'
        '  "hidden_desires": ["deseo 1", "deseo 2"],'
        '  "contradictions": ["contradiccion 1", "contradiccion 2"],'
        '  "worldview": {"optimism": 0.5, "morality": 0.5, "individualism": 0.5, "traditionalism": 0.5},'
        '  "behavior_biases": ["sesgo 1", "sesgo 2"],'
        '  "important_people": [],'
        '  "life_philosophy": "una linea que define su filosofia de vida",'
        '  "speech_bias": {"style": "como habla", "quirks": []},'
        '  "core_memories": ["recuerdo fundacional 1", "recuerdo fundacional 2"],'
        '  "secret_shame": "verguenza secreta",'
        '  "coping_mechanisms": ["mecanismo 1"]'
        "}\n\n"
        "REGLAS:\n"
        "- NO generes perfiles genericos o de Wikipedia\n"
        "- Debe sentirse como el nucleo psicologico REAL del personaje\n"
        "- Incluye contradicciones y ambiguedad\n"
        "- Los deseos ocultos deben ser especificos, no abstractos\n"
        "- Las heridas emocionales deben tener origen en eventos de vida\n"
        "- La filosofia de vida debe ser personal, no un cliche"
    )

    try:
        result = self._llm_client.generate(
            messages=[
                {"role": "system", "content": "Eres un escritor de perfiles psicologicos. Responde SOLO con JSON valido."},
                {"role": "user", "content": prompt},
            ],
            stream=False,
            max_tokens=2048,
            temperature=0.75,
        )
        text = result["choices"][0]["message"].get("content", "")
        compressed = self._parse_compressed_json(text)
        if compressed and compressed.get("core_identity"):
            compressed["_generated_by"] = "llm"
            return compressed
    except Exception as e:
        self._log_warning(f"Error en compresion con LLM: {e}")

    return self._compress_heuristic(state, total_events)

SoulGenerator._compress_with_llm = _compress_with_llm


def _compress_heuristic(self: SoulGenerator, state: _SoulState, total_events: int) -> dict:
    traits = state.core_traits
    mental = state.mental_state

    archetype = "The Seeker"
    if traits["conscientiousness"] > 0.7 and traits["neuroticism"] < 0.4:
        archetype = "The Pillar"
    elif traits["extraversion"] > 0.7:
        archetype = "The Socialite"
    elif traits["neuroticism"] > 0.7:
        archetype = "The Tormented"
    elif traits["openness"] > 0.7:
        archetype = "The Explorer"

    summary_parts = []
    if mental.get("happiness", 0.5) > 0.6:
        summary_parts.append("generally content")
    else:
        summary_parts.append("carries inner struggles")

    if mental.get("trust", 0.5) < 0.4:
        summary_parts.append("guarded and cautious with others")
    elif mental.get("trust", 0.5) > 0.7:
        summary_parts.append("open and trusting")

    if state.fears:
        summary_parts.append(f"haunted by {state.fears[0][:50]}")

    summary = f"A person who is {', '.join(summary_parts)}. "
    summary += f"Life has shaped them into {archetype.lower()}."

    return {
        "core_identity": {
            "summary": summary,
            "archetype": archetype,
        },
        "emotional_scars": [
            c.get("thought", "") for c in state.internal_conflicts[-5:]
            if "trust" in str(c.get("emotional_shift", {}))
        ] or ["Life experiences have left their mark"],
        "hidden_desires": state.values[:3] or ["To find meaning"],
        "contradictions": [
            "Wants connection but fears vulnerability",
            "Seeks stability but craves novelty",
        ],
        "worldview": state.worldview,
        "behavior_biases": [
            "Acts based on past experiences",
        ],
        "important_people": [],
        "life_philosophy": "Life is what happens while making other plans.",
        "speech_bias": {
            "style": "Reflective and measured",
            "quirks": ["Often references past experiences"],
        },
        "core_memories": [
            c.get("thought", "")[:100] for c in state.internal_conflicts[:3]
            if c.get("thought")
        ] or ["A life lived fully"],
        "secret_shame": "None disclosed",
        "coping_mechanisms": list(state.skills.keys())[:5] or ["reflection"],
        "_generated_by": "heuristic",
    }

SoulGenerator._compress_heuristic = _compress_heuristic


def _parse_compressed_json(self: SoulGenerator, text: str) -> Optional[dict]:
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end <= start:
            return None
        return json.loads(text[start:end])
    except Exception:
        return None

SoulGenerator._parse_compressed_json = _parse_compressed_json


def _save_checkpoint(
    self: SoulGenerator,
    path: Optional[Path],
    current_month: int,
    state: _SoulState,
    character_name: str = "",
) -> None:
    if not path:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        cp = {
            "character_name": character_name,
            "current_month": current_month,
            "genome": asdict(self._genome) if hasattr(self, '_genome') and self._genome else None,
            "soul_state": {
                "age_months": state.age_months,
                "core_traits": state.core_traits,
                "mental_state": state.mental_state,
                "beliefs": state.beliefs,
                "worldview": state.worldview,
                "values": state.values,
                "fears": state.fears,
                "internal_conflicts": state.internal_conflicts[-50:],
                "goals": state.goals,
                "skills": state.skills,
                "economic_state": state.economic_state,
                "event_count": state.event_count,
            },
            "chroma_ready": self._chroma is not None and self._chroma.is_available,
            "timestamp": time.time(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cp, f, ensure_ascii=False, indent=2)
    except Exception as e:
        self._log_warning(f"Error guardando checkpoint: {e}")

SoulGenerator._save_checkpoint = _save_checkpoint


def _load_checkpoint(self: SoulGenerator, path: Path) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

SoulGenerator._load_checkpoint = _load_checkpoint


def _restore_soul_state(self: SoulGenerator, state_data: dict) -> None:
    if not self._soul_state:
        self._soul_state = _SoulState()

    for key, val in state_data.items():
        if hasattr(self._soul_state, key):
            setattr(self._soul_state, key, val)

SoulGenerator._restore_soul_state = _restore_soul_state


def _cleanup_checkpoints(self: SoulGenerator, path: Optional[Path]) -> None:
    if path and path.exists():
        try:
            path.unlink()
            self._log_debug("SOUL", "Checkpoints cleanup done.")
        except Exception:
            pass

SoulGenerator._cleanup_checkpoints = _cleanup_checkpoints


def _save_soul_json(self: SoulGenerator, path: Path, data: dict) -> None:
    soul_output = {
        "version": "2.0",
        "compressed": data.get("compressed", data),
        "events_count": data.get("events_generated", 0),
        "life_months": data.get("life_months",
            self._soul_state.age_months if self._soul_state else 0),
        "memory_loss_start_age": self._soul_state.memory_loss_start_age if self._soul_state else 0,
        "world_context": {
            "world_type": getattr(self, "_world_type", "real"),
            "country": getattr(self, "_country", "US"),
            "birth_year": getattr(self, "_birth_year", 2000),
            "economy": getattr(self, "_economy", "stable"),
            "family_income": getattr(self, "_family_income", "middle_class"),
            "world_description": getattr(self, "_world_description", ""),
            "use_historical_context": getattr(self, "_use_historical_context", False),
            "fictional_lore_reference": getattr(self, "_fictional_lore_reference", ""),
        },
    }

    if self._soul_state and hasattr(self._soul_state, 'beliefs') and self._soul_state.beliefs:
        beliefs_list = []
        for bid, bdata in self._soul_state.beliefs.items():
            if isinstance(bdata, dict):
                beliefs_list.append({
                    "id": bid,
                    "content": bdata.get("content", ""),
                    "strength": bdata.get("strength", 0.5),
                    "source": bdata.get("source_event", ""),
                })
        soul_output["beliefs"] = beliefs_list

    if hasattr(self, '_genome') and self._genome:
        genome_dict = {k: getattr(self._genome, k) for k in
            ["sociability", "emotional_sensitivity", "impulsivity",
             "risk_aversion", "empathy", "curiosity", "security_need",
             "independence", "creativity", "aggression",
             "emotional_regulation", "persistence", "playfulness"]}
        soul_output["genome"] = genome_dict

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(soul_output, f, ensure_ascii=False, indent=2)
    self._log_info(f"Soul saved: {path}")

SoulGenerator._save_soul_json = _save_soul_json


def _add_event_to_history(
    self: SoulGenerator, event_id: str, month: int, event: dict, psy_impact: dict,
) -> None:
    if not getattr(self, "_save_events_history", True):
        return
    if not self._char_dir:
        return

    history_dir = self._char_dir / "_memory"
    history_dir.mkdir(parents=True, exist_ok=True)
    history_path = history_dir / "life_events.json"

    event_history = []
    if history_path.exists():
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                event_history = json.load(f)
        except Exception:
            event_history = []

    if any(e.get("event_id") == event_id for e in event_history):
        return

    history_entry = {
        "event_id": event_id,
        "month": month,
        "age_years": month // 12,
        "age_months": month % 12,
        "type": event.get("type", "unknown"),
        "description": event.get("description", ""),
        "importance": event.get("importance", 0.5),
        "emotion": event.get("emotion", "neutral"),
        "location": event.get("location", "unknown"),
        "people_involved": event.get("people_involved", []),
        "psychological_impact": psy_impact,
        "belief_formed": event.get("belief_formed", ""),
        "reflection": event.get("reflection", ""),
        "coping_strategy": event.get("coping_strategy", ""),
    }
    event_history.append(history_entry)

    try:
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(event_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        self._log_warning(f"Error escribiendo life_events.json: {e}")

SoulGenerator._add_event_to_history = _add_event_to_history
