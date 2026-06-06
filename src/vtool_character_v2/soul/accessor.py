"""accessor.py — RuntimeSoulAccessor: acceso en tiempo de ejecución al Soul."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable, Optional

from ..db.chroma_store import ChromaStore


class RuntimeSoulAccessor:
    def __init__(
        self,
        char_dir: Path,
        soul_generator: Any,
        log_debug_fn: Callable = None,
    ):
        self._char_dir = char_dir
        self._generator = soul_generator
        self._log = log_debug_fn or (lambda t, m: None)

        self._soul_data: Optional[dict] = None
        self._chroma: Optional[ChromaStore] = None
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    def initialize(self) -> bool:
        soul_path = self._char_dir / "soul" / "soul.json"
        if not soul_path.exists():
            soul_path = self._char_dir / "soul.json"
        if not soul_path.exists():
            return False

        try:
            with open(soul_path, "r", encoding="utf-8") as f:
                self._soul_data = json.load(f)
        except Exception:
            return False

        chroma_path = self._char_dir / "soul" / "life_timeline"
        legacy_chroma_path = self._char_dir / "memory" / "life_timeline"
        if not chroma_path.exists() and legacy_chroma_path.exists():
            chroma_path = legacy_chroma_path

        self._chroma = ChromaStore(
            chroma_path,
            "life_timeline",
            log_fn=lambda m: self._log("SOUL", m),
        )
        chroma_ok = self._chroma.initialize()

        self._active = True
        self._log("SOUL", f"Soul accessor active. ChromaDB: {'OK' if chroma_ok else 'N/A'}")

        return True

    def get_soul_block(self) -> str:
        if not self._active or not self._soul_data:
            return ""

        core = self._soul_data.get("core_identity", {})
        summary = core.get("summary", "")
        archetype = core.get("archetype", "")
        philosophy = self._soul_data.get("life_philosophy", "")

        parts = ["[SOUL SYSTEM - Nucleo Psicologico del Personaje]"]

        if summary:
            parts.append(f"Identidad: {summary}")
        if archetype:
            parts.append(f"Arquetipo: {archetype}")
        if philosophy:
            parts.append(f"Filosofia de Vida: {philosophy}")

        world = self._soul_data.get("world_context", {})
        if world:
            parts.append("Contexto del Mundo Natal en el que creció:")
            w_type_label = "Ficticio/Fantasía" if world.get("world_type") == "fictional" else "Mundo Real"
            parts.append(f"- Tipo de Mundo: {w_type_label}")
            parts.append(f"- País/Región/Reino: {world.get('country', 'US')}")
            parts.append(f"- Año de Nacimiento: {world.get('birth_year', 2000)}")
            parts.append(f"- Situación Económica: {world.get('economy', 'stable')}")
            parts.append(f"- Nivel de Ingresos Familiares: {world.get('family_income', 'middle_class')}")
            if world.get("world_type") == "real":
                parts.append(f"- Usar Contexto Histórico Real: {'Sí' if world.get('use_historical_context') else 'No'}")
            else:
                if world.get("fictional_lore_reference"):
                    parts.append(f"- Referencia de Lore/Libro: {world.get('fictional_lore_reference')}")
            if world.get("world_description"):
                parts.append(f"- Descripción y Leyes del Entorno: {world.get('world_description')}")

        scars = self._soul_data.get("emotional_scars", [])
        if scars:
            parts.append("Heridas Emocionales:")
            for s in scars[:3]:
                parts.append(f"- {s[:200]}")

        contradictions = self._soul_data.get("contradictions", [])
        if contradictions:
            parts.append("Contradicciones Internas:")
            for c in contradictions[:3]:
                parts.append(f"- {c}")

        desires = self._soul_data.get("hidden_desires", [])
        if desires:
            parts.append("Deseos Ocultos:")
            for d in desires[:3]:
                parts.append(f"- {d}")

        worldview = self._soul_data.get("worldview", {})
        if worldview:
            parts.append(
                f"Vision del Mundo: "
                f"Optimismo={worldview.get('optimism', 0.5):.1f}, "
                f"Moral={worldview.get('morality', 0.5):.1f}, "
                f"Individualismo={worldview.get('individualism', 0.5):.1f}"
            )

        speech_bias = self._soul_data.get("speech_bias", {})
        if speech_bias:
            style = speech_bias.get("style", "")
            quirks = speech_bias.get("quirks", [])
            if style:
                parts.append(f"Estilo de Habla (Influencia del Alma): {style}")
            if quirks:
                for q in quirks:
                    parts.append(f"- Particularidad: {q}")

        return "\n".join(parts)

    def retrieve_context(self, query: str, top_k: int = 3) -> str:
        if not self._active or not self._chroma or not self._chroma.is_available:
            return ""

        results = self._chroma.search(query, top_k=top_k * 3)
        if not results:
            return ""

        scored = []
        for r in results:
            meta = r.get("metadata", {})
            similarity = r.get("similarity", 0.5)

            try:
                importance = float(meta.get("importance", 0.5))
            except (TypeError, ValueError):
                importance = 0.5

            try:
                emotional_weight = float(meta.get("emotional_weight", 0.5))
            except (TypeError, ValueError):
                emotional_weight = 0.5

            try:
                age_months = int(meta.get("age_months", meta.get("month", 0)))
            except (TypeError, ValueError):
                age_months = 0

            event_age_years = age_months / 12.0

            memory_loss_age = 0
            if self._soul_data:
                memory_loss_age = self._soul_data.get("memory_loss_start_age", 0)

            if event_age_years < 3.0:
                continue
            elif memory_loss_age > 0 and event_age_years < memory_loss_age:
                if importance < 0.75 and emotional_weight < 0.75:
                    continue

            current_age_months = 1200
            if self._soul_data:
                try:
                    current_age_months = int(self._soul_data.get("life_months", 1200))
                except (TypeError, ValueError):
                    current_age_months = 1200

            elapsed_years = max(0.0, (current_age_months - age_months) / 12.0)

            max_importance = max(importance, emotional_weight)
            decay_rate = 0.15 * ((1.0 - max_importance) ** 2)
            retention = math.exp(-decay_rate * elapsed_years)

            if retention < 0.15 and max_importance < 0.75:
                continue

            score = (
                similarity * 0.40 +
                importance * 0.25 +
                emotional_weight * 0.15 +
                retention * 0.20
            )
            scored.append((score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        filtered_results = [r for _, r in scored[:top_k]]

        if not filtered_results:
            return ""

        parts = ["[RECUERDOS VIVIDOS — Recuperados por relevancia al contexto actual]"]
        for r in filtered_results:
            meta = r.get("metadata", {})
            try:
                imp = float(meta.get("importance", 0))
            except (TypeError, ValueError):
                imp = 0.5
            emotion = meta.get("emotion", "neutral")
            age = meta.get("age", "?")
            desc = r.get("document", r.get("description", ""))
            if desc and len(desc) > 10:
                imp_label = "★" if imp > 0.7 else "♦" if imp > 0.5 else "•"
                parts.append(f"{imp_label} (Edad {age}, {emotion}): {desc[:300]}")

        if len(parts) == 1:
            return ""

        return "\n".join(parts)
