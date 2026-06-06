"""events.py — Fase 2-5: Life Director, Character Mind, generación de eventos."""

from __future__ import annotations

import json
import random
from typing import Optional

from .soul_generator import SoulGenerator, LIFE_STAGES, EVENT_TYPES, SOUL_GENERATION_SYSTEM_PROMPT


def _interpret_event_with_character_mind(
    self: SoulGenerator,
    character_name: str,
    traits_str: str,
    flaws_str: str,
    motivations_str: str,
    ev: dict,
) -> dict:
    if not self._llm_client or not getattr(self._llm_client, 'is_loaded', False):
        rule_based = self._generate_reflection_rule_based(ev, self._soul_state)
        return {
            "emotion": ev.get("emotion", "neutral"),
            "psychological_impact": rule_based.get("emotional_shift", {}),
            "belief_formed": rule_based.get("belief_change", ""),
            "reflection": rule_based.get("thought", ""),
            "coping_strategy": rule_based.get("coping_strategy", ""),
        }

    prompt = (
        f"Eres la Mente Emocional (Character Mind) de {character_name}.\n"
        f"Tu tarea es interpretar subjetivamente un evento objetivo que te ocurrió, determinando "
        f"cómo impacta tu psique y qué emociones y creencias dejas grabadas.\n\n"
        f"Tus rasgos innatos (Genome) y DNA:\n"
        f"- Rasgos: {traits_str}\n"
        f"- Defectos/Miedos: {flaws_str}\n"
        f"- Motivaciones: {motivations_str}\n\n"
        f"EVENTO OBJETIVO A INTERPRETAR:\n"
        f"- Mes: {ev.get('month', 0)} (Edad {ev.get('month', 0)//12} años)\n"
        f"- Tipo: {ev.get('type', 'social')}\n"
        f"- Qué pasó: {ev.get('description', '')}\n"
        f"- Importancia: {ev.get('importance', 0.5)}\n\n"
        "Determina:\n"
        "1. La emoción subjetiva predominante que sentiste (joy, sadness, anger, fear, surprise, disgust, trust, etc.).\n"
        "2. El impacto psicológico (psychological_impact): un dict de cambios sutiles (-0.2 a 0.2) en tus ejes: openness, conscientiousness, extraversion, agreeableness, neuroticism, trust_in_people, optimism, sense_of_control, meaningfulness, must_appear_confident.\n"
        "3. La creencia que formaste (belief_formed) como resultado.\n"
        "4. Tu reflexión íntima sobre lo sucedido (reflection).\n"
        "5. El mecanismo de defensa o estrategia de afrontamiento (coping_strategy) que desarrollaste.\n\n"
        "Responde UNICAMENTE con un JSON con este formato:\n"
        "{\n"
        '  "emotion": "<emocion>",\n'
        '  "psychological_impact": {"neuroticism": 0.05, "trust_in_people": -0.1},\n'
        '  "belief_formed": "<creencia formada>",\n'
        '  "reflection": "<reflexion intima>",\n'
        '  "coping_strategy": "<mecanismo>"\n'
        "}\n"
        "Recuerda: Responde SOLO con el JSON puro."
    )

    try:
        result = self._llm_client.generate(
            messages=[
                {"role": "system", "content": "Eres la mente emocional del personaje. Responde SOLO con JSON válido sin markdown."},
                {"role": "user", "content": prompt},
            ],
            stream=False,
            max_tokens=512,
            temperature=0.8,
        )
        text = result["choices"][0]["message"].get("content", "")
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            data = json.loads(text[start:end])
            return data
    except Exception as e:
        self._log_warning(f"Error en Character Mind para evento: {e}")

    rule_based = self._generate_reflection_rule_based(ev, self._soul_state)
    return {
        "emotion": ev.get("emotion", "neutral"),
        "psychological_impact": rule_based.get("emotional_shift", {}),
        "belief_formed": rule_based.get("belief_change", ""),
        "reflection": rule_based.get("thought", ""),
        "coping_strategy": rule_based.get("coping_strategy", ""),
    }

SoulGenerator._interpret_event_with_character_mind = _interpret_event_with_character_mind


