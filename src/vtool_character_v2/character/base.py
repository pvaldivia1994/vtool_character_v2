"""
Gestor del Character System para vtool_character_v2 — Clase base.

Maneja la arquitectura completa de personajes:
  - DNA (inmutable): identity.json, personality.json, speech.json, rules.json
  - Memory (mutable): chat_history.db (SQLite unificada)
  - State (runtime cache): runtime_state.json, personality_state.json
  - Mods (dinámicas temporales): mods.json
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Optional

from ..types import (
    ConfigSchema,
    CharacterLoadResult,
    ContextSummary,
    IdentityDNA,
    PersonalityDNA,
    SpeechDNA,
    RulesDNA,
    MemoryEntry,
    RuntimeState,
    RelationshipState,
    PersonalityState,
    CharacterMod,
    Genome,
)
from ..compiler import CharacterCompiler
from ..exceptions import LoadCancelledError


class CharacterManager:
    def __init__(
        self,
        base_dir: Optional[str] = None,
        logger_fn: Optional[Callable[[str, str], None]] = None,
    ):
        self._lock = threading.RLock()
        self._logger_fn = logger_fn or (lambda t, m: None)

        if base_dir is None:
            self._base_dir = Path(__file__).parent.parent / "characters"
        else:
            self._base_dir = Path(base_dir)

        self._ensure_dir(self._base_dir)

        self._character_name: Optional[str] = None
        self._char_dir: Optional[Path] = None

        self.identity: IdentityDNA = IdentityDNA()
        self.personality_dna: PersonalityDNA = PersonalityDNA()
        self.speech: SpeechDNA = SpeechDNA()
        self.rules: RulesDNA = RulesDNA()

        self.memories: list[MemoryEntry] = []
        self.runtime_state: RuntimeState = RuntimeState()
        self.personality_state: PersonalityState = PersonalityState()
        self.relationship_state: RelationshipState = RelationshipState()

        self.active_mods: dict[str, CharacterMod] = {}

        # --- Cache de prompt compilado (in-memory) ---
        # _prompt_dirty: True cuando mods/memorias cambian en esta sesión
        # _compiled_prompt_cache: último prompt compilado
        # _last_prompt_cache_key: tupla (base_system_prompt, config_fingerprint)
        self._prompt_dirty: bool = True
        self._compiled_prompt_cache: str = ""
        self._last_prompt_cache_key: tuple = (None, None)

        # --- Rebuild persistido (KV sync) ---
        # _cached_prompt_hash: hash SHA256 del último prompt syncado con KV store
        # _needs_rebuild: True cuando hay cambios que requieren recompilar
        self._cached_prompt_hash: str = ""
        self._needs_rebuild: bool = True

        # Atributos asignados dinámicamente por persistence.py y psychology_init.py
        self._soul_accessor = None
        self._psychology_manager = None
        self._genome: Optional[Genome] = None
        self._core_identity = None
        self._loading: bool = False
        self._cancel_loading: bool = False
        self._load_logs: list[str] = []
        self._last_load_result = None
        self.current_episode = None
        self._chat_memory = None

        self._compiler = CharacterCompiler(self)

    @property
    def is_loaded(self) -> bool:
        return self._character_name is not None

    @property
    def character_name(self) -> Optional[str]:
        return self._character_name

    @property
    def loading(self) -> bool:
        return self._loading

    def cancel_load(self) -> None:
        """Solicita cancelación de la carga en curso (thread-safe, non-blocking)."""
        self._cancel_loading = True

    def _check_cancel(self) -> None:
        """Lanzar LoadCancelledError si se solicitó cancelación."""
        if self._cancel_loading:
            raise LoadCancelledError("Carga cancelada por nueva solicitud")

    def check_needs_rebuild(self, prompt: str) -> bool:
        import hashlib
        if self._needs_rebuild:
            return True
        current_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        return current_hash != self._cached_prompt_hash

    def list_characters(self) -> list[dict]:
        if not self._base_dir.exists():
            return []

        chars = []
        for d in self._base_dir.iterdir():
            if not d.is_dir() or not (d / "dna").exists():
                continue
            name = d.name
            entry = {"name": name, "role": "", "background": "", "has_soul": False}

            identity_data = self._read_json_dict(d / "dna" / "identity.json")
            entry["role"] = identity_data.get("role", "")
            entry["background"] = identity_data.get("background", "")

            entry["has_soul"] = (
                (d / "soul" / "soul.json").exists()
                or (d / "soul.json").exists()
            )

            chars.append(entry)

        return sorted(chars, key=lambda c: c["name"])

    def _snapshot_state(self) -> dict:
        return {
            "_character_name": self._character_name,
            "_char_dir": self._char_dir,
            "_prompt_dirty": self._prompt_dirty,
            "_compiled_prompt_cache": self._compiled_prompt_cache,
            "_last_prompt_cache_key": self._last_prompt_cache_key,
            "identity": self.identity,
            "personality_dna": self.personality_dna,
            "speech": self.speech,
            "rules": self.rules,
            "memories": list(self.memories),
            "runtime_state": self.runtime_state,
            "personality_state": self.personality_state,
            "relationship_state": self.relationship_state,
            "active_mods": dict(self.active_mods),
            "_cached_prompt_hash": self._cached_prompt_hash,
            "_needs_rebuild": self._needs_rebuild,
            "_soul_accessor": self._soul_accessor,
            "_psychology_manager": self._psychology_manager,
            "_genome": self._genome,
            "_core_identity": self._core_identity,
            "current_episode": self.current_episode,
            "_chat_memory": self._chat_memory,
        }

    def _restore_state(self, snap: dict) -> None:
        for attr, val in snap.items():
            object.__setattr__(self, attr, val)

    def load_character(self, name: str) -> CharacterLoadResult:
        with self._lock:
            self._loading = True
            self._cancel_loading = False
            self._load_logs = []
            result = CharacterLoadResult(character_name=name)
            snap = self._snapshot_state()

            try:
                char_dir = self._base_dir / name
                if not char_dir.exists() or not (char_dir / "dna").exists():
                    raise ValueError(f"Personaje '{name}' no encontrado en {self._base_dir}")

                # _char_dir se asigna temprano porque _load_dna y otros lo necesitan
                self._char_dir = char_dir
                self._prompt_dirty = True

                self._ensure_dir(self._char_dir / "_memory")
                self._ensure_dir(self._char_dir / "_memory" / "episodes")
                self._ensure_dir(self._char_dir / "state")
                self._ensure_dir(self._char_dir / "mods")

                self._check_cancel()
                self._load_dna()

                self._check_cancel()
                self._load_memory()

                self._check_cancel()
                self._load_state()

                self._check_cancel()
                self._load_mods()

                self._check_cancel()
                self._init_soul_accessor()

                self._check_cancel()
                self._init_chat_memory()

                # Rehidratar el episodio/sesión más reciente si existe.
                # Esto deja a current_episode listo para que el caller
                # restaure la memoria conversacional en vtool_llama_v2.
                self._load_latest_episode()

                # Todo salio bien — asignar nombre definitivo
                self._character_name = name

                result.soul_active = (
                    self._soul_accessor is not None
                    and self._soul_accessor.is_active
                )
                result.psychology_active = self._psychology_manager is not None

                self._log("CHAR", f"Personaje '{name}' cargado exitosamente.")

            except LoadCancelledError:
                self._restore_state(snap)
                result.success = False
                result.error = "Carga cancelada por nueva solicitud"
                self._log("CHAR", f"Carga de '{name}' cancelada.")

            except Exception as e:
                self._restore_state(snap)
                result.success = False
                result.error = str(e)
                raise

            finally:
                result.logs = list(self._load_logs)
                self._last_load_result = result
                self._loading = False
                self._cancel_loading = False
                self._load_logs = []

            return result

    @property
    def last_load_result(self) -> Optional[CharacterLoadResult]:
        return self._last_load_result

    def create_character(
        self, name: str,
        identity_data: dict, personality_data: dict,
        speech_data: dict, rules_data: dict,
        initial_memories: list = None,
    ) -> None:
        with self._lock:
            char_dir = self._base_dir / name
            if char_dir.exists():
                raise ValueError(f"El personaje '{name}' ya existe en {self._base_dir}")

            self._ensure_dir(char_dir / "dna")
            self._ensure_dir(char_dir / "_memory")
            self._ensure_dir(char_dir / "_memory" / "episodes")
            self._ensure_dir(char_dir / "state")
            self._ensure_dir(char_dir / "mods")

            self._write_json(char_dir / "dna" / "identity.json", asdict(IdentityDNA(**identity_data)))
            self._write_json(char_dir / "dna" / "personality.json", asdict(PersonalityDNA(**personality_data)))
            self._write_json(char_dir / "dna" / "speech.json", asdict(SpeechDNA(**speech_data)))
            self._write_json(char_dir / "dna" / "rules.json", asdict(RulesDNA(**rules_data)))

            mems = []
            if initial_memories:
                import uuid
                for mem in initial_memories:
                    mems.append(MemoryEntry(
                        id=str(uuid.uuid4())[:8],
                        content=mem,
                        priority=1.0,
                        always_include=True,
                        tags=[],
                    ))

            from ..db.character_memory import CharacterMemoryStore
            memory_store = CharacterMemoryStore(char_dir / "_memory" / "chat_history.db")
            memory_store.initialize()
            memory_store.replace_all(mems)

            # Legacy mirror solo para compatibilidad de carga antigua.
            self._write_json(
                char_dir / "_memory" / "long_term.json",
                {"memories": [asdict(m) for m in mems], "rebuild": True},
            )

            self._write_json(char_dir / "state" / "state_meta.json", {"prompt_hash": ""})
            self._write_json(char_dir / "state" / "runtime_state.json", asdict(RuntimeState()))
            self._write_json(char_dir / "state" / "personality_state.json", asdict(PersonalityState()))
            self._write_json(char_dir / "state" / "relationship_state.json", asdict(RelationshipState()))
            self._write_json(char_dir / "mods" / "active_mods.json", {})

            import shutil
            default_config_path = self._base_dir / "default" / "config.json"
            if default_config_path.exists():
                shutil.copy2(str(default_config_path), str(char_dir / "config.json"))
            else:
                self._write_json(char_dir / "config.json", {})

            for yaml_file in ("system_core.yaml", "anti_assistant.yaml", "roleplay_mode.yaml"):
                src = self._base_dir / "default" / yaml_file
                if src.exists():
                    shutil.copy2(str(src), str(char_dir / yaml_file))

            self._log("CHAR", f"Estructura del personaje '{name}' creada exitosamente.")

    def _config_cache_key(self, config: Optional[ConfigSchema]) -> str:
        if config is None:
            return "none"
        import json
        from dataclasses import asdict
        return json.dumps(asdict(config), sort_keys=True, default=str)

    def build_system_prompt(
        self,
        base_system_prompt: str,
        config: Optional[ConfigSchema] = None,
        chat_query: Optional[str] = None,
    ) -> str:
        key = (base_system_prompt, self._config_cache_key(config), chat_query or "")
        use_cache = chat_query is None
        if (use_cache and not self._prompt_dirty and not self._needs_rebuild
                and self._compiled_prompt_cache and self._last_prompt_cache_key == key):
            return self._compiled_prompt_cache

        if config and getattr(config, "compact_system_prompt", False):
            self._compiled_prompt_cache = self._compiler.compile_compact_prompt(
                base_system_prompt,
                config,
                chat_query=chat_query,
            )
        else:
            self._compiled_prompt_cache = self._compiler.compile_static_prompt(
                base_system_prompt,
                config,
                chat_query=chat_query,
            )
        if use_cache:
            self._prompt_dirty = False
            self._needs_rebuild = False
            self._last_prompt_cache_key = key
            self._save_prompt_reference(self._compiled_prompt_cache)
        return self._compiled_prompt_cache

    def _save_prompt_reference(self, prompt: str) -> None:
        """Guarda el prompt compilado en _memory/system_prompt.md como referencia."""
        if not self._char_dir:
            return
        try:
            ref_dir = self._char_dir / "_memory"
            ref_dir.mkdir(parents=True, exist_ok=True)
            (ref_dir / "system_prompt.md").write_text(prompt, encoding="utf-8")
        except OSError:
            pass

    def build_full_system_prompt(
        self,
        base_system_prompt: str,
        config: Optional[ConfigSchema] = None,
        chat_query: Optional[str] = None,
    ) -> str:
        return self._compiler.compile_full_prompt(base_system_prompt, config, chat_query=chat_query)

    def build_compact_system_prompt(
        self,
        base_system_prompt: str,
        config: Optional[ConfigSchema] = None,
        chat_query: Optional[str] = None,
    ) -> str:
        return self._compiler.compile_compact_prompt(base_system_prompt, config, chat_query=chat_query)

    def build_dynamic_prompt(self) -> str:
        return self._compiler.compile_dynamic_prompt()

    def get_prompt_layer_breakdown(
        self,
        base_system_prompt: str,
        count_fn: Optional[Callable[[str], int]] = None,
        config: Optional[ConfigSchema] = None,
    ) -> dict:
        return self._compiler.get_layer_token_breakdown(base_system_prompt, count_fn, config)

    def mark_prompt_dirty(self) -> None:
        self._prompt_dirty = True

    def build_base_system_prompt(self, base_system_prompt: str, config: Optional[ConfigSchema] = None) -> str:
        return self._compiler.compile_base_prompt(base_system_prompt, config)

    def compile_base_soul_prompt(self, base_system_prompt: str, config: Optional[ConfigSchema] = None) -> str:
        return self._compiler.compile_base_soul_prompt(base_system_prompt, config)

    def get_relevant_memories(self) -> list[MemoryEntry]:
        with self._lock:
            mems = list(self.memories)
            mems.sort(key=lambda m: m.priority, reverse=True)
            return mems

    # ------------------------------------------------------------------
    # Chat session helpers (delegan a vtool_llama_v2.SQLiteChatStore)
    # ------------------------------------------------------------------

    def get_memory_dir(self) -> Path:
        """Directorio de memoria del personaje cargado."""
        if not self._char_dir:
            raise RuntimeError("No hay personaje cargado.")
        return self._char_dir / "_memory"

    def get_memory_db_path(self) -> Path:
        """Ruta unificada a la base SQLite del character."""
        return self.get_chat_db_path()

    def get_context_summary_db_path(self) -> Path:
        """Ruta unificada a la base SQLite del resumen de contexto."""
        return self.get_memory_db_path()

    def get_chat_log_dir(self) -> Path:
        """Directorio donde se guardan los logs markdown por turno."""
        return self.get_memory_dir() / "chat log"

    def count_chat_turn_logs(self) -> int:
        """Cuenta los archivos de log por turno ya escritos."""
        log_dir = self.get_chat_log_dir()
        if not log_dir.exists():
            return 0
        return sum(1 for _ in log_dir.glob("turn_*.md"))

    def get_chat_db_path(self) -> Path:
        """Ruta a la base SQLite de historial conversacional."""
        return self.get_memory_dir() / "chat_history.db"

    def count_chat_session_messages(self, session_id: str) -> int:
        """Cuenta los mensajes persistidos de una sesión."""
        return self._with_chat_store(lambda s: s.count_session_messages(session_id))

    def get_context_summary(self, session_id: str) -> Optional[ContextSummary]:
        """Obtiene el resumen de contexto activo para una sesión."""
        return self._with_memory_store(lambda s: s.get_context_summary(session_id))

    def list_context_summaries(self, character_name: Optional[str] = None) -> list[ContextSummary]:
        """Lista los resúmenes de contexto guardados."""
        return self._with_memory_store(lambda s: s.list_context_summaries(character_name))

    def save_context_summary(
        self,
        session_id: str,
        summary: str,
        summarized_message_count: int,
        title: Optional[str] = None,
        model_name: Optional[str] = None,
        character_name: Optional[str] = None,
    ) -> None:
        """Guarda o actualiza el resumen de contexto activo."""
        def _save(store):
            store.upsert_context_summary(
                session_id=session_id,
                summary=summary,
                summarized_message_count=summarized_message_count,
                character_name=character_name or self._character_name or "",
                title=title or "",
                model_name=model_name or "",
            )

        self._with_memory_store(_save)

    def delete_context_summary(self, session_id: str) -> bool:
        """Elimina el resumen activo de una sesión."""
        return bool(self._with_memory_store(lambda s: s.delete_context_summary(session_id)))

    def get_unsummarized_chat_messages(self, session_id: str) -> list[dict]:
        """Retorna los mensajes no cubiertos por el resumen activo."""
        summary = self.get_context_summary(session_id)
        summarized_message_count = summary.summarized_message_count if summary else 0
        messages = self.load_chat_session_messages(session_id)
        return messages[summarized_message_count:]

    def should_refresh_context_summary(self, session_id: str, every_n_messages: int = 20) -> bool:
        """Indica si ya conviene regenerar el resumen de contexto."""
        if every_n_messages <= 0:
            return False
        summary = self.get_context_summary(session_id)
        summarized_message_count = summary.summarized_message_count if summary else 0
        total_messages = self.count_chat_session_messages(session_id)
        return (total_messages - summarized_message_count) >= every_n_messages

    def should_summarize_before_next_message(self, session_id: str, history_limit: int = 10) -> bool:
        """Indica si el bloque activo ya alcanzo el limite y debe resumirse antes del siguiente mensaje."""
        return self.should_refresh_context_summary(session_id, every_n_messages=history_limit)

    def _with_chat_store(self, fn):
        try:
            from vtool_llama_v2.chat_store import SQLiteChatStore
        except ImportError:
            raise RuntimeError(
                "vtool_llama_v2 no está instalado o no se encuentra en el PATH. "
                "Instálalo o agrégalo al sys.path para usar historial conversacional."
            )
        store = SQLiteChatStore(str(self.get_chat_db_path()))
        try:
            store.initialize()
            return fn(store)
        finally:
            store.close()

    def _with_memory_store(self, fn):
        from ..db.character_memory import CharacterMemoryStore

        store = CharacterMemoryStore(self.get_chat_db_path(), log_fn=lambda msg: self._logger_fn("MEM_DB", msg))
        store.initialize()
        try:
            return fn(store)
        finally:
            pass

    def list_chat_sessions(self) -> list[dict]:
        """Lista todas las sesiones guardadas del personaje cargado.

        Retorna lista de dicts con metadatos de cada sesión.
        El source of truth del historial conversacional es vtool_llama_v2.
        """
        return self._with_chat_store(lambda s: s.list_sessions())

    def get_chat_session(self, session_id: str) -> Optional[dict]:
        """Recupera metadatos de una sesión específica."""
        return self._with_chat_store(lambda s: s.get_session(session_id))

    def load_chat_session_messages(self, session_id: str) -> list[dict]:
        """Carga los mensajes de una sesión guardada."""
        return self._with_chat_store(lambda s: s.load_session_messages(session_id))

    def append_chat_session_messages(
        self,
        session_id: str,
        messages: list[dict],
        character_name: Optional[str] = None,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        """Inserta mensajes nuevos en una sesiÃ³n SQLite, sin reemplazar el historial."""
        if not messages:
            return

        def _append(store):
            if not store.session_exists(session_id):
                store.upsert_session(
                    session_id=session_id,
                    character_name=character_name or self._character_name,
                    title=title,
                    summary=summary,
                    model_name=model_name,
                )
            store.append_session_messages(session_id, messages)

        self._with_chat_store(_append)

    def get_chat_history_messages(
        self,
        session_id: Optional[str] = None,
        history_limit: Optional[int] = None,
        source_messages: Optional[list[dict]] = None,
    ) -> list[dict]:
        """Retorna el historial reciente del chat sin mensajes system."""
        raw_messages: list[dict] = []

        if source_messages is not None:
            raw_messages = [dict(m) for m in source_messages]
        elif session_id:
            try:
                raw_messages = self.load_chat_session_messages(session_id)
            except Exception:
                raw_messages = []
        elif self.current_episode and getattr(self.current_episode, "source", "") == "sqlite" and self.current_episode.messages:
            raw_messages = [dict(m) for m in self.current_episode.messages]

        filtered = [m for m in raw_messages if m.get("role") != "system"]
        if history_limit is not None and history_limit >= 0:
            filtered = filtered[-history_limit:]
        return filtered

    def build_chat_messages(
        self,
        base_system_prompt: str,
        user_message: str,
        session_id: Optional[str] = None,
        history_limit: int = 40,
        chat_query: Optional[str] = None,
        source_messages: Optional[list[dict]] = None,
    ) -> list[dict]:
        """Construye el contexto completo para una llamada con messages explícitos."""
        query = chat_query or user_message
        system_prompt = self.build_full_system_prompt(base_system_prompt, chat_query=query)

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        history = self.get_chat_history_messages(
            session_id=session_id,
            history_limit=history_limit,
            source_messages=source_messages,
        )
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return messages

    def build_chat_messages_from_summary(
        self,
        base_system_prompt: str,
        user_message: str,
        session_id: str,
        history_limit: int = 40,
        chat_query: Optional[str] = None,
    ) -> list[dict]:
        """Construye mensajes usando el resumen activo guardado en SQLite."""
        summary = self.get_context_summary(session_id)
        summary_text = summary.summary if summary else ""
        summarized_message_count = summary.summarized_message_count if summary else 0
        query = chat_query or user_message
        system_prompt = self.build_full_system_prompt(base_system_prompt, chat_query=None)
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        memory_block = self._compiler._resolve_memory()
        if memory_block:
            messages.append({"role": "system", "content": memory_block})
        if summary_text:
            messages.append({
                "role": "system",
                "content": "\n".join([
                    "[CONTEXT SUMMARY]",
                    summary_text.strip(),
                ]),
            })
        semantic_block = self.get_chat_memories_block(query) if query else ""
        if semantic_block:
            messages.append({"role": "system", "content": semantic_block})
        history = self.get_chat_history_messages(session_id=session_id, history_limit=None)
        if summarized_message_count:
            history = history[int(summarized_message_count):]
        if history_limit is not None and history_limit >= 0:
            history = history[-history_limit:]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return messages

    def _format_summary_transcript(self, messages: list[dict]) -> list[str]:
        """Convierte un bloque de mensajes en transcript legible para el resumidor."""
        speaker_name = (self.identity.name or "Character").strip() if self.is_loaded else "Character"
        lines: list[str] = []

        for msg in messages:
            role = str(msg.get("role", "")).strip().lower()
            content = str(msg.get("content", "") or "").strip()
            if not content:
                continue

            if role == "user":
                speaker = "Usuario"
            elif role == "assistant":
                speaker = speaker_name
            elif role == "tool":
                speaker = "Tool"
            else:
                speaker = role.capitalize() or "Mensaje"

            lines.append(f"{speaker} dijo: {content}")

        return lines or ["Sin mensajes para resumir."]

    def build_context_summary_messages(
        self,
        session_id: str,
        summary_system_prompt: str,
        history_limit: int = 80,
    ) -> list[dict]:
        """Construye mensajes para pedirle al LLM un resumen incremental."""
        summary = self.get_context_summary(session_id)
        previous_summary = summary.summary if summary else ""
        summarized_message_count = summary.summarized_message_count if summary else 0

        history = self.get_chat_history_messages(session_id=session_id, history_limit=None)
        if summarized_message_count:
            history = history[int(summarized_message_count):]
        if history_limit is not None and history_limit >= 0:
            history = history[-history_limit:]

        payload_lines: list[str] = [
            "Resumen anterior:",
            previous_summary.strip() if previous_summary.strip() else "Sin resumen anterior.",
            "",
            "Bloque de conversacion a resumir:",
        ]
        payload_lines.extend(self._format_summary_transcript(history))

        return [
            {"role": "system", "content": summary_system_prompt.strip()},
            {"role": "user", "content": "\n".join(payload_lines).strip()},
        ]

    def build_long_term_memory_extraction_messages(
        self,
        source_messages: list[dict],
        extraction_system_prompt: str,
    ) -> list[dict]:
        """Construye mensajes para extraer recuerdos duraderos desde un bloque real de chat."""
        existing_memories = [m.content for m in self.get_relevant_memories() if getattr(m, "content", "").strip()]
        payload_lines: list[str] = [
            "Recuerdos anteriores que NO debes repetir:",
        ]
        if existing_memories:
            payload_lines.extend([f"- {memory.strip()}" for memory in existing_memories])
        else:
            payload_lines.append("- No hay recuerdos anteriores.")
        payload_lines.extend([
            "",
            "Nuevos chats:",
        ])
        payload_lines.extend(self._format_summary_transcript(source_messages))
        return [
            {
                "role": "system",
                "content": "\n".join([
                    extraction_system_prompt.strip(),
                    "",
                    "OUTPUT RULES:",
                    "- Return ONLY valid JSON.",
                    "- The top-level value must be an array.",
                    "- Each item must be an object with keys: content, priority, always_include, tags.",
                    "- Do not wrap the JSON in markdown fences.",
                    "- Do not add explanations.",
                    "- Do not repeat memories that are already present in 'Recuerdos anteriores que NO debes repetir'.",
                    "- Do not return questions, prompts, or vague fragments.",
                    "- Only return durable facts Luna should remember.",
                    "- Return 1 to 7 memories only if they add new value.",
                ]),
            },
            {"role": "user", "content": "\n".join(payload_lines).strip()},
        ]

    def build_default_summary_system_prompt(self) -> str:
        """Prompt base para resúmenes incrementales consistentes."""
        return (
            "Eres un experto en resumir conversaciones narrativas entre personajes.\n"
            "Tu trabajo es actualizar un resumen acumulado usando SOLO el resumen anterior y el bloque de conversacion recibido.\n"
            "No inventes hechos. No agregues opinion. No respondas como personaje. No escribas dialogo nuevo.\n"
            "Si un detalle no es claro, omitelo.\n"
            "Debes dejar muy claro cual fue el ultimo dialogo relevante, que temas se hablaron, que informacion importante se confirmo y si quedo algo pendiente.\n"
            "Escribe todo en espanol.\n"
            "Devuelve texto plano con exactamente estas secciones, en este orden:\n"
            "1. Ultimo dialogo relevante\n"
            "2. Conversacion relevante entre los personajes\n"
            "3. Temas hablados\n"
            "4. Datos importantes confirmados\n"
            "5. Temas pendientes o compromisos\n"
            "6. Estado actual de la relacion y tono\n"
            "Reglas:\n"
            "- En 'Ultimo dialogo relevante' deja claro cual fue el ultimo intercambio importante.\n"
            "- En 'Conversacion relevante entre los personajes' resume lo que realmente se dijeron entre si.\n"
            "- En 'Temas hablados' resume los topicos principales tratados en la ventana.\n"
            "- En 'Datos importantes confirmados' extrae hechos utiles como nombres, gustos, trabajo, relaciones o contexto estable.\n"
            "- En 'Temas pendientes o compromisos' deja claro si quedo algo abierto.\n"
            "- Usa bullets cortos.\n"
            "- Si una seccion no tiene contenido, escribe '- Sin cambios.'.\n"
        )

    def build_default_memory_extraction_prompt(self) -> str:
        """Prompt base para extraer memorias duraderas desde un resumen."""
        return (
            "Eres un experto en memoria narrativa para personajes.\n"
            "Tu trabajo es extraer los recuerdos importantes del personaje Luna sobre su conversacion con el personaje User.\n"
            "Debes pensar como si estuvieras construyendo los recuerdos propios de Luna, segun las directrices del personaje.\n"
            "Los recuerdos pueden ser sobre lo que dijo User, sobre lo que dijo Luna, y sobre la relacion que se va formando entre ambos.\n"
            "Usa SOLO los recuerdos anteriores y los nuevos chats recibidos.\n"
            "Extrae solo informacion nueva, estable y relevante para futuras conversaciones.\n"
            "No repitas recuerdos ya guardados.\n"
            "No devuelvas preguntas, respuestas conversacionales, recomendaciones pasajeras, frases de cortesia, ni fragmentos vagos.\n"
            "No guardes lineas literales de dialogo salvo que expresen un hecho estable realmente importante.\n"
            "Prefiere hechos como: nombre del User, gustos estables del User, trabajo del User, gustos estables de Luna, creencias de Luna, relaciones, compromisos, contexto personal importante y datos duraderos de la relacion entre Luna y User.\n"
            "Buenos ejemplos de recuerdos: 'El User se llama Pedro.', 'A Luna le gustan los libros de terror.', 'A Pedro le gustan los libros de amor.', 'Luna no cree en el amor.'.\n"
            "Si los nuevos chats no agregan nada importante, devuelve un array vacio.\n"
            "Devuelve SOLO JSON valido como un array de objetos.\n"
            "Cada objeto debe tener: content, priority, always_include, tags.\n"
            "Escribe 'content' en espanol, como afirmacion clara y completa.\n"
            "Cada memoria debe sonar como algo que Luna deberia recordar despues sobre User, sobre ella misma o sobre la relacion entre ambos, no como una pregunta ni como una respuesta momentanea.\n"
        )

    @staticmethod
    def _normalize_memory_text(text: str) -> str:
        return " ".join(str(text or "").strip().lower().split())

    @staticmethod
    def _looks_like_invalid_memory(text: str) -> bool:
        clean = str(text or "").strip()
        if not clean:
            return True
        if len(clean) < 12:
            return True
        if "?" in clean or "¿" in clean:
            return True
        lowered = clean.lower()
        bad_prefixes = (
            "como ",
            "qué ",
            "que ",
            "cual ",
            "cuál ",
            "su nombre",
            "su trabajo",
            "tiempo de trabajo",
            "funciones en la oficina",
            "relacion cordial",
            "relación cordial",
        )
        return lowered.startswith(bad_prefixes)

    @staticmethod
    def _sanitize_memory_text(text: str) -> str:
        import html

        clean = html.unescape(str(text or ""))
        clean = clean.replace("Â¿", "¿").replace("Â¡", "¡")
        clean = " ".join(clean.split())
        return clean.strip(" -\t")

    @staticmethod
    def _normalize_memory_text(text: str) -> str:
        return " ".join(CharacterManager._sanitize_memory_text(text).lower().split())

    @staticmethod
    def _looks_like_invalid_memory(text: str, tags: Optional[list[str]] = None) -> bool:
        clean = CharacterManager._sanitize_memory_text(text)
        if not clean:
            return True
        if len(clean) < 12:
            return True
        if "?" in clean or "¿" in clean:
            return True
        lowered = clean.lower()
        normalized_tags = [CharacterManager._normalize_memory_text(tag) for tag in (tags or [])]
        if any("summary_fallback" in tag for tag in normalized_tags):
            return True
        if lowered.startswith((
            "ultimo dialogo relevante:",
            "conversacion relevante entre los personajes:",
            "conversación relevante entre los personajes:",
            "temas hablados:",
            "datos importantes confirmados:",
            "temas pendientes o compromisos:",
            "estado actual de la relacion y tono:",
            "estado actual de la relación y tono:",
        )):
            return True
        bad_prefixes = (
            "como ",
            "qué ",
            "que ",
            "cual ",
            "cuál ",
            "su nombre",
            "su trabajo",
            "tiempo de trabajo",
            "funciones en la oficina",
            "relacion cordial",
            "relación cordial",
            "si busca ",
            "si prefiere ",
            "si quiere ",
            "es una historia ",
            "un libro ",
            "los libros de ",
            "las cronicas ",
            "las crónicas ",
            "el libro de ",
            "el carter de ",
            "el cárter de ",
        )
        if lowered.startswith(bad_prefixes):
            return True
        allowed_prefixes = (
            "el user ",
            "al user ",
            "el usuario ",
            "al usuario ",
            "user ",
            "usuario ",
            "pedro ",
            "a pedro ",
            "luna ",
            "a luna ",
            "entre luna y user",
            "entre luna y usuario",
            "entre luna y pedro",
            "la relacion entre luna y user",
            "la relación entre luna y user",
            "la relacion entre luna y pedro",
            "la relación entre luna y pedro",
        )
        if not lowered.startswith(allowed_prefixes):
            return True
        if lowered.startswith((
            "pedro le pregunto",
            "pedro le preguntó",
            "el user pregunto",
            "el user preguntó",
            "el usuario pregunto",
            "el usuario preguntó",
        )):
            return True
        return False

    def cleanup_character_memories(self, persist: bool = False) -> dict:
        """Limpia memorias inválidas o duplicadas ya cargadas en memoria."""
        original_count = len(self.memories)
        cleaned: list[MemoryEntry] = []
        seen: dict[str, MemoryEntry] = {}

        for mem in self.memories:
            sanitized = self._sanitize_memory_text(mem.content)
            if self._looks_like_invalid_memory(sanitized, mem.tags):
                continue

            normalized = self._normalize_memory_text(sanitized)
            overlap_key = None
            for existing_key in seen:
                if normalized in existing_key or existing_key in normalized:
                    overlap_key = existing_key
                    break

            if overlap_key is not None:
                existing = seen[overlap_key]
                replacement = existing
                if len(normalized) > len(overlap_key):
                    replacement = MemoryEntry(
                        id=mem.id,
                        content=sanitized,
                        priority=max(existing.priority, mem.priority),
                        always_include=existing.always_include or mem.always_include,
                        tags=list(dict.fromkeys([*existing.tags, *mem.tags])),
                    )
                    cleaned[cleaned.index(existing)] = replacement
                    del seen[overlap_key]
                    seen[normalized] = replacement
                else:
                    existing.priority = max(existing.priority, mem.priority)
                    existing.always_include = existing.always_include or mem.always_include
                    existing.tags = list(dict.fromkeys([*existing.tags, *mem.tags]))
                continue

            if normalized in seen:
                existing = seen[normalized]
                existing.priority = max(existing.priority, mem.priority)
                existing.always_include = existing.always_include or mem.always_include
                existing.tags = list(dict.fromkeys([*existing.tags, *mem.tags]))
                continue

            cleaned_mem = MemoryEntry(
                id=mem.id,
                content=sanitized,
                priority=mem.priority,
                always_include=mem.always_include,
                tags=list(mem.tags),
            )
            seen[normalized] = cleaned_mem
            cleaned.append(cleaned_mem)

        self.memories = cleaned
        result = {
            "before": original_count,
            "after": len(cleaned),
            "removed": max(0, original_count - len(cleaned)),
        }
        if persist and self._char_dir:
            try:
                self.save_state()
            except Exception as e:
                self._log("CHAR", f"No se pudo persistir limpieza de memorias automaticamente: {e}")
        return result

    def store_extracted_memories_from_json(self, payload: str) -> list[MemoryEntry]:
        """Convierte un JSON de memorias extraidas en recuerdos persistentes."""
        try:
            data = json.loads(payload)
        except Exception:
            import re
            candidate = ""
            match = re.search(r"```(?:json)?\s*(.*?)```", payload, re.S | re.I)
            if match:
                candidate = match.group(1).strip()
            else:
                start = payload.find("[")
                end = payload.rfind("]")
                if start != -1 and end != -1 and end > start:
                    candidate = payload[start:end + 1].strip()
                else:
                    start = payload.find("{")
                    end = payload.rfind("}")
                    if start != -1 and end != -1 and end > start:
                        candidate = payload[start:end + 1].strip()
            if not candidate:
                return []
            try:
                data = json.loads(candidate)
            except Exception:
                return []

        if isinstance(data, dict):
            items = data.get("memories", data.get("items", []))
        else:
            items = data

        if not isinstance(items, list):
            return []

        existing_normalized = {
            self._normalize_memory_text(m.content)
            for m in self.get_relevant_memories()
            if getattr(m, "content", "").strip()
        }
        created: list[MemoryEntry] = []
        created_normalized: set[str] = set()
        for item in items:
            if isinstance(item, str):
                content = self._sanitize_memory_text(item)
                priority = 0.7
                always_include = False
                tags: list[str] = []
            elif isinstance(item, dict):
                content = self._sanitize_memory_text(
                    item.get("content")
                    or item.get("memory")
                    or item.get("text")
                    or ""
                )
                priority = float(item.get("priority", 0.7) or 0.7)
                always_include = bool(item.get("always_include", False))
                raw_tags = item.get("tags", [])
                tags = [str(tag) for tag in raw_tags] if isinstance(raw_tags, list) else []
            else:
                continue

            normalized = self._normalize_memory_text(content)
            if (
                not content
                or self._looks_like_invalid_memory(content, tags)
                or normalized in existing_normalized
                or normalized in created_normalized
            ):
                continue
            created_normalized.add(normalized)
            created.append(
                self.add_memory(
                    content=content,
                    priority=priority,
                    always_include=always_include,
                    tags=tags,
                )
            )
        return created

    def store_extracted_memories_from_summary(self, summary_text: str, max_items: int = 5) -> list[MemoryEntry]:
        """Compatibilidad: el fallback desde summary queda desactivado para evitar recuerdos basura."""
        _ = summary_text
        _ = max_items
        return []

    def backfill_context_summary(
        self,
        session_id: str,
        chat_callable: Callable[[list[dict]], object],
        summary_system_prompt: str,
        extraction_system_prompt: str,
        every_n_messages: int = 8,
        history_limit: int = 80,
        title: Optional[str] = None,
        model_name: Optional[str] = None,
        character_name: Optional[str] = None,
    ) -> list[ContextSummary]:
        """Genera resúmenes incrementales hasta alcanzar el estado actual del chat.

        Usa el resumen previo como base y avanza por bloques completos de `every_n_messages`.
        Si el bloque restante es menor al limite, se deja activo sin resumir.
        """
        if every_n_messages <= 0:
            raise ValueError("every_n_messages debe ser mayor que 0.")

        history = self.get_chat_history_messages(session_id=session_id, history_limit=None)
        total_messages = len(history)
        if total_messages == 0:
            return []

        current_summary = self.get_context_summary(session_id)
        summarized_count = current_summary.summarized_message_count if current_summary else 0
        summarized_count = max(0, min(summarized_count, total_messages))

        remaining_messages = total_messages - summarized_count
        if summarized_count >= total_messages:
            return [current_summary] if current_summary else []
        if remaining_messages < every_n_messages:
            return [current_summary] if current_summary else []

        saved_summaries: list[ContextSummary] = []
        current_text = current_summary.summary if current_summary else ""

        end_points = list(range(
            summarized_count + every_n_messages,
            total_messages + 1,
            every_n_messages,
        ))

        for end_idx in end_points:
            chunk = history[summarized_count:end_idx]
            if not chunk:
                continue

            payload_lines: list[str] = [
                "Resumen anterior:",
                current_text.strip() if current_text.strip() else "Sin resumen anterior.",
                "",
                "Bloque de conversacion a resumir:",
            ]
            payload_lines.extend(self._format_summary_transcript(chunk))

            summary_messages: list[dict] = [
                {"role": "system", "content": summary_system_prompt.strip()},
                {"role": "user", "content": "\n".join(payload_lines).strip()},
            ]

            summary_resp = chat_callable(summary_messages)
            if not getattr(summary_resp, "success", False):
                break
            summary_text = (getattr(summary_resp, "content", "") or "").strip()
            if not summary_text:
                break

            summarized_count = end_idx
            self.save_context_summary(
                session_id=session_id,
                summary=summary_text,
                summarized_message_count=summarized_count,
                title=title,
                model_name=model_name,
                character_name=character_name,
            )
            current_text = summary_text
            self.add_chat_memory(
                text=summary_text,
                session_id=session_id,
                importance=0.85,
                topic="context_summary",
            )

            extraction_messages = self.build_long_term_memory_extraction_messages(
                chunk,
                extraction_system_prompt,
            )
            extraction_resp = chat_callable(extraction_messages)
            if getattr(extraction_resp, "success", False):
                extracted = self.store_extracted_memories_from_json(getattr(extraction_resp, "content", "") or "")
                if extracted:
                    self._prompt_dirty = True

            saved = self.get_context_summary(session_id)
            if saved:
                saved_summaries.append(saved)

        return saved_summaries

    def write_chat_turn_log(
        self,
        *,
        session_id: str,
        turn_index: int,
        user_message: str,
        response_message: str,
        messages_sent: list[dict],
        flow_steps: Optional[list[str]] = None,
        error: Optional[str] = None,
        system_prompt: Optional[str] = None,
        chat_query: Optional[str] = None,
        context_summary: Optional[str] = None,
        summarized_message_count: Optional[int] = None,
        relevant_memories: Optional[list[str]] = None,
        semantic_memory_block: Optional[str] = None,
        source_messages: Optional[list[dict]] = None,
    ) -> Path:
        """Escribe un log markdown por turno en _memory/chat log/."""
        if not self._char_dir:
            raise RuntimeError("No hay personaje cargado.")

        from datetime import datetime

        log_dir = self.get_chat_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now()
        stamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"turn_{stamp}_{turn_index:04d}.md"
        path = log_dir / filename

        def _clean_text(text: object) -> str:
            value = str(text or "")
            return value.replace("\r\n", "\n").replace("\r", "\n").strip()

        def _collapse_whitespace(text: object) -> str:
            return " ".join(_clean_text(text).split())

        def _truncate(text: object, limit: int = 420) -> str:
            value = _clean_text(text)
            if len(value) <= limit:
                return value
            return value[: max(0, limit - 1)].rstrip() + "..."

        def _message_content(msg: dict, *, collapse: bool = False, limit: int = 420) -> str:
            content = msg.get("content", "")
            if isinstance(content, list):
                content = "\n".join(str(item) for item in content)
            if not content and msg.get("tool_calls"):
                tool_calls = msg.get("tool_calls", [])
                return f"[tool_calls: {len(tool_calls)}]"
            if collapse:
                return _truncate(_collapse_whitespace(content), limit=limit)
            return _truncate(content, limit=limit)

        def _message_label(msg: dict, index: int) -> str:
            role = str(msg.get("role", "")).strip() or "unknown"
            if role == "system":
                system_titles = ["System base", "Memory", "Summary", "Semantic"]
                if index < len(system_titles):
                    return system_titles[index]
                return f"System extra {index - len(system_titles) + 1}"
            if role == "user":
                return "Usuario"
            if role == "assistant":
                return "Asistente"
            if role == "tool":
                return "Tool"
            return role.capitalize()

        def _render_message_list(items: list[dict], *, collapse: bool = False) -> str:
            if not items:
                return "_Sin mensajes._"
            lines: list[str] = []
            for i, msg in enumerate(items, 1):
                label = _message_label(msg, i - 1)
                content = _message_content(msg, collapse=collapse, limit=260 if collapse else 900)
                lines.append(f"{i}. **{label}**")
                lines.append("")
                lines.append("```markdown")
                lines.append(content or "_Vacio_")
                lines.append("```")
                lines.append("")
            return "\n".join(lines).rstrip()

        def _render_plain_list(title: str, items: list[str]) -> list[str]:
            block: list[str] = [f"## {title}", ""]
            if items:
                block.extend([f"- {_truncate(item, limit=300)}" for item in items])
            else:
                block.append("_Vacio_")
            block.append("")
            return block

        if relevant_memories is None:
            relevant_memories = [m.content for m in self.get_relevant_memories() if getattr(m, "content", "")]

        if semantic_memory_block is None:
            semantic_query = chat_query or user_message
            semantic_memory_block = self.get_chat_memories_block(semantic_query) if semantic_query else ""

        lines: list[str] = [
            f"# Chat Turn {turn_index}",
            "",
            "## Resumen rapido",
            "",
            f"- Fecha de ejecucion: `{now.strftime('%Y-%m-%d %H:%M:%S')}`",
            f"- Session ID: `{session_id}`",
            f"- Usuario: `{_truncate(user_message, limit=160) or '_Vacio_'}`",
            f"- Respuesta: `{_truncate(response_message, limit=160) or '_Vacio_'}`",
            f"- Mensajes enviados: `{len(messages_sent)}`",
            f"- Recuerdos relevantes: `{len(relevant_memories or [])}`",
            f"- Resumen de contexto: `{summarized_message_count if summarized_message_count is not None else 'N/D'}` mensajes resumidos",
            "",
            "## Flujo ejecutado",
        ]
        steps = flow_steps or [
            "1. Se construyo el contexto con CharacterManager.build_chat_messages_from_summary().",
            "2. Se envio la lista final de mensajes a session.chat(messages=...).",
            "3. El modelo genero la respuesta.",
            "4. Se guardo el turno en SQLite con append_chat_session_messages().",
            "5. Se escribio este archivo Markdown para auditoria.",
        ]
        lines.extend([f"- {step}" for step in steps])

        if error:
            lines.extend([
                "",
                "## Error",
                "",
                f"`{error}`",
            ])

        lines.extend([
            "",
            "## Entrada del usuario",
            "",
            user_message or "_Vacio_",
            "",
            "## Respuesta del modelo",
            "",
            response_message or "_Vacio_",
            "",
            "## System Prompt",
            "",
            "```markdown",
            _clean_text(system_prompt or "_No provisto_"),
            "```",
            "",
            "## Resumen de contexto",
            "",
            "```markdown",
            _clean_text(context_summary or "_No provisto_"),
            "```",
            "",
            "## Mensajes resumidos",
            "",
            str(summarized_message_count) if summarized_message_count is not None else "_No provisto_",
            "",
        ])

        lines.extend(_render_plain_list("Recuerdos relevantes", relevant_memories or []))

        lines.extend([
            "## Memoria semantica",
            "",
            "```markdown",
            _clean_text(semantic_memory_block or "_Vacio_"),
            "```",
            "",
            "## Mensajes enviados al modelo",
            "",
            _render_message_list(messages_sent, collapse=False),
        ])

        if source_messages is not None:
            lines.extend([
                "",
                "## Historial usado para construir el contexto",
                "",
                _render_message_list(source_messages, collapse=True),
            ])

        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        self._log("CHAT_LOG", f"Turno {turn_index} guardado en {path.name}")
        return path

    def delete_chat_session(self, session_id: str) -> bool:
        return self._with_chat_store(lambda s: s.delete_session(session_id))

    def rename_chat_session(self, session_id: str, title: str) -> bool:
        return self._with_chat_store(lambda s: s.rename_session(session_id, title))

    # ------------------------------------------------------------------
    # Chat memory (ChromaDB — memoria semántica conversacional)
    # ------------------------------------------------------------------

    def _init_chat_memory(self) -> None:
        """Inicializa el gestor de memoria semántica del chat."""
        if not self._char_dir:
            self._chat_memory = None
            return
        from ..db.chat_memory import ChatMemoryManager
        # El logger de CharacterManager espera (tag, msg), ChatMemoryManager espera (msg,)
        _chat_logger = lambda msg: self._logger_fn("CHAT_MEM", msg)
        self._chat_memory = ChatMemoryManager(
            char_dir=self._char_dir,
            log_fn=_chat_logger,
        )
        self._chat_memory.initialize()

    def search_chat_memories(self, query: str, top_k: int = 5) -> list[dict]:
        """Busca recuerdos conversacionales relevantes por similitud semántica.

        Args:
            query: texto de búsqueda
            top_k: cantidad de resultados

        Returns:
            lista de recuerdos con document, metadata, similarity
        """
        if not self._chat_memory or not self._chat_memory.is_available:
            return []
        return self._chat_memory.search_memories(query=query, top_k=top_k)

    def get_chat_memories_block(self, query: str, top_k: int = 5) -> str:
        """Busca recuerdos y los formatea como bloque de texto para el prompt."""
        if not self._chat_memory or not self._chat_memory.is_available:
            return ""
        mems = self._chat_memory.search_memories(query=query, top_k=top_k)
        return self._chat_memory.format_memories_block(mems)

    def add_chat_memory(
        self,
        text: str,
        session_id: str = "",
        importance: float = 0.5,
        topic: str = "general",
    ) -> str | None:
        """Guarda un recuerdo semántico del chat manualmente."""
        if not self._chat_memory or not self._chat_memory.is_available:
            return None
        doc_id = self._chat_memory.add_memory(
            text=text,
            session_id=session_id,
            importance=importance,
            topic=topic,
        )
        if doc_id:
            self._prompt_dirty = True
        return doc_id

    def _ensure_dir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def _read_json_dict(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _read_json(self, path: Path, dataclass_type: type) -> dict:
        data = self._read_json_dict(path)
        valid = {}
        for f in dataclass_type.__dataclass_fields__:
            if f in data:
                valid[f] = data[f]
        return valid

    def _write_json(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, path)
        except Exception as e:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise e

    def _log(self, tag: str, message: str) -> None:
        self._logger_fn(tag, message)
        if self._loading:
            self._load_logs.append(f"[{tag}] {message}")
