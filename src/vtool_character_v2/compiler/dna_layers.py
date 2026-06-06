"""dna_layers.py — Capas de DNA del CharacterCompiler."""

from __future__ import annotations


from .compiler import CharacterCompiler


def _get_mod_override(self: CharacterCompiler, target_layer: str) -> str | None:
    overrides = []
    for mod in self.manager.active_mods.values():
        if mod.target_layer == target_layer and mod.override_value:
            overrides.append(mod)
    if overrides:
        overrides.sort(key=lambda m: (m.intensity, m.id), reverse=True)
        return overrides[0].override_value
    return None

CharacterCompiler._get_mod_override = _get_mod_override


def _load_template(name: str) -> str:
    """Carga un template desde config/prompts/ o devuelve vacío."""
    from pathlib import Path
    base = Path(__file__).resolve().parent.parent / "config" / "prompts"
    # Buscar con número: 2_traits.md, 3_motivations.md, etc.
    for f in base.iterdir():
        if f.name.endswith(".md") and f.name.split("_", 1)[-1] == name:
            return f.read_text(encoding="utf-8")
    path = base / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _render_template(name: str, replacements: dict[str, str] | None = None, items: dict[str, list[str] | None] | None = None, texts: dict[str, str | None] | None = None) -> str:
    """Carga un template numerado y reemplaza placeholders.

    Args:
        name: nombre del template (ej: "traits.md", busca 2_traits.md)
        replacements: {#PLACEHOLDER: value} reemplazos simples
        items: {#ITEMS: [str]} listas que se unen con \\n- y se envuelven con HAS_
    """
    tmpl = _load_template(name)
    if not tmpl:
        return ""

    result = tmpl
    if replacements:
        for key, val in replacements.items():
            result = result.replace(key, str(val))

    import re

    def _handle(tag: str, value: str | list[str] | None) -> None:
        nonlocal result
        ms = f"#HAS_{tag}"
        me = f"/HAS_{tag}"
        if value:
            result = result.replace(ms, "").replace(me, "")
            if isinstance(value, list):
                result = result.replace(f"#{tag}_ITEMS", "\n".join(f"- {v}" for v in value))
            else:
                result = result.replace(f"#{tag}_TEXT", str(value))
        else:
            result = re.sub(rf"{re.escape(ms)}\n.*?\n{re.escape(me)}\n?", "", result, flags=re.DOTALL)

    if texts:
        for tag, val in texts.items():
            _handle(tag, val)
    if items:
        for tag, val in items.items():
            _handle(tag, val)

    return result.strip()


def _resolve_identity(self: CharacterCompiler) -> str:
    ident = self.manager.identity
    result = _render_template("identity.md",
        replacements={"#NAME": ident.name or "Unknown", "#ROLE": ident.role or "Unknown"},
        texts={"AGE": ident.age if ident.age and ident.age != "Desconocida" else None,
               "BACKGROUND": ident.background or None,
               "SCENARIO": ident.scenario or None},
    )
    if result:
        return result
    # fallback
    parts = [
        "[IDENTITY]",
        f"Your name is {ident.name or 'Unknown'}.",
        f"Your role is {ident.role or 'Unknown'}.",
    ]
    if ident.age and ident.age != "Desconocida":
        parts.append(f"Your age is {ident.age}.")
    if ident.background:
        parts.append(f"Your background: {ident.background}")
    if ident.scenario:
        parts.append(f"Current scenario: {ident.scenario}")
    parts.append(
        "This is who you are. Never forget it. "
        f"You are {ident.name or 'Unknown'}, not a chatbot."
    )
    return "\n".join(parts)

CharacterCompiler._resolve_identity = _resolve_identity


def _resolve_traits(self: CharacterCompiler) -> str:
    traits_override = self._get_mod_override("traits")
    if traits_override:
        return f"[TRAITS (MODIFIED)]\n{traits_override}"
    p_dna = self.manager.personality_dna
    result = _render_template("traits.md", items={"TRAITS": p_dna.traits if p_dna.traits else None})
    if result:
        return result
    if not p_dna.traits:
        return ""
    return "[TRAITS]\n" + "\n".join(f"- {t}" for t in p_dna.traits)

CharacterCompiler._resolve_traits = _resolve_traits


