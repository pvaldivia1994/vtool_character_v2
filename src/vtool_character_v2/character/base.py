"""
Gestor del Character System para vtool_character_v2 — Clase base.

Maneja la arquitectura completa de personajes:
  - DNA (inmutable): identity.json, personality.json, speech.json, rules.json
  - Memory (mutable): long_term.json
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
                    mems.append({
                        "id": str(uuid.uuid4())[:8],
                        "content": mem,
                        "priority": 1.0,
                        "always_include": True,
                        "tags": [],
                    })
            self._write_json(char_dir / "_memory" / "long_term.json", {"memories": mems})

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

    def build_system_prompt(self, base_system_prompt: str, config: Optional[ConfigSchema] = None) -> str:
        key = (base_system_prompt, self._config_cache_key(config))
        if (not self._prompt_dirty and not self._needs_rebuild
                and self._compiled_prompt_cache and self._last_prompt_cache_key == key):
            return self._compiled_prompt_cache

        if config and getattr(config, "compact_system_prompt", False):
            self._compiled_prompt_cache = self._compiler.compile_compact_prompt(base_system_prompt, config)
        else:
            self._compiled_prompt_cache = self._compiler.compile_static_prompt(base_system_prompt, config)
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

    def build_full_system_prompt(self, base_system_prompt: str, config: Optional[ConfigSchema] = None) -> str:
        return self._compiler.compile_full_prompt(base_system_prompt, config)

    def build_compact_system_prompt(self, base_system_prompt: str, config: Optional[ConfigSchema] = None) -> str:
        return self._compiler.compile_compact_prompt(base_system_prompt, config)

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

    def get_chat_db_path(self) -> Path:
        """Ruta a la base SQLite de historial conversacional."""
        return self.get_memory_dir() / "chat_history.db"

    def _with_chat_store(self, fn):
        from vtool_llama_v2.chat_store import SQLiteChatStore
        store = SQLiteChatStore(str(self.get_chat_db_path()))
        try:
            store.initialize()
            return fn(store)
        finally:
            store.close()

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

    def delete_chat_session(self, session_id: str) -> bool:
        return self._with_chat_store(lambda s: s.delete_session(session_id))

    def rename_chat_session(self, session_id: str, title: str) -> bool:
        return self._with_chat_store(lambda s: s.rename_session(session_id, title))

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