def _roll_random_chaos_event(self: SoulGenerator, age_years: int) -> Optional[dict]:
    roll = random.random()
    p_social = 0.20
    p_strong = 0.08
    p_life = 0.02

    if hasattr(self, '_genome') and self._genome:
        if self._genome.impulsivity > 0.7 or self._genome.risk_aversion < 0.3:
            p_strong += 0.04
        if self._genome.sociability > 0.7:
            p_social += 0.05

    if getattr(self, '_economy', 'stable') in ('poor', 'crisis'):
        p_life += 0.04
        p_strong += 0.02
    if getattr(self, '_family_income', 'middle_class') == 'poor':
        p_life += 0.05

    if roll < p_life:
        event_type = random.choice(["economic", "trauma", "loss", "crime", "existential"])
        importance = round(random.uniform(0.75, 0.95), 2)
        desc_pool = {
            "economic": f"Extreme financial hardship hit the family in {self._country} due to national crisis.",
            "trauma": "A major political instability forced relocation, leaving almost everything behind.",
            "loss": "Faced severe poverty and food shortages during a harsh economic winter.",
            "crime": "Witnessed or fell victim to a serious neighborhood crime.",
            "existential": "A historic event or epidemic swept through the region, disrupting daily life.",
        }
        desc = desc_pool.get(event_type, "A major life-defining event occurred.")
    elif roll < p_life + p_strong:
        event_type = random.choice(["health", "accident", "trauma", "violence", "loss"])
        importance = round(random.uniform(0.55, 0.80), 2)
        desc_pool = {
            "health": "Suffered a serious illness that kept them bedridden for months.",
            "accident": "Survived a dangerous accident that left physical and emotional scars.",
            "trauma": "Experienced a deeply distressing event at school or home.",
            "violence": "Confronted a violent confrontation in the local neighborhood.",
            "loss": "Mourned the sudden loss of someone or something highly valued.",
        }
        desc = desc_pool.get(event_type, "A strong, impactful event occurred.")
    elif roll < p_life + p_strong + p_social:
        event_type = random.choice(["betrayal", "romantic", "mentorship", "rivalry", "friendship"])
        importance = round(random.uniform(0.35, 0.65), 2)
        desc_pool = {
            "betrayal": "Discovered a close friend had shared private secrets.",
            "romantic": "Experienced the intense highs and lows of a first crush/romance.",
            "mentorship": "Met an older figure who offered guidance and new perspectives.",
            "rivalry": "Engaged in a fierce rivalry at school or work.",
            "friendship": "Formed an incredibly close bond with someone who shared their worldview.",
        }
        desc = desc_pool.get(event_type, "A significant social event occurred.")
    else:
        return None

    event_year = self._birth_year + age_years
    desc += f" (Year {event_year} in {self._country})"

    return {
        "month": age_years * 12 + random.randint(0, 11),
        "type": event_type,
        "description": desc,
        "importance": importance,
        "people_involved": [],
        "location": self._country,
        "stage": next((s["name"] for s in LIFE_STAGES if s["start"] <= age_years * 12 < s["end"]), "adulthood"),
    }

SoulGenerator._roll_random_chaos_event = _roll_random_chaos_event