def _resolve_motivations(self: CharacterCompiler) -> str:
    p_dna = self.manager.personality_dna
    result = _render_template("motivations.md", items={"MOTIVATIONS": p_dna.motivations if p_dna.motivations else None})
    if result:
        return result
    if not p_dna.motivations:
        return ""
    return "[MOTIVATIONS]\n" + "\n".join(f"- {m}" for m in p_dna.motivations)

CharacterCompiler._resolve_motivations = _resolve_motivations


def _resolve_flaws(self: CharacterCompiler) -> str:
    p_dna = self.manager.personality_dna
    result = _render_template("flaws.md", items={"FLAWS": p_dna.flaws if p_dna.flaws else None})
    if result:
        return result
    if not p_dna.flaws:
        return ""
    return "[FLAWS]\n" + "\n".join(f"- {f}" for f in p_dna.flaws)

CharacterCompiler._resolve_flaws = _resolve_flaws


def _resolve_speech(self: CharacterCompiler) -> str:
    speech_override = self._get_mod_override("speech")
    if speech_override:
        return f"[SPEECH STYLE (MODIFIED)]\n{speech_override}"

    sp = self.manager.speech
    result = _render_template("speech.md",
        replacements={"#STYLE": sp.style or "", "#TONE": sp.tone or "", "#VERBOSITY": sp.verbosity or ""},
        texts={"EMOTIONS": ", ".join(sp.emotions) if sp.emotions else None},
    )
    if result:
        return result
    parts = ["[SPEECH STYLE]"]
    if sp.style:
        parts.append(f"Style: {sp.style}")
    if sp.tone:
        parts.append(f"Tone: {sp.tone}")
    if sp.verbosity:
        parts.append(f"Verbosity: {sp.verbosity}")
    if sp.emotions:
        parts.append(f"Base emotions: {', '.join(sp.emotions)}")
    return "\n".join(parts)

CharacterCompiler._resolve_speech = _resolve_speech


def _resolve_few_shot_examples(self: CharacterCompiler) -> str:
    sp = self.manager.speech
    result = _render_template("few_shot.md", items={"EXAMPLES": sp.examples if sp.examples else None})
    if result:
        return result
    if not sp.examples:
        return ""
    return "[FEW SHOT EXAMPLES]\n" + "\n\n".join(sp.examples)

CharacterCompiler._resolve_few_shot_examples = _resolve_few_shot_examples


def _resolve_scenario(self: CharacterCompiler) -> str:
    ident = self.manager.identity
    result = _render_template("scenario.md", texts={"SCENARIO": ident.scenario if ident.scenario else None})
    if result:
        return result
    if ident.scenario:
        return f"[WORLD]\n{ident.scenario}"
    return ""

CharacterCompiler._resolve_scenario = _resolve_scenario


def _resolve_response_style(self: CharacterCompiler) -> str:
    rules = self.manager.rules
    result = _render_template("response_style.md", items={"RESPONSE_STYLE": rules.response_style if rules.response_style else None})
    if result:
        return result
    if not rules.response_style:
        return ""
    return "[RESPONSE STYLE]\n" + "\n".join(f"- {r}" for r in rules.response_style)

CharacterCompiler._resolve_response_style = _resolve_response_style


def _resolve_inner_conflict(self: CharacterCompiler) -> str:
    p_dna = self.manager.personality_dna
    result = _render_template("inner_conflict.md", texts={"INNER_CONFLICT": p_dna.inner_conflict if p_dna.inner_conflict else None})
    if result:
        return result
    if not p_dna.inner_conflict:
        return ""
    return f"[INNER CONFLICT]\n{p_dna.inner_conflict}"

CharacterCompiler._resolve_inner_conflict = _resolve_inner_conflict


def _resolve_emotional_triggers(self: CharacterCompiler) -> str:
    p_dna = self.manager.personality_dna
    result = _render_template("emotional_triggers.md", items={"EMOTIONAL_TRIGGERS": p_dna.emotional_triggers if p_dna.emotional_triggers else None})
    if result:
        return result
    if not p_dna.emotional_triggers:
        return ""
    return "[EMOTIONAL TRIGGERS]\n" + "\n".join(f"- {t}" for t in p_dna.emotional_triggers)

CharacterCompiler._resolve_emotional_triggers = _resolve_emotional_triggers


