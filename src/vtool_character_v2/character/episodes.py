"""episodes.py — Capa de compatibilidad para episodios (file-based + SQLite).

La persistencia de sesiones se maneja via SQLite (chat_history.db).
Este módulo ofrece wrappers de compatibilidad que unifican:
- sesiones modernas en SQLite (desde vtool_llama_v2 via CharacterManager)
- episodios legacy en JSON (episode_*.json)

Para nuevo código, usar los métodos directos en CharacterManager:
- list_chat_sessions()
- get_chat_session()
- delete_chat_session()
- rename_chat_session()
"""
from __future__ import annotations

from ..types import EpisodeSnapshot
from .base import CharacterManager


def _load_latest_episode(self: CharacterManager) -> None:
    """Carga el último episodio (SQLite primero, luego legacy JSON).

    La sesión SQLite más reciente tiene precedencia sobre legacy JSON.
    El snapshot incluye source='sqlite' si viene de SQLite.
    """
    self.current_episode = None
    if not self._char_dir:
        return

    # 1. Intentar SQLite (fuente principal)
    # list_chat_sessions() devuelve updated_at DESC, sessions[0] = más reciente.
    # Usamos max() con key explícito por resiliencia ante cambios de orden.
    try:
        sessions = self.list_chat_sessions()
        if sessions:
            latest = max(sessions, key=lambda s: s.get("updated_at", s.get("created_at", "")))
            msgs = self.load_chat_session_messages(latest["session_id"])
            self.current_episode = EpisodeSnapshot(
                episode_id=latest["session_id"],
                timestamp=latest.get("created_at", ""),
                summary=latest.get("summary", ""),
                messages=msgs,
                title=latest.get("title", ""),
                character_name=latest.get("character_name", ""),
                source="sqlite",
            )
            return
    except Exception:
        pass

    # 2. Fallback legacy JSON
    episodes_dir = self._char_dir / "_memory" / "episodes"
    if not episodes_dir.exists():
        return
    try:
        paths = sorted(episodes_dir.glob("episode_*.json"))
        if not paths:
            return
        import json
        data = json.loads(paths[-1].read_text(encoding="utf-8"))
        self.current_episode = EpisodeSnapshot(
            episode_id=data.get("episode_id", 0),
            timestamp=data.get("timestamp", ""),
            summary=data.get("summary", ""),
            messages=data.get("messages", []),
            source="legacy",
        )
    except Exception:
        self.current_episode = None


CharacterManager._load_latest_episode = _load_latest_episode


def save_episode(self: CharacterManager, messages: list[dict], summary: str) -> EpisodeSnapshot:
    raise RuntimeError(
        "save_episode() en CharacterManager está DEPRECATED. "
        "Usar list_chat_sessions() / delete_chat_session() / "
        "o vtool_llama_v2.Session para persistencia de conversaciones."
    )


CharacterManager.save_episode = save_episode


def _list_legacy_episodes(self: CharacterManager) -> list[dict]:
    """Lista episodios legacy desde archivos episode_*.json."""
    episodes_dir = self._char_dir / "_memory" / "episodes"
    if not episodes_dir or not episodes_dir.exists():
        return []
    result = []
    for path in sorted(episodes_dir.glob("episode_*.json")):
        try:
            import json
            data = json.loads(path.read_text(encoding="utf-8"))
            result.append({
                "source": "legacy",
                "file": path.name,
                "episode_id": data.get("episode_id", 0),
                "timestamp": data.get("timestamp", ""),
                "summary": data.get("summary", ""),
                "message_count": len(data.get("messages", [])),
            })
        except Exception:
            continue
    return result


CharacterManager._list_legacy_episodes = _list_legacy_episodes


def list_episodes(self: CharacterManager) -> list[dict]:
    """Lista sesiones (SQLite) + episodios legacy (JSON).

    Retorna lista combinada ordenada por timestamp descendente.
    Cada entrada incluye 'source' ('sqlite' | 'legacy') para
    que el caller pueda distinguir el origen.
    """
    if not self._char_dir:
        return []

    result = []

    # 1. SQLite sessions (fuente principal)
    try:
        for s in self.list_chat_sessions():
            result.append({
                "source": "sqlite",
                "session_id": s["session_id"],
                "timestamp": s.get("created_at", ""),
                "summary": s.get("summary", ""),
                "title": s.get("title", ""),
                "message_count": 0,
            })
    except Exception:
        pass

    # 2. Legacy JSON episodes
    result.extend(self._list_legacy_episodes())

    result.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return result


CharacterManager.list_episodes = list_episodes


def load_episode(self: CharacterManager, episode_id: int | str) -> None:
    """Carga un episodio: session_id (str) → SQLite, episode_id (int) → legacy.

    Para sesiones SQLite el snapshot incluye source='sqlite', title y character_name.
    Para episodios legacy el snapshot tiene source='legacy'.

    Args:
        episode_id: ID de sesión (str, SQLite) o número de episodio (int, legacy).
    """
    if not self._char_dir:
        raise RuntimeError("No hay personaje cargado.")

    if isinstance(episode_id, str):
        session = self.get_chat_session(episode_id)
        if session is None:
            raise ValueError(f"Sesión '{episode_id}' no encontrada.")
        msgs = self.load_chat_session_messages(episode_id)
        self.current_episode = EpisodeSnapshot(
            episode_id=episode_id,
            timestamp=session.get("created_at", ""),
            summary=session.get("summary", ""),
            messages=msgs,
            title=session.get("title", ""),
            character_name=session.get("character_name", ""),
            source="sqlite",
        )
        return

    # Legacy: episode_id es int
    path = self._char_dir / "_memory" / "episodes" / f"episode_{episode_id:03d}.json"
    if not path.exists():
        raise ValueError(f"Episodio #{episode_id} no encontrado.")
    import json
    data = json.loads(path.read_text(encoding="utf-8"))
    self.current_episode = EpisodeSnapshot(
        episode_id=data.get("episode_id", episode_id),
        timestamp=data.get("timestamp", ""),
        summary=data.get("summary", ""),
        messages=data.get("messages", []),
        source="legacy",
    )


CharacterManager.load_episode = load_episode


def delete_episode(self: CharacterManager, episode_id: int | str) -> bool:
    """Elimina un episodio: session_id (str) → SQLite, episode_id (int) → legacy.

    La eliminación SQLite no afecta archivos legacy y viceversa.
    """
    if not self._char_dir:
        return False

    if isinstance(episode_id, str):
        try:
            return self.delete_chat_session(episode_id)
        except Exception:
            return False

    # Legacy: episode_id es int
    path = self._char_dir / "_memory" / "episodes" / f"episode_{episode_id:03d}.json"
    if not path.exists():
        return False
    path.unlink()
    return True


CharacterManager.delete_episode = delete_episode
