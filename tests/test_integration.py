"""Tests de integración para vtool_character_v2."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from vtool_character_v2.types import CharacterLoadResult


class TestCharacterLoading:
    """Fase 4 y 5: Carga de personaje sin estado parcial."""

    def test_load_character_success(self, loaded_cm, create_test_character):
        assert loaded_cm.is_loaded
        assert loaded_cm.character_name == create_test_character
        assert loaded_cm.identity.name == create_test_character

    def test_load_character_result(self, loaded_cm, create_test_character):
        result = loaded_cm.last_load_result
        assert result is not None
        assert result.success is True
        assert result.character_name == create_test_character
        assert isinstance(result, CharacterLoadResult)

    def test_load_nonexistent_character(self, cm):
        with pytest.raises(ValueError, match="no encontrado"):
            cm.load_character("personaje_que_no_existe")
        assert not cm.is_loaded

    def test_load_character_creates_directories(self, cm, create_test_character, temp_base_dir):
        char_dir = temp_base_dir / create_test_character
        cm.load_character(create_test_character)
        assert (char_dir / "_memory").exists()
        assert (char_dir / "_memory" / "episodes").exists()
        assert (char_dir / "state").exists()
        assert (char_dir / "mods").exists()

    def test_dna_is_loaded(self, loaded_cm):
        assert loaded_cm.identity.name == "test_personaje"
        assert "curioso" in loaded_cm.personality_dna.traits


class TestChromaClose:
    """Fase 1: ChromaStore.close() no destructivo."""

    def test_close_does_not_delete_collection(self, temp_base_dir):
        from vtool_character_v2.db.chroma_store import ChromaStore

        db_path = temp_base_dir / "chroma_test"
        store = ChromaStore(db_path, "test_collection")
        ok = store.initialize()
        assert ok is True

        store.add_document("doc1", "test document", {"key": "val"})
        assert store.count() == 1

        store.close()
        assert store._client is None
        assert store._collection is None

        store2 = ChromaStore(db_path, "test_collection")
        store2.initialize()
        assert store2.count() == 1, "close() no debe borrar datos persistentes"
        store2.close()

    def test_drop_collection_removes_data(self, temp_base_dir):
        from vtool_character_v2.db.chroma_store import ChromaStore

        db_path = temp_base_dir / "chroma_drop_test"
        store = ChromaStore(db_path, "test_drop")
        store.initialize()
        store.add_document("doc1", "test", {"key": "val"})
        assert store.count() == 1

        store.drop_collection()

        store2 = ChromaStore(db_path, "test_drop")
        store2.initialize()
        assert store2.count() == 0, "drop_collection() debe borrar datos"
        store2.close()


class TestLLMAdapterContract:
    """Fase 3: Contrato LLMClient via adapter."""

    def test_adapter_protocol_match(self):
        from vtool_character_v2.soul import LLMClient, VToolLlamaAdapter

        assert hasattr(VToolLlamaAdapter, "is_loaded")
        assert hasattr(VToolLlamaAdapter, "generate")

        adapter = VToolLlamaAdapter.__init__
        assert callable(adapter)

    def test_adapter_without_backend(self):
        """Probar adapter sin LLM real (no debe crashear al iniciar)."""
        from vtool_character_v2.soul import VToolLlamaAdapter

        dummy = object()
        adapter = VToolLlamaAdapter(dummy)
        assert adapter.is_loaded is False

    def test_adapter_fallback_when_not_loaded(self, loaded_cm):
        """SoulGenerator debe caer a heurísticas si no hay LLM."""
        from vtool_character_v2.soul import SoulGenerator

        gen = SoulGenerator(
            character_manager=loaded_cm,
            config=None,
            llm_client=None,
        )
        assert gen._has_llm is False

    def test_llmclient_protocol_importable(self):
        from vtool_character_v2.soul import LLMClient
        import typing
        assert isinstance(LLMClient, typing._ProtocolMeta)


class TestForceRegenerate:
    """Fase 2: force_regenerate limpia _memory y legacy memory/."""

    def test_force_regenerate_cleans_legacy_path(self, temp_base_dir, cm, create_test_character):
        """Verifica que la limpieza de force_regenerate borra legacy memory/."""
        char_dir = temp_base_dir / create_test_character

        legacy_dir = char_dir / "memory"
        legacy_file = legacy_dir / "life_events.json"
        legacy_file.parent.mkdir(parents=True, exist_ok=True)
        legacy_file.write_text(json.dumps([{"event": "legacy"}]), encoding="utf-8")
        assert legacy_file.exists()

        from vtool_character_v2.soul import SoulGenerator

        gen = SoulGenerator(character_manager=cm, config=None, llm_client=None)
        gen._char_dir = char_dir
        gen._chroma = None

        gen.generate_soul(
            create_test_character,
            force_regenerate=True,
            seed=42,
            start_age_years=1,
        )

        # Legacy memory/ debe estar limpio tras regeneracion
        assert not legacy_file.exists(), "memory/life_events.json legacy debe eliminarse"

    def test_force_regenerate_rewrites_new_soul(self, temp_base_dir, cm, create_test_character):
        """Tras force_regenerate=True, el soul.json se regenera."""
        char_dir = temp_base_dir / create_test_character

        from vtool_character_v2.soul import SoulGenerator

        gen = SoulGenerator(character_manager=cm, config=None, llm_client=None)
        gen._char_dir = char_dir
        gen._chroma = None

        result = gen.generate_soul(
            create_test_character,
            force_regenerate=True,
            seed=42,
            start_age_years=1,
        )

        assert result["status"] == "complete"
        soul_path = char_dir / "soul" / "soul.json"
        assert soul_path.exists(), "Nuevo soul.json debe existir tras regeneracion"

    def test_force_regenerate_file_removal_before_generation(self, temp_base_dir, create_test_character):
        """El cleanup elimina archivos viejos ANTES de regenerar (verificacion directa del codigo)."""
        char_dir = temp_base_dir / create_test_character
        from vtool_character_v2.soul.soul_generator import SoulGenerator as SG

        # Verificar que la logica de limpieza esta en el lugar correcto del flujo
        source = open(SG.generate_soul.__code__.co_filename).read()
        lines = source.split("\n")
        found_cleanup = False
        for i, line in enumerate(lines):
            if "if force_regenerate:" in line:
                # Verificar que reference _memory y memory
                block = "\n".join(lines[i:i+20])
                assert '"_memory"' in block, "Debe limpiar _memory"
                assert '"memory"' in block, "Debe limpiar legacy memory"
                found_cleanup = True
                break
        assert found_cleanup, "Debe existir bloque force_regenerate en generate_soul"


class TestEpisodesModule:
    """Fase 4: Episodios no deben hacer referencia a _chat_store."""

    def test_save_episode_raises(self, loaded_cm):
        with pytest.raises(RuntimeError, match="DEPRECATED"):
            loaded_cm.save_episode([], "summary")

    def test_list_episodes_no_crash(self, loaded_cm):
        result = loaded_cm.list_episodes()
        assert isinstance(result, list)

    def test_load_latest_episode_no_crash(self, loaded_cm):
        loaded_cm._load_latest_episode()
        assert loaded_cm.current_episode is None


class TestSoulGeneratorFallback:
    """Fase 6: SoulGenerator sin LLM debe usar heurísticas."""

    def test_generate_random_events(self, loaded_cm, create_test_character):
        from vtool_character_v2.soul import SoulGenerator

        gen = SoulGenerator(
            character_manager=loaded_cm,
            config=None,
            llm_client=None,
        )
        events = gen._generate_random_events(age_months=360)
        assert isinstance(events, list)
        assert len(events) > 0
        for ev in events:
            assert "month" in ev
            assert "type" in ev
            assert "description" in ev

    def test_has_soul_returns_false_when_no_soul(self, loaded_cm, create_test_character):
        from vtool_character_v2.soul import SoulGenerator

        gen = SoulGenerator(
            character_manager=loaded_cm,
            config=None,
            llm_client=None,
        )
        assert gen.has_soul(create_test_character) is False

    def test_get_soul_data_returns_none(self, loaded_cm, create_test_character):
        from vtool_character_v2.soul import SoulGenerator

        gen = SoulGenerator(
            character_manager=loaded_cm,
            config=None,
            llm_client=None,
        )
        assert gen.get_soul_data(create_test_character) is None


class TestManagerBuildPrompt:
    """Compilación de prompts sin crash."""

    def test_build_system_prompt(self, loaded_cm):
        prompt = loaded_cm.build_system_prompt("Eres un asistente.")
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_build_full_system_prompt(self, loaded_cm):
        prompt = loaded_cm.build_full_system_prompt("Eres un asistente.")
        assert isinstance(prompt, str)

    def test_build_compact_system_prompt(self, loaded_cm):
        prompt = loaded_cm.build_compact_system_prompt("Eres un asistente.")
        assert isinstance(prompt, str)


class TestPromptCacheInvalidation:
    """Hallazgo 1: build_system_prompt() no debe cachear con base distinta."""

    def test_different_base_prompts_produce_different_output(self, loaded_cm):
        p1 = loaded_cm.build_system_prompt("Eres un asistente amigable.")
        p2 = loaded_cm.build_system_prompt("Eres un asistente severo.")
        assert p1 != p2, "Dos bases distintas deben producir prompts distintos"

    def test_cache_hit_with_same_base(self, loaded_cm):
        p1 = loaded_cm.build_system_prompt("Eres un asistente.")
        p2 = loaded_cm.build_system_prompt("Eres un asistente.")
        assert p1 == p2, "Misma base debe retornar el mismo prompt (cache hit)"

    def test_cache_recompiles_after_mark_dirty(self, loaded_cm):
        p1 = loaded_cm.build_system_prompt("Eres un asistente.")
        loaded_cm.mark_prompt_dirty()
        p2 = loaded_cm.build_system_prompt("Eres un asistente.")
        assert p1 == p2, "Misma base, mismo resultado, pero debe recompilar"

    def test_three_different_bases(self, loaded_cm):
        bases = ["Eres A.", "Eres B.", "Eres C."]
        results = [loaded_cm.build_system_prompt(b) for b in bases]
        assert len(set(results)) == 3, "Tres bases distintas deben producir tres prompts distintos"


class TestSnapshotRestore:
    """Hallazgo 2 y 3: snapshot/restore de CharacterManager."""

    def test_snapshot_includes_full_state(self, cm):
        snap = cm._snapshot_state()
        expected_keys = {
            "_character_name", "_char_dir", "_prompt_dirty", "_compiled_prompt_cache",
            "identity", "personality_dna", "speech", "rules", "memories",
            "runtime_state", "personality_state", "relationship_state", "active_mods",
            "_cached_prompt_hash", "_needs_rebuild", "_soul_accessor",
            "_psychology_manager", "_genome", "_core_identity", "current_episode",
        }
        assert expected_keys.issubset(snap.keys()), f"Faltan keys en snapshot: {expected_keys - snap.keys()}"

    def test_restore_rolls_back_completely(self, cm, create_test_character):
        cm.load_character(create_test_character)
        name_a = cm.character_name
        id_a = id(cm.identity)
        dna_a = cm.personality_dna

        snap = cm._snapshot_state()
        cm._character_name = "otro_parcial"
        cm._restore_state(snap)

        assert cm.character_name == name_a
        assert id(cm.identity) == id_a
        assert cm.personality_dna is dna_a

    def test_rollback_after_load_cancelled_error(self, cm, create_test_character):
        """LoadCancelledError: si ya habia personaje cargado, se restaura el anterior."""
        from vtool_character_v2.exceptions import LoadCancelledError
        from vtool_character_v2.character import base as char_base

        # Cargar personaje A
        cm.load_character(create_test_character)
        assert cm.is_loaded
        name_a = cm.character_name

        # Parchear _load_dna para que lance LoadCancelledError
        original = char_base.CharacterManager._load_dna
        char_base.CharacterManager._load_dna = lambda self: (_ for _ in ()).throw(LoadCancelledError("cancelado en test"))
        try:
            result = cm.load_character(create_test_character)
            assert not result.success, "Resultado debe indicar fallo"
            assert result.error == "Carga cancelada por nueva solicitud"
            assert cm.is_loaded, "Personaje anterior debe seguir cargado"
            assert cm.character_name == name_a
        finally:
            char_base.CharacterManager._load_dna = original

    def test_failed_load_preserves_previous_character(self, cm, temp_base_dir):
        """Cargar A, luego intentar B con error, A debe quedar intacto."""
        name_a = "personaje_a"
        identity_a = {"name": name_a, "role": "a", "age": "20", "background": "A"}
        personality_a = {"traits": ["serio"], "flaws": [], "motivations": []}
        speech_a = {"style": "formal", "verbosity": "normal", "tone": "neutral"}
        rules_a = {"core_rules": []}
        cm.create_character(name_a, identity_a, personality_a, speech_a, rules_a)
        cm.load_character(name_a)

        name_b = "personaje_b"
        cm.create_character(name_b, identity_a, personality_a, speech_a, rules_a)
        char_b_dir = temp_base_dir / name_b
        import shutil
        shutil.rmtree(str(char_b_dir / "dna"), ignore_errors=True)

        with pytest.raises(ValueError, match="no encontrado"):
            cm.load_character(name_b)

        assert cm.is_loaded, "A debe seguir cargado tras fallo de B"
        assert cm.character_name == name_a
        assert cm.identity.name == name_a


class TestRuntimeSoulManagerActive:
    """Hallazgo 4: RuntimeSoulManager.active debe reflejar estado real."""

    def test_active_false_when_no_state(self, cm, create_test_character, temp_base_dir):
        from vtool_character_v2.psychology.runtime_manager import RuntimeSoulManager
        from vtool_character_v2.psychology import PsychologySynthesizer
        from vtool_character_v2.types import Genome

        char_dir = temp_base_dir / create_test_character
        synth = PsychologySynthesizer()
        genome = Genome()
        mgr = RuntimeSoulManager(char_dir=char_dir, genome=genome, synthesizer=synth)
        assert not mgr.active, "Sin synthesize, active debe ser False"

    def test_active_true_after_synthesize(self, cm, create_test_character, temp_base_dir):
        from vtool_character_v2.psychology.runtime_manager import RuntimeSoulManager
        from vtool_character_v2.psychology import PsychologySynthesizer
        from vtool_character_v2.types import Genome

        char_dir = temp_base_dir / create_test_character
        synth = PsychologySynthesizer()
        genome = Genome()
        mgr = RuntimeSoulManager(char_dir=char_dir, genome=genome, synthesizer=synth)
        mgr.synthesize_psychology()
        mgr.synthesize_persona()
        assert mgr.active, "Tras synthesize completo, active debe ser True"


class TestCacheHitReal:
    """F1: El cache de prompt debe hacer hit real en llamadas consecutivas iguales."""

    def test_needs_rebuild_becomes_false_after_compile(self, loaded_cm):
        assert loaded_cm._needs_rebuild is True, "Post-load debe necesitar rebuild"
        loaded_cm.build_system_prompt("Eres un asistente.")
        assert loaded_cm._needs_rebuild is False, "Tras compilar, rebuild debe ser False"

    def test_cache_hits_on_identical_consecutive_calls(self, loaded_cm):
        p1 = loaded_cm.build_system_prompt("Eres un asistente.")
        # Segunda llamada debe ser cache hit
        p2 = loaded_cm.build_system_prompt("Eres un asistente.")
        assert p1 is p2, "Cache hit debe retornar el MISMO objeto (misma identidad)"

    def test_cache_misses_after_add_memory(self, loaded_cm):
        loaded_cm.build_system_prompt("Eres un asistente.")
        loaded_cm.add_memory("Nuevo recuerdo.")
        assert loaded_cm._needs_rebuild is True, "add_memory debe marcar needs_rebuild"
        p2 = loaded_cm.build_system_prompt("Eres un asistente.")
        assert p2 is not None


class TestManagerRuntimeStates:
    """F2: Estados runtime del manager post-load."""

    def test_is_loaded_after_successful_load(self, cm, create_test_character):
        cm.load_character(create_test_character)
        assert cm.is_loaded is True
        assert cm.character_name == create_test_character
        assert cm.loading is False

    def test_not_loaded_after_failed_load(self, cm):
        with pytest.raises(ValueError):
            cm.load_character("inexistente")
        assert cm.is_loaded is False
        assert cm.character_name is None
        assert cm.loading is False

    def test_loading_flag_during_load(self, cm, create_test_character):
        cm.load_character(create_test_character)
        assert cm.loading is False

    def test_soul_accessor_none_without_soul(self, cm, create_test_character, temp_base_dir):
        cm.load_character(create_test_character)
        assert cm._soul_accessor is None or not cm._soul_accessor.is_active


class TestChatDbPaths:
    """F1: Rutas de chat SQLite."""

    def test_get_memory_dir_raises_without_character(self, cm):
        with pytest.raises(RuntimeError, match="No hay personaje"):
            cm.get_memory_dir()

    def test_get_memory_dir_returns_correct_path(self, cm, create_test_character):
        cm.load_character(create_test_character)
        expected = cm._char_dir / "_memory"
        assert cm.get_memory_dir() == expected

    def test_get_chat_db_path_returns_correct_path(self, cm, create_test_character):
        cm.load_character(create_test_character)
        expected = cm._char_dir / "_memory" / "chat_history.db"
        assert cm.get_chat_db_path() == expected


class TestChatSessionWrappers:
    """F1: Wrappers de sesiones sobre SQLiteChatStore."""

    def test_list_chat_sessions_empty(self, cm, create_test_character):
        cm.load_character(create_test_character)
        assert cm.list_chat_sessions() == []

    def test_list_after_creating_session(self, cm, create_test_character):
        cm.load_character(create_test_character)
        from vtool_llama_v2.chat_store import SQLiteChatStore

        store = SQLiteChatStore(str(cm.get_chat_db_path()))
        try:
            store.initialize()
            store.upsert_session("chat_001", character_name=cm.character_name, title="Mi chat", summary="")
        finally:
            store.close()

        sessions = cm.list_chat_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "chat_001"

    def test_delete_chat_session(self, cm, create_test_character):
        cm.load_character(create_test_character)
        from vtool_llama_v2.chat_store import SQLiteChatStore

        store = SQLiteChatStore(str(cm.get_chat_db_path()))
        try:
            store.initialize()
            store.upsert_session("chat_001", character_name=cm.character_name, title="", summary="")
        finally:
            store.close()

        assert cm.delete_chat_session("chat_001") is True
        assert cm.list_chat_sessions() == []

    def test_rename_chat_session(self, cm, create_test_character):
        cm.load_character(create_test_character)
        from vtool_llama_v2.chat_store import SQLiteChatStore

        store = SQLiteChatStore(str(cm.get_chat_db_path()))
        try:
            store.initialize()
            store.upsert_session("chat_001", character_name=cm.character_name, title="Viejo titulo", summary="")
        finally:
            store.close()

        assert cm.rename_chat_session("chat_001", "Nuevo titulo") is True
        store = SQLiteChatStore(str(cm.get_chat_db_path()))
        try:
            store.initialize()
            session = store.get_session("chat_001")
            assert session["title"] == "Nuevo titulo"
        finally:
            store.close()

    def test_delete_nonexistent_session(self, cm, create_test_character):
        cm.load_character(create_test_character)
        assert cm.delete_chat_session("no_existe") is False


class TestEpisodesCompatibility:
    """F2: episodes.py como capa de compatibilidad sobre SQLite."""

    def test_list_episodes_includes_sqlite_sessions(self, cm, create_test_character):
        cm.load_character(create_test_character)
        from vtool_llama_v2.chat_store import SQLiteChatStore

        store = SQLiteChatStore(str(cm.get_chat_db_path()))
        try:
            store.initialize()
            store.upsert_session("chat_001", character_name=cm.character_name, title="", summary="Resumen")
        finally:
            store.close()

        episodes = cm.list_episodes()
        sqlite_eps = [e for e in episodes if e.get("source") == "sqlite"]
        assert len(sqlite_eps) == 1
        assert sqlite_eps[0]["session_id"] == "chat_001"

    def test_load_episode_with_session_id(self, cm, create_test_character):
        cm.load_character(create_test_character)
        from vtool_llama_v2.chat_store import SQLiteChatStore

        store = SQLiteChatStore(str(cm.get_chat_db_path()))
        try:
            store.initialize()
            store.upsert_session("chat_001", character_name=cm.character_name, title="", summary="")
        finally:
            store.close()

        cm.load_episode("chat_001")
        assert cm.current_episode is not None
        assert cm.current_episode.episode_id == "chat_001"

    def test_delete_episode_with_session_id(self, cm, create_test_character):
        cm.load_character(create_test_character)
        from vtool_llama_v2.chat_store import SQLiteChatStore

        store = SQLiteChatStore(str(cm.get_chat_db_path()))
        try:
            store.initialize()
            store.upsert_session("chat_001", character_name=cm.character_name, title="", summary="")
        finally:
            store.close()

        assert cm.delete_episode("chat_001") is True
        assert cm.list_chat_sessions() == []


class TestChatIntegrationScope:
    """F4: Tests de scope, metadata y precedencia en integración SQLite."""

    def test_load_episode_sqlite_with_metadata(self, cm, create_test_character):
        """Persistir sesión con title/summary/character_name y verificar snapshot."""
        cm.load_character(create_test_character)
        from vtool_llama_v2.chat_store import SQLiteChatStore

        store = SQLiteChatStore(str(cm.get_chat_db_path()))
        try:
            store.initialize()
            store.upsert_session(
                "chat_001",
                character_name=cm.character_name,
                title="Mi conversación",
                summary="Resumen importante",
            )
        finally:
            store.close()

        cm.load_episode("chat_001")
        snap = cm.current_episode
        assert snap is not None
        assert snap.title == "Mi conversación"
        assert snap.summary == "Resumen importante"
        assert snap.character_name == cm.character_name
        assert snap.source == "sqlite"
        assert snap.episode_id == "chat_001"

    def test_load_latest_episode_prefers_sqlite(self, cm, create_test_character, temp_base_dir, monkeypatch):
        """Tanto SQLite como legacy disponibles: SQLite gana."""
        cm.load_character(create_test_character)

        from vtool_llama_v2.chat_store import SQLiteChatStore
        store = SQLiteChatStore(str(cm.get_chat_db_path()))
        try:
            store.initialize()
            store.upsert_session("chat_002", character_name=cm.character_name, title="SQLite", summary="")
        finally:
            store.close()

        # Crear episodio legacy más viejo
        ep_dir = cm._char_dir / "_memory" / "episodes"
        ep_dir.mkdir(parents=True, exist_ok=True)
        (ep_dir / "episode_001.json").write_text(
            '{"episode_id": 1, "timestamp": "2024-01-01", "summary": "legacy", "messages": []}',
            encoding="utf-8",
        )

        cm._load_latest_episode()
        assert cm.current_episode is not None
        assert cm.current_episode.source == "sqlite"
        assert cm.current_episode.episode_id == "chat_002"

    def test_delete_sqlite_does_not_touch_legacy(self, cm, create_test_character):
        """Borrar sesión SQLite no afecta archivos JSON legacy."""
        cm.load_character(create_test_character)

        from vtool_llama_v2.chat_store import SQLiteChatStore
        store = SQLiteChatStore(str(cm.get_chat_db_path()))
        try:
            store.initialize()
            store.upsert_session("chat_001", character_name=cm.character_name, title="", summary="")
        finally:
            store.close()

        # Crear episodio legacy
        ep_dir = cm._char_dir / "_memory" / "episodes"
        ep_dir.mkdir(parents=True, exist_ok=True)
        legacy_file = ep_dir / "episode_001.json"
        legacy_file.write_text('{"episode_id": 1, "messages": []}', encoding="utf-8")

        cm.delete_chat_session("chat_001")
        assert legacy_file.exists(), "Legacy no debe tocarse al borrar SQLite"

    def test_rename_reflected_in_list_episodes(self, cm, create_test_character):
        """Renombrar sesión se refleja en list_episodes()."""
        cm.load_character(create_test_character)
        from vtool_llama_v2.chat_store import SQLiteChatStore

        store = SQLiteChatStore(str(cm.get_chat_db_path()))
        try:
            store.initialize()
            store.upsert_session("chat_001", character_name=cm.character_name, title="Viejo", summary="")
        finally:
            store.close()

        cm.rename_chat_session("chat_001", "Nuevo")

        episodes = cm.list_episodes()
        sqlite_eps = [e for e in episodes if e.get("source") == "sqlite"]
        assert len(sqlite_eps) == 1
        assert sqlite_eps[0]["title"] == "Nuevo"

    def test_load_latest_episode_picks_newest_from_multiple_sqlite(self, cm, create_test_character):
        """Con múltiples sesiones SQLite, _load_latest_episode elige la más reciente."""
        cm.load_character(create_test_character)
        from vtool_llama_v2.chat_store import SQLiteChatStore

        store = SQLiteChatStore(str(cm.get_chat_db_path()))
        try:
            store.initialize()
            store.upsert_session("chat_viejo", character_name=cm.character_name, title="Viejo", summary="")
            store.upsert_session("chat_nuevo", character_name=cm.character_name, title="Nuevo", summary="")
        finally:
            store.close()

        cm._load_latest_episode()
        assert cm.current_episode is not None
        assert cm.current_episode.source == "sqlite"
        # Debe elegir la más reciente (chat_nuevo fue creada después)
        assert cm.current_episode.episode_id == "chat_nuevo"
        assert cm.current_episode.title == "Nuevo"

    def test_get_chat_session_returns_metadata(self, cm, create_test_character):
        """get_chat_session() retorna metadatos completos."""
        cm.load_character(create_test_character)
        from vtool_llama_v2.chat_store import SQLiteChatStore

        store = SQLiteChatStore(str(cm.get_chat_db_path()))
        try:
            store.initialize()
            store.upsert_session("chat_001", character_name=cm.character_name, title="Test", summary="Resumen")
        finally:
            store.close()

        session = cm.get_chat_session("chat_001")
        assert session is not None
        assert session["session_id"] == "chat_001"
        assert session["title"] == "Test"
        assert session["summary"] == "Resumen"
        assert session["character_name"] == cm.character_name