def _resolve_speech_patterns(self: CharacterCompiler) -> str:
    sp = self.manager.speech
    result = _render_template("speech_patterns.md", items={"SPEECH_PATTERNS": sp.speech_patterns if sp.speech_patterns else None})
    if result:
        return result
    if not sp.speech_patterns:
        return ""
    return "[SPEECH PATTERNS]\n" + "\n".join(f"- {p}" for p in sp.speech_patterns)

CharacterCompiler._resolve_speech_patterns = _resolve_speech_patterns





def _resolve_dna(self: CharacterCompiler, ignore_mods: bool = False) -> str:
    parts = []
    self._try_add(parts, self._resolve_identity())
    self._try_add(parts, self._resolve_traits())
    self._try_add(parts, self._resolve_motivations())
    self._try_add(parts, self._resolve_inner_conflict())
    self._try_add(parts, self._resolve_speech())
    self._try_add(parts, self._resolve_speech_patterns())
    self._try_add(parts, self._resolve_core_rules())
    self._try_add(parts, self._resolve_never_do())
    self._try_add(parts, self._resolve_response_style())
    self._try_add(parts, self._resolve_scenario())
    self._try_add(parts, self._resolve_few_shot_examples())
    self._try_add(parts, self._resolve_flaws())
    self._try_add(parts, self._resolve_roleplay_mode())
    return "\n".join(parts)

CharacterCompiler._resolve_dna = _resolve_dna


def _resolve_core_rules(self: CharacterCompiler) -> str:
    rules = self.manager.rules
    result = _render_template("core_rules.md", items={"CORE_RULES": rules.core_rules if rules.core_rules else None})
    if result:
        return result
    if not rules.core_rules:
        return ""
    return "[CORE RULES — Character Rules]\n" + "\n".join(f"- {r}" for r in rules.core_rules)


CharacterCompiler._resolve_core_rules = _resolve_core_rules


def _resolve_never_do(self: CharacterCompiler) -> str:
    rules = self.manager.rules
    result = _render_template("never_do.md", items={"NEVER_DO": rules.never_do if rules.never_do else None})
    if result:
        return result
    if not rules.never_do:
        return ""
    return "[HARD RULES — Character Restrictions]\nNever:\n" + "\n".join(f"- {r}" for r in rules.never_do)

CharacterCompiler._resolve_never_do = _resolve_never_do


def _resolve_beliefs_contradictions(self: CharacterCompiler) -> str:
    soul_data = self._get_soul_data()
    if not soul_data:
        return ""

    parts = ["[CREENCIAS Y CONTRADICCIONES]"]

    philosophy = soul_data.get("life_philosophy", "")
    if philosophy:
        parts.append(f"Filosofía de Vida: {philosophy}")

    worldview = soul_data.get("worldview", {})
    if worldview:
        parts.append(
            f"Visión del Mundo: "
            f"Optimismo={worldview.get('optimism', 0.5):.1f}, "
            f"Moral={worldview.get('morality', 0.5):.1f}, "
            f"Individualismo={worldview.get('individualism', 0.5):.1f}"
        )

    contradictions = soul_data.get("contradictions", [])
    if contradictions:
        parts.append("Contradicciones Internas:")
        for c in contradictions[:3]:
            parts.append(f"- {c}")

    desires = soul_data.get("hidden_desires", [])
    if desires:
        parts.append("Deseos:")
        for d in desires[:3]:
            parts.append(f"- {d}")

    if len(parts) == 1:
        return ""

    return "\n".join(parts)

CharacterCompiler._resolve_beliefs_contradictions = _resolve_beliefs_contradictions


def _resolve_soul(self: CharacterCompiler) -> str:
    soul_data = self._get_soul_data()
    if not soul_data:
        return ""

    core = soul_data.get("core_identity", {})
    summary = core.get("summary", "")
    archetype = core.get("archetype", "")

    parts = ["[SOUL SYSTEM — Núcleo Psicológico del Personaje]"]

    if summary:
        parts.append(f"Identidad: {summary}")
    if archetype:
        parts.append(f"Arquetipo: {archetype}")

    world = soul_data.get("world_context", {})
    if world:
        parts.append("Contexto del Mundo Natal:")
        w_type_label = "Ficticio/Fantasía" if world.get("world_type") == "fictional" else "Mundo Real"
        parts.append(f"  Tipo: {w_type_label}")
        if world.get("country"):
            parts.append(f"  País/Región: {world.get('country')}")
        if world.get("world_description"):
            parts.append(f"  Entorno: {world.get('world_description')}")

    scars = soul_data.get("emotional_scars", [])
    if scars:
        parts.append("Heridas Emocionales:")
        for s in scars[:3]:
            parts.append(f"- {s[:200]}")

    if len(parts) == 1:
        return ""

    return "\n".join(parts)

