"""
Soul System para vtool_character_v2 — Clase base y API pública.

Genera una vida simulada persistente para personajes.
Las fases de generación se implementan en módulos hermanos.

Arquitectura:
  Fase 1  — Inicialización del ser (desde DNA/Genome)
  Fase 2  — Simulación temporal mes a mes
  Fase 3  — Context Engine
  Fase 4  — Event Probability Engine
  Fase 5  — Generación de eventos por etapa via LLM
  Fase 6  — Reflection Engine
  Fase 7  — Relationship Evolution
  Fase 8  — Identity Drift
  Fase 9  — Semantic Compression -> soul.json
  Fase 10 — Retrieval Architecture
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Protocol


try:
    from ..db.chroma_store import ChromaStore, HAS_CHROMA
except ImportError:
    HAS_CHROMA = False


class LLMClient(Protocol):
    """Protocolo para clientes LLM usados por SoulGenerator.

    Cualquier objeto que implemente estos métodos puede usarse como
    backend de generación de texto. vtool_llama_v2.VToolLlamaV2
    es compatible mediante un adapter.
    """

    @property
    def is_loaded(self) -> bool:
        """Indica si el modelo está cargado y listo para generar."""
        ...

    def generate(self, messages: list[dict], **kwargs) -> dict:
        """Genera una respuesta del modelo.

        Args:
            messages: lista de dicts con role y content
            **kwargs: max_tokens, temperature, stream, etc.

        Returns:
            dict con formato {"choices": [{"message": {"content": str}}]}
        """
        ...


# ======================================================================
# CONSTANTES
# ======================================================================

EVENT_TYPES = [
    "family", "romantic", "friendship", "education", "work",
    "economic", "health", "trauma", "accident", "violence",
    "loss", "travel", "success", "failure", "crime",
    "technology", "political", "existential", "social", "hobby",
    "skill_growth", "discrimination", "spiritual", "betrayal",
    "discovery", "responsibility", "rivalry", "mentorship",
]

LIFE_STAGES = [
    {"name": "early_childhood", "start": 0, "end": 72,
     "label": "First Years (0-6)", "event_density": 0.15},
    {"name": "middle_childhood", "start": 72, "end": 156,
     "label": "Childhood (6-13)", "event_density": 0.20},
    {"name": "adolescence", "start": 156, "end": 228,
     "label": "Adolescence (13-19)", "event_density": 0.30},
    {"name": "young_adult", "start": 228, "end": 360,
     "label": "Young Adult (20-30)", "event_density": 0.35},
    {"name": "adulthood", "start": 360, "end": 600,
     "label": "Adulthood (30-50)", "event_density": 0.30},
    {"name": "maturity", "start": 600, "end": 1200,
     "label": "Maturity (50+)", "event_density": 0.25},
]

DEFAULT_EVENT_WEIGHTS = {
    "family": 0.5, "romantic": 0.3, "friendship": 0.5,
    "education": 0.4, "work": 0.3, "economic": 0.3,
    "health": 0.2, "trauma": 0.1, "accident": 0.1,
    "violence": 0.1, "loss": 0.1, "travel": 0.2,
    "success": 0.2, "failure": 0.2, "crime": 0.05,
    "technology": 0.2, "political": 0.1, "existential": 0.15,
    "social": 0.4, "hobby": 0.3, "skill_growth": 0.3,
    "discrimination": 0.1, "spiritual": 0.15, "betrayal": 0.1,
    "discovery": 0.25, "responsibility": 0.2, "rivalry": 0.15,
    "mentorship": 0.2,
}

SOUL_GENERATION_SYSTEM_PROMPT = (
    "Eres un escritor de ficcion especializado en crear vidas humanas "
    "profundas, realistas y psicologicamente complejas. "
    "Generas eventos de vida detallados, emocionalmente resonantes, "
    "con contradicciones, ambiguedad e imperfeccion. "
    "Cada evento debe sentirse real, no generico. "
    "DEBES responder UNICAMENTE con JSON valido, sin markdown, "
    "sin explicaciones, solo el JSON puro."
)


def _identity_age_to_months(identity) -> int:
    """Convierte la edad desde identity a meses."""
    try:
        age_str = getattr(identity, "age", "25")
        age = int(age_str) if age_str else 25
    except (ValueError, TypeError):
        age = 25
    return age * 12


# ======================================================================
# ESTADO DEL ALMA
# ======================================================================

@dataclass
class _SoulState:
    age_months: int = 0
    core_traits: dict = field(default_factory=lambda: {
        "openness": 0.5, "conscientiousness": 0.5,
        "extraversion": 0.5, "agreeableness": 0.5,
        "neuroticism": 0.5,
    })
    beliefs: dict = field(default_factory=dict)
    traumas: list = field(default_factory=list)
    social_links: list = field(default_factory=list)
    skills: dict = field(default_factory=dict)
    economic_state: dict = field(default_factory=lambda: {
        "level": "working_class", "stability": 0.5,
    })
    mental_state: dict = field(default_factory=lambda: {
        "happiness": 0.6, "anxiety": 0.3, "trust": 0.5,
        "self_esteem": 0.5, "resilience": 0.5,
    })
    worldview: dict = field(default_factory=lambda: {
        "optimism": 0.5, "morality": 0.5,
        "individualism": 0.5, "traditionalism": 0.5,
    })
    goals: list = field(default_factory=list)
    internal_conflicts: list = field(default_factory=list)
    values: list = field(default_factory=list)
    fears: list = field(default_factory=list)
    education_stage: str = "none"
    current_relationship: Optional[dict] = None
    event_count: int = 0
    last_reflection_month: int = 0
    memory_loss_start_age: int = 0


# ======================================================================
# GENERADOR DE ALMA
# ======================================================================

class SoulGenerator:
    """
    Genera una vida simulada completa para un personaje.
    Los métodos de cada fase se asignan desde módulos hermanos.
    """

    def __init__(
        self,
        character_manager: Any,
        config: Any,
        llm_client: Optional[LLMClient] = None,
        log_debug_fn: Callable = None,
        log_info_fn: Callable = None,
        log_warning_fn: Callable = None,
    ):
        self._cm = character_manager
        self._llm_client = llm_client
        self._config = config
        self._log_debug = log_debug_fn or (lambda t, m: None)
        self._log_info = log_info_fn or (lambda m: None)
        self._log_warning = log_warning_fn or (lambda m: None)

        self._chroma: Optional[ChromaStore] = None
        self._soul_state: Optional[_SoulState] = None
        self._char_dir: Optional[Path] = None
        self._has_llm: bool = False
        self._seed: Optional[int] = None

    # ==================================================================
    # API PUBLICA
    # ==================================================================

    def generate_soul(
        self,
        character_name: str,
        force_regenerate: bool = False,
        seed: Optional[int] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        stop_flag: Optional[Callable[[], bool]] = None,
        country: str = "US",
        birth_year: int = 2000,
        economy: str = "stable",
        family_income: str = "middle_class",
        world_description: str = "",
        start_age_years: int = 0,
        memory_loss_start_age: int = 0,
        interactive_mode: bool = False,
        interactive_callback: Optional[Callable[[int, list[dict]], str]] = None,
        world_type: str = "real",
        use_historical_context: bool = False,
        fictional_lore_reference: str = "",
        max_age_years: Optional[int] = None,
        save_events_history: bool = True,
    ) -> dict:
        self._seed = seed
        if seed is not None:
            random.seed(seed)

        self._country = country
        self._birth_year = birth_year
        self._economy = economy
        self._family_income = family_income
        self._world_description = world_description
        self._interactive_mode = interactive_mode
        self._interactive_callback = interactive_callback
        self._world_type = world_type
        self._use_historical_context = use_historical_context
        self._fictional_lore_reference = fictional_lore_reference
        self._save_events_history = save_events_history

        char_dir = self._cm._base_dir / character_name
        if not char_dir.exists() or not (char_dir / "dna").exists():
            raise ValueError(f"Personaje '{character_name}' no encontrado")

        self._char_dir = char_dir
        soul_dir = char_dir / "soul"
        soul_dir.mkdir(parents=True, exist_ok=True)
        soul_path = soul_dir / "soul.json"
        legacy_soul_path = char_dir / "soul.json"
        progress_path = soul_dir / "soul_progress.json"

        existing_soul_path = soul_path if soul_path.exists() else legacy_soul_path
        if existing_soul_path.exists() and not force_regenerate:
            raise ValueError(
                f"Soul ya existe para '{character_name}'. "
                "Usa force_regenerate=True para regenerar."
            )

        self._cm.load_character(character_name)
        identity = self._cm.identity
        personality = self._cm.personality_dna
        speech = self._cm.speech
        rules = self._cm.rules

        if max_age_years is not None and max_age_years > 0:
            age_months = max_age_years * 12
        else:
            age_months = _identity_age_to_months(identity)

        if age_months < 12:
            raise ValueError(f"Personaje demasiado joven ({age_months//12} anios) para generar alma.")

        self._chroma = ChromaStore(soul_dir / "life_timeline", "life_timeline",
                                    log_fn=lambda m: self._log_debug("SOUL", m))
        chroma_ok = self._chroma.initialize()

        if not chroma_ok:
            self._log_warning("ChromaDB no disponible. Continuando sin busqueda semantica.")

        if force_regenerate:
            if self._chroma:
                self._chroma.clear()
            if soul_path.exists():
                soul_path.unlink()
            if legacy_soul_path.exists():
                legacy_soul_path.unlink()

            # Limpiar historial — prioriza _memory, soporta legacy memory/
            for p in [char_dir / "_memory" / "life_events.json",
                      char_dir / "memory" / "life_events.json"]:
                if p.exists():
                    try:
                        p.unlink()
                    except Exception:
                        pass

        self._genome = self._load_genome(char_dir, personality)
        self._soul_state = self._init_soul_state(
            identity, personality, speech, rules, age_months,
            genome=self._genome,
        )

        if memory_loss_start_age > 0:
            self._soul_state.memory_loss_start_age = memory_loss_start_age

        if progress_callback:
            progress_callback(1, "Initializing soul state...")

        current_month = 0
        if start_age_years > 0:
            current_month = start_age_years * 12
            self._soul_state.age_months = current_month

        if progress_path.exists():
            try:
                cp = self._load_checkpoint(progress_path)
                if cp and cp.get("character_name") == character_name:
                    current_month = cp.get("current_month", 0)
                    self._restore_soul_state(cp.get("soul_state", {}))
                    if self._chroma and cp.get("chroma_ready"):
                        self._chroma.initialize()
                    self._log_info(f"Reanudando generacion desde mes {current_month}")
                    if progress_callback:
                        pct = int((current_month / age_months) * 100)
                        progress_callback(max(pct, 1), f"Resuming from month {current_month}")
            except Exception as e:
                self._log_warning(f"Error cargando checkpoint: {e}")
                if start_age_years > 0:
                    current_month = start_age_years * 12
                    self._soul_state.age_months = current_month
                else:
                    current_month = 0

        stage_events = self._pre_generate_stage_events(
            identity, personality, rules, speech,
            age_months, progress_callback,
            start_month=current_month,
        )

        result = self._simulate_life(
            age_months=age_months,
            stage_events=stage_events,
            start_month=current_month,
            progress_path=progress_path,
            progress_callback=progress_callback,
            stop_flag=stop_flag,
        )

        if result["status"] == "paused":
            return result

        if progress_callback:
            progress_callback(95, "Compressing soul essence...")

        compressed = self._compress_soul(result["events_generated"])
        self._save_soul_json(soul_path, compressed)
        self._cleanup_checkpoints(progress_path)

        if progress_callback:
            progress_callback(100, "Soul generation complete!")

        self._log_info(f"Soul generado para '{character_name}' con {result['events_generated']} eventos.")

        return {
            "status": "complete",
            "character": character_name,
            "soul_path": str(soul_path),
            "events_generated": result["events_generated"],
            "life_months": age_months,
            "genome": asdict(self._genome) if hasattr(self, '_genome') and self._genome else None,
        }

    def retrieve_relevant_memories(
        self,
        query: str,
        top_k: int = 5,
        importance_min: float = 0.0,
        emotion_filter: Optional[str] = None,
    ) -> list[dict]:
        if not self._chroma or not self._chroma.is_available:
            return []

        where_clause = {}
        if importance_min > 0:
            where_clause["importance"] = {"$gte": importance_min}
        if emotion_filter:
            where_clause["emotion"] = emotion_filter

        raw = self._chroma.search(query, top_k=top_k * 3, where=where_clause or None)

        scored = []
        for ev in raw:
            meta = ev.get("metadata", {})
            similarity = ev.get("similarity", 0.5)
            importance = meta.get("importance", 0.5)
            emotional_weight = meta.get("emotional_weight", 0.5)
            age_months = meta.get("age_months", meta.get("month", 0))

            event_age_years = age_months / 12.0

            memory_loss_age = 0
            if self._soul_state:
                memory_loss_age = self._soul_state.memory_loss_start_age
            elif hasattr(self, '_soul_data') and self._soul_data:
                memory_loss_age = self._soul_data.get("memory_loss_start_age", 0)

            if event_age_years < 3.0:
                continue
            elif memory_loss_age > 0 and event_age_years < memory_loss_age:
                if importance < 0.75 and emotional_weight < 0.75:
                    continue

            current_age_months = self._soul_state.age_months if self._soul_state else 1200
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
            scored.append((score, ev))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [ev for _, ev in scored[:top_k]]

    def has_soul(self, character_name: str) -> bool:
        char_dir = self._cm._base_dir / character_name
        return (char_dir / "soul" / "soul.json").exists() or (char_dir / "soul.json").exists()

    def has_timeline_db(self, character_name: str) -> bool:
        char_dir = self._cm._base_dir / character_name
        return (
            (char_dir / "soul" / "life_timeline").exists()
            or (char_dir / "memory" / "life_timeline").exists()
        )

    def get_soul_data(self, character_name: str) -> Optional[dict]:
        char_dir = self._cm._base_dir / character_name
        soul_path = char_dir / "soul" / "soul.json"
        if not soul_path.exists():
            soul_path = char_dir / "soul.json"
        if not soul_path.exists():
            return None
        try:
            with open(soul_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def get_soul_path(self, character_name: str) -> Optional[Path]:
        char_dir = self._cm._base_dir / character_name
        soul_path = char_dir / "soul" / "soul.json"
        if not soul_path.exists():
            soul_path = char_dir / "soul.json"
        return soul_path if soul_path.exists() else None
