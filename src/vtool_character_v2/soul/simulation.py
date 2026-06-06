"""simulation.py — Fase 2: Simulación mes a mes, micro eventos, chaos, interactivo."""

from __future__ import annotations

import json
import random
import uuid
from pathlib import Path
from typing import Optional

from .soul_generator import SoulGenerator, LIFE_STAGES


def _simulate_life(
    self: SoulGenerator,
    age_months: int,
    stage_events: list[dict],
    start_month: int = 0,
    progress_path: Optional[Path] = None,
    progress_callback=None,
    stop_flag=None,
) -> dict:
    events_generated = 0
    last_checkpoint_month = 0

    personality = self._cm.personality_dna
    traits_str = ", ".join(personality.traits)
    flaws_str = ", ".join(personality.flaws)
    motivations_str = ", ".join(personality.motivations)

    events_by_month: dict[int, list[dict]] = {}
    for ev in stage_events:
        m = ev.get("month", 0)
        if m not in events_by_month:
            events_by_month[m] = []
        events_by_month[m].append(ev)

    total_simulated = age_months - start_month
    if total_simulated <= 0:
        return {"status": "complete", "events_generated": len(stage_events)}

    for month in range(start_month, age_months):
        if stop_flag and stop_flag():
            self._save_checkpoint(
                progress_path, month, self._soul_state,
                character_name=self._cm.character_name,
            )
            pct = int((month / age_months) * 100)
            return {
                "status": "paused",
                "progress": pct,
                "current_month": month,
                "events_generated": events_generated,
            }

        year = month // 12

        if month > 0 and month % 12 == 0:
            chaos_event = self._roll_random_chaos_event(year)
            if chaos_event:
                if getattr(self, '_interactive_mode', False) and getattr(self, '_interactive_callback', None):
                    ans = self._interactive_callback(year, [{"type": "chaos_roll", "event": chaos_event}])
                    if ans and ans != "continue":
                        chaos_event["description"] = ans

                mind_res = self._interpret_event_with_character_mind(
                    self._cm.character_name, traits_str, flaws_str, motivations_str, chaos_event
                )
                chaos_event.update(mind_res)
                m = chaos_event["month"]
                if m not in events_by_month:
                    events_by_month[m] = []
                events_by_month[m].append(chaos_event)

        month_events = events_by_month.get(month, [])
        for event in month_events:
            psy_impact = event.get("psychological_impact", {}) or {}
            event_meta = {
                "age": month // 12,
                "month": month,
                "emotion": event.get("emotion", "neutral"),
                "importance": event.get("importance", 0.5),
                "event_type": event.get("type", "unknown"),
                "emotional_weight": min(1.0, event.get("importance", 0.5) * 1.2),
                "psychological_impact": json.dumps(psy_impact),
                "belief_formed": event.get("belief_formed", ""),
                "coping_strategy": event.get("coping_strategy", ""),
            }
            event_id = f"life_{month}_{uuid.uuid4().hex[:8]}"

            if self._chroma:
                self._chroma.add_document(
                    doc_id=event_id,
                    document=event.get("description", ""),
                    metadata=event_meta,
                )

            events_generated += 1
            self._add_event_to_history(event_id, month, event, psy_impact)

            if progress_callback and event.get("importance", 0) > 0.35:
                pct = 5 + int((month / age_months) * 85)
                desc_short = event.get("description", "")
                if len(desc_short) > 75:
                    desc_short = desc_short[:72] + "..."

                ev_type = event.get("type", "unknown").upper()
                emotion = event.get("emotion", "neutral")

                progress_callback(min(pct, 90), f"[Age {year} | {ev_type} | {emotion}] {desc_short}")

                if event.get("belief_formed"):
                    progress_callback(min(pct, 90), f"  ↳ [Belief] {event.get('belief_formed')[:75]}")
                if event.get("coping_strategy"):
                    progress_callback(min(pct, 90), f"  ↳ [Coping] developed: {event.get('coping_strategy')}")

            if event.get("importance", 0) > 0.65:
                self._process_reflection(event, self._soul_state)

                if progress_callback and self._soul_state.internal_conflicts:
                    pct = 5 + int((month / age_months) * 85)
                    thought = self._soul_state.internal_conflicts[-1].get("thought", "")
                    if thought:
                        thought_short = thought
                        if len(thought_short) > 70:
                            thought_short = thought_short[:67] + "..."
                        progress_callback(min(pct, 90), f"  ↳ [Reflection] {thought_short}")

            if event.get("belief_formed"):
                self._soul_state.beliefs[event_id] = {
                    "content": event.get("belief_formed", ""),
                    "strength": event.get("importance", 0.5),
                    "source_event": event.get("description", "")[:100],
                }

            ev_type = event.get("type", "")
            if ev_type == "economic":
                self._soul_state.economic_state["stability"] = max(
                    0.0, min(1.0,
                        self._soul_state.economic_state["stability"] +
                        random.uniform(-0.2, 0.2)
                    )
                )

        if not month_events and random.random() < 0.08:
            micro = self._generate_micro_event(month)
            if micro:
                micro_meta = {
                    "age": month // 12,
                    "month": month,
                    "emotion": micro.get("emotion", "neutral"),
                    "importance": micro.get("importance", 0.2),
                    "event_type": micro.get("type", "social"),
                    "emotional_weight": 0.2,
                }
                event_id = f"micro_{month}_{uuid.uuid4().hex[:8]}"
                if self._chroma:
                    self._chroma.add_document(
                        doc_id=event_id,
                        document=micro.get("description", ""),
                        metadata=micro_meta,
                    )
                events_generated += 1
                self._add_event_to_history(event_id, month, micro, {})

        if month % 12 == 11 and getattr(self, '_interactive_mode', False) and getattr(self, '_interactive_callback', None):
            year_start_month = year * 12
            year_events = []
            for m in range(year_start_month, year_start_month + 12):
                year_events.extend(events_by_month.get(m, []))

            cmd = self._interactive_callback(year, year_events)
            if cmd and cmd.startswith("inject:"):
                parts = cmd.split(":", 2)
                inj_type = parts[1]
                inj_desc = parts[2]

                inj_event = {
                    "month": month,
                    "type": inj_type,
                    "description": inj_desc,
                    "importance": 0.8,
                    "people_involved": [],
                    "location": self._country,
                    "stage": next((s["name"] for s in LIFE_STAGES if s["start"] <= month < s["end"]), "adulthood"),
                }

                mind_res = self._interpret_event_with_character_mind(
                    self._cm.character_name, traits_str, flaws_str, motivations_str, inj_event
                )
                inj_event.update(mind_res)

                if month not in events_by_month:
                    events_by_month[month] = []
                events_by_month[month].append(inj_event)

                psy_impact = inj_event.get("psychological_impact", {}) or {}
                event_meta = {
                    "age": month // 12,
                    "month": month,
                    "emotion": inj_event.get("emotion", "neutral"),
                    "importance": inj_event.get("importance", 0.8),
                    "event_type": inj_event.get("type", "unknown"),
                    "emotional_weight": 0.9,
                    "psychological_impact": json.dumps(psy_impact),
                    "belief_formed": inj_event.get("belief_formed", ""),
                    "coping_strategy": inj_event.get("coping_strategy", ""),
                }
                event_id = f"injected_{month}_{uuid.uuid4().hex[:8]}"
                if self._chroma:
                    self._chroma.add_document(doc_id=event_id, document=inj_event.get("description", ""), metadata=event_meta)
                events_generated += 1
                self._add_event_to_history(event_id, month, inj_event, psy_impact)

                if inj_event.get("importance", 0) > 0.65:
                    self._process_reflection(inj_event, self._soul_state)
                if inj_event.get("belief_formed"):
                    self._soul_state.beliefs[event_id] = {
                        "content": inj_event.get("belief_formed", ""),
                        "strength": inj_event.get("importance", 0.8),
                        "source_event": inj_event.get("description", "")[:100],
                    }

        if month > 0 and month % 12 == 0:
            self._apply_identity_drift(month, self._soul_state)

        if progress_callback and month % max(1, age_months // 100) == 0:
            pct = 5 + int((month / age_months) * 85)
            progress_callback(min(pct, 90), f"Age {year}: Processing life...")

        if progress_path and (month - last_checkpoint_month >= 6):
            self._save_checkpoint(
                progress_path, month, self._soul_state,
                character_name=self._cm.character_name,
            )
            last_checkpoint_month = month

    return {"status": "complete", "events_generated": events_generated}

SoulGenerator._simulate_life = _simulate_life


def _generate_micro_event(self: SoulGenerator, month: int) -> Optional[dict]:
    if random.random() < 0.3:
        return None

    micro_types = ["social", "hobby", "reflection", "discovery"]
    ev_type = random.choice(micro_types)
    emotions = ["contentment", "curiosity", "boredom", "amusement", "nostalgia", "melancholy"]

    descriptions = [
        f"Spent a quiet afternoon reflecting on life (age {month//12})",
        "Had an unexpected conversation with a stranger that made me think",
        "Discovered a new interest while browsing",
        "Felt a sudden wave of nostalgia thinking about the past",
        "Witnessed something beautiful that lifted the mood",
        "A small disagreement reminded me of past conflicts",
    ]

    return {
        "month": month,
        "type": ev_type,
        "description": random.choice(descriptions),
        "importance": round(random.uniform(0.1, 0.35), 2),
        "emotion": random.choice(emotions),
        "people_involved": [],
        "location": "unknown",
    }

SoulGenerator._generate_micro_event = _generate_micro_event