CharacterCompiler._resolve_soul = _resolve_soul


def _resolve_state(self: CharacterCompiler) -> str:
    emotion_override = self._get_mod_override("emotion")
    emotion = emotion_override if emotion_override else self.manager.runtime_state.current_emotion
    ps = self.manager.personality_state

    result = _render_template("state.md",
        replacements={"#EMOTION": emotion or "neutral"},
        texts={"PERSONALITY": ps.base_personality or None,
               "BEHAVIOR": ps.behavior_summary or None},
    )
    if result:
        return result

    parts = []
    if emotion_override:
        parts.append(f"[EMOTIONAL STATE]\nCurrent emotion (forced): {emotion_override}")
    else:
        parts.append(f"[EMOTIONAL STATE]\nCurrent emotion: {self.manager.runtime_state.current_emotion}")
    if ps.base_personality:
        parts.append(f"Personality: {ps.base_personality}")
    if ps.behavior_summary:
        parts.append(f"Current behavior: {ps.behavior_summary}")
    return "\n".join(parts)

CharacterCompiler._resolve_state = _resolve_state


def _resolve_relationship(self: CharacterCompiler) -> str:
    rel = self.manager.relationship_state
    result = _render_template("relationship.md",
        replacements={
            "#TRUST": f"{rel.trust_level:.2f}",
            "#FAMILIARITY": f"{rel.familiarity:.2f}",
        },
        texts={"DYNAMICS": ", ".join(rel.dynamics) if rel.dynamics else None},
        items={"MEMORIES": rel.affective_memory if rel.affective_memory else None},
    )
    if result:
        return result
    parts = [
        "[RELATIONSHIP]",
        f"Trust: {rel.trust_level:.2f}",
        f"Familiarity: {rel.familiarity:.2f}",
    ]
    if rel.dynamics:
        parts.append("Dynamics: " + ", ".join(rel.dynamics))
    if rel.affective_memory:
        parts.append("Affective Memory:\n" + "\n".join(f"- {m}" for m in rel.affective_memory))
    return "\n".join(parts)

CharacterCompiler._resolve_relationship = _resolve_relationship


def _resolve_active_mods_description(self: CharacterCompiler) -> str:
    if not self.manager.active_mods:
        return ""
    mods_desc = []
    for m in self.manager.active_mods.values():
        desc = f"- Modificador '{m.id}' (Intensidad {m.intensity})"
        if m.override_value:
            desc += f": Sobreescribe '{m.target_layer}'"
        mods_desc.append(desc)
    return "[MODIFICADORES ACTIVOS]\n" + "\n".join(mods_desc)

CharacterCompiler._resolve_active_mods_description = _resolve_active_mods_description


def _resolve_memory(self: CharacterCompiler) -> str:
    relevant_mems = self.manager.get_relevant_memories()
    if not relevant_mems:
        return ""
    mem_lines = [f"- {m.content}" for m in relevant_mems if m.always_include or m.priority >= 0.5]
    if not mem_lines:
        return ""
    return "[MEMORIA RELEVANTE]\n" + "\n".join(mem_lines)

CharacterCompiler._resolve_memory = _resolve_memory


def _resolve_episode(self: CharacterCompiler) -> str:
    return ""

CharacterCompiler._resolve_episode = _resolve_episode


def _resolve_psychology(self: CharacterCompiler) -> str:
    psych_mgr = getattr(self.manager, '_psychology_manager', None)
    if not psych_mgr or not psych_mgr.is_loaded:
        return ""
    return psych_mgr.get_psychology_block()

CharacterCompiler._resolve_psychology = _resolve_psychology


def _resolve_persona(self: CharacterCompiler) -> str:
    psych_mgr = getattr(self.manager, '_psychology_manager', None)
    if not psych_mgr or not psych_mgr.is_loaded:
        return ""
    return psych_mgr.get_persona_block()

CharacterCompiler._resolve_persona = _resolve_persona