def _pre_generate_stage_events(
    self: SoulGenerator,
    identity, personality, rules, speech,
    age_months: int,
    progress_callback,
    start_month: int = 0,
) -> list[dict]:
    if not self._llm_client or not getattr(self._llm_client, 'is_loaded', False):
        self._log_warning("No hay LLM disponible. Usando generacion aleatoria.")
        return self._generate_random_events(age_months, start_month)

    self._has_llm = True
    all_events = []

    identity_name = getattr(identity, "name", "unknown")
    identity_background = getattr(identity, "background", "")

    traits_str = ", ".join(personality.traits)
    flaws_str = ", ".join(personality.flaws)
    motivations_str = ", ".join(personality.motivations)

    total_stages = sum(
        1 for s in LIFE_STAGES
        if s["start"] < age_months and s["end"] > start_month
    )
    stage_idx = 0

    for stage in LIFE_STAGES:
        if stage["start"] >= age_months:
            break
        if stage["end"] <= start_month:
            continue

        stage_idx += 1
        stage_start = max(stage["start"], start_month)
        stage_end = min(stage["end"], age_months)
        stage_years_start = stage_start // 12
        stage_years_end = stage_end // 12

        if progress_callback:
            base_progress = 5 + int((stage_idx / total_stages) * 70)
            progress_callback(
                base_progress,
                f"[Life Director] Generating stage {stage['label']} (age {stage_years_start}-{stage_years_end})...",
            )

        world_type = getattr(self, "_world_type", "real")
        use_historical = getattr(self, "_use_historical_context", False)
        fictional_lore = getattr(self, "_fictional_lore_reference", "")

        world_context_prompt = ""
        if world_type == "real":
            world_context_prompt = (
                f"El mundo de este personaje es el MUNDO REAL.\n"
                f"País/Región: {getattr(self, '_country', 'US')}\n"
                f"Periodo de tiempo de esta etapa: Años {getattr(self, '_birth_year', 2000) + stage_years_start} a {getattr(self, '_birth_year', 2000) + stage_years_end}.\n"
            )
            if use_historical:
                world_context_prompt += (
                    "DEBES basar e integrar los eventos del personaje de manera estricta y profunda en la situación histórica, crisis, tensiones políticas y acontecimientos reales que ocurrieron en ese país/región durante esos años exactos (por ejemplo, si el país es Cuba y la época son los años 1990, debes integrar los sucesos de la crisis del Período Especial en Cuba: escasez de alimentos, apagones constantes, tensiones sociales y familiares; si es EE.UU. en los años 2000, los ataques del 11 de septiembre, etc.). Las vivencias del personaje y sus recuerdos deben reflejar fielmente la atmósfera real de esa época y región."
                )
            else:
                world_context_prompt += "Usa el contexto general de este país, pero no es estrictamente obligatorio apegarse a acontecimientos históricos específicos."
        else:
            world_context_prompt = (
                f"El mundo de este personaje es un MUNDO DE FICCIÓN/FANTASÍA.\n"
                f"Reino/Mundo/Región: {getattr(self, '_country', 'US')}\n"
                f"Periodo de tiempo en el mundo ficticio: Años o ciclo {getattr(self, '_birth_year', 2000) + stage_years_start} a {getattr(self, '_birth_year', 2000) + stage_years_end}.\n"
            )
            if fictional_lore:
                world_context_prompt += (
                    f"DEBES basar e integrar los eventos en las leyes de la física/magia, lore y acontecimientos descritos de este mundo ficticio (Referencia de Lore/Libro: {fictional_lore}). "
                    f"Los recuerdos y vivencias cotidianas del personaje deben construirse sobre esta base y lore del mundo ficticio en esta era."
                )
            else:
                world_context_prompt += "Usa el contexto del mundo de fantasía sugerido por el nombre o el escenario, integrándolo en la vida cotidiana del personaje."

        director_prompt = (
            f"Eres el Director de Vida (Life Director), un observador frío y lógico de la causalidad humana. "
            f"Tu tarea es decidir qué eventos objetivos ocurren en la vida de {identity_name} "
            f"para la etapa {stage['label']} (Edad {stage_years_start} a {stage_years_end} años).\n\n"
            f"TIPO DE MUNDO Y CONTEXTO HISTÓRICO:\n{world_context_prompt}\n\n"
            f"Situación económica local: {getattr(self, '_economy', 'stable')}\n"
            f"Ingresos de la familia: {getattr(self, '_family_income', 'middle_class')}\n"
            f"Descripción y reglas especiales del mundo: {getattr(self, '_world_description', 'Ninguna')}\n"
            f"Antecedentes del personaje: {identity_background}\n"
            f"DNA/Traits: {traits_str}\n\n"
            "Genera una lista de eventos puramente OBJETIVOS que suceden. "
            "NO menciones emociones, ni cambios psicológicos, ni heridas en la descripción. "
            "Solo describe lo que pasó físicamente en el mundo real, la fecha (en meses desde nacimiento), "
            "el tipo de evento, "
            "la importancia (0.0 a 1.0), y el lugar/personas involucradas.\n"
            "IMPORTANTE: Si necesitas que el orquestador humano defina el resultado de una acción aleatoria, "
            "especifique un detalle familiar o responda una duda de lore específica para evitar alucinaciones, "
            "añade el campo opcional 'query_for_orchestrator' en el JSON del evento con la pregunta. La simulación "
            "se detendrá para preguntarle y el resultado se inyectará en la descripción del evento.\n\n"
            "Responde UNICAMENTE con un JSON con este formato:\n"
            "{\n"
            '  "events": [\n'
            "    {\n"
            '      "month": <int>,\n'
            '      "type": "<tipo>",\n'
            '      "description": "<descripción física y factual del suceso>",\n'
            '      "importance": <0.0-1.0>,\n'
            '      "location": "<lugar>",\n'
            '      "people_involved": ["<persona>"],\n'
            '      "query_for_orchestrator": "<pregunta opcional al orquestador>"\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        try:
            result = self._llm_client.generate(
                messages=[
                    {"role": "system", "content": SOUL_GENERATION_SYSTEM_PROMPT},
                    {"role": "user", "content": director_prompt},
                ],
                stream=False,
                max_tokens=1536,
                temperature=0.8,
            )
            response_text = result["choices"][0]["message"].get("content", "")
            stage_events = self._parse_events_from_json(response_text)

            if progress_callback:
                progress_callback(base_progress + 1, f"[Character Mind] Analyzing {len(stage_events)} events for {stage['label']}...")

            interpreted_events = []
            for i, ev in enumerate(stage_events):
                ev["stage"] = stage["name"]
                ev["month"] = max(stage_start, min(stage_end - 1, ev.get("month", stage_start)))

                query = ev.pop("query_for_orchestrator", None)
                if query and getattr(self, '_interactive_mode', False) and getattr(self, '_interactive_callback', None):
                    ans = self._interactive_callback(ev["month"] // 12, [{"type": "query", "query": query, "event": ev}])
                    if ans:
                        orig_desc = ev.get("description", "")
                        ev["description"] = f"{orig_desc} (Orchestrator details: {ans})"

                if progress_callback:
                    ev_type = ev.get("type", "event")
                    progress_callback(base_progress + 1, f"[Character Mind] Interpreting event {i+1}/{len(stage_events)} (Age {ev['month']//12} | {ev_type})...")

                mind_result = self._interpret_event_with_character_mind(
                    identity_name, traits_str, flaws_str, motivations_str, ev
                )
                ev.update(mind_result)
                interpreted_events.append(ev)

            all_events.extend(interpreted_events)

        except Exception as e:
            self._log_warning(f"Error en Life Director para {stage['name']}: {e}")
            fallback = self._generate_random_events_for_stage(stage, age_months)
            all_events.extend(fallback)

    return all_events

SoulGenerator._pre_generate_stage_events = _pre_generate_stage_events


def _parse_events_from_json(self: SoulGenerator, text: str) -> list[dict]:
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end <= start:
            return []
        data = json.loads(text[start:end])
        raw_events = data.get("events", [])
        if isinstance(raw_events, list):
            return raw_events
        return []
    except (json.JSONDecodeError, Exception):
        return []

SoulGenerator._parse_events_from_json = _parse_events_from_json


def _generate_random_events(self: SoulGenerator, age_months: int, start_month: int = 0) -> list[dict]:
    events = []
    for stage in LIFE_STAGES:
        if stage["start"] >= age_months:
            break
        if stage["end"] <= start_month:
            continue
        stage_events = self._generate_random_events_for_stage(stage, age_months, start_month)
        events.extend(stage_events)
    return events

SoulGenerator._generate_random_events = _generate_random_events


def _generate_random_events_for_stage(
    self: SoulGenerator, stage: dict, age_months: int, start_month: int = 0,
) -> list[dict]:
    events = []
    stage_start = max(stage["start"], start_month)
    stage_end = min(stage["end"], age_months)
    density = stage["event_density"]
    num_events = max(1, int((stage_end - stage_start) / 12 * density))

    for _ in range(num_events):
        month = random.randint(stage_start, max(stage_start, stage_end - 1))
        ev_type = random.choice(EVENT_TYPES)
        importance = round(random.uniform(0.3, 0.9), 2)
        emotions = ["joy", "sadness", "anger", "fear", "surprise", "disgust", "trust", "anticipation"]
        event = {
            "month": month,
            "type": ev_type,
            "description": f"A {ev_type} event occurred (age {month//12}y {month%12}m)",
            "importance": importance,
            "emotion": random.choice(emotions),
            "people_involved": [],
            "location": "unknown",
            "personality_impact": "slight change",
            "stage": stage["name"],
        }
        events.append(event)
    return events

SoulGenerator._generate_random_events_for_stage = _generate_random_events_for_stage
