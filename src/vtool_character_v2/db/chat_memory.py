"""chat_memory.py — Memoria semántica conversacional con ChromaDB.

Guarda recuerdos resumidos del chat (no el transcript crudo).
Cada personaje tiene su propia colección en _memory/chat_memory/.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .chroma_store import ChromaStore


class ChatMemoryManager:
    """Maneja la memoria semántica conversacional de un personaje.

    Almacena y recupera recuerdos resumidos del chat usando ChromaDB.
    Cada personaje tiene su propia colección en _memory/chat_memory/.
    """

    def __init__(
        self,
        char_dir: Path,
        log_fn: Optional[Callable] = None,
        top_k: int = 5,
    ):
        self._char_dir = char_dir
        self._log = log_fn or (lambda msg: None)
        self._top_k = top_k
        self._store: Optional[ChromaStore] = None

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def initialize(self) -> bool:
        db_path = self._char_dir / "_memory" / "chat_memory"
        self._store = ChromaStore(
            db_path=db_path,
            collection_name="chat_memories",
            log_fn=self._log,
        )
        ok = self._store.initialize()
        if ok:
            self._log(f"[CHAT_MEMORY] Inicializada en {db_path}")
        else:
            self._log("[CHAT_MEMORY] ChromaDB no disponible — memoria semántica desactivada")
        return ok

    def close(self) -> None:
        if self._store:
            self._store.close()

    @property
    def is_available(self) -> bool:
        return self._store is not None and self._store.is_available

    @property
    def memory_count(self) -> int:
        if not self._store:
            return 0
        return self._store.count()

    # ------------------------------------------------------------------
    # Guardar recuerdos
    # ------------------------------------------------------------------

    def add_memory(
        self,
        text: str,
        session_id: str = "",
        importance: float = 0.5,
        topic: str = "general",
        metadata: Optional[dict] = None,
    ) -> str | None:
        """Guarda un recuerdo semántico del chat.

        Args:
            text: texto resumido del recuerdo
            session_id: sesión asociada (opcional)
            importance: 0.0 a 1.0
            topic: categoría temática
            metadata: metadatos adicionales
        """
        if not self._store or not self._store.is_available:
            return None

        doc_id = f"chat_mem_{uuid.uuid4().hex[:12]}"
        meta = {
            "type": "chat_memory",
            "session_id": session_id,
            "importance": importance,
            "topic": topic,
            "created_at": datetime.now().isoformat(),
        }
        if metadata:
            meta.update(metadata)

        self._store.add_document(
            doc_id=doc_id,
            document=text,
            metadata=meta,
        )
        self._log(f"[CHAT_MEMORY] Guardado: '{text[:60]}...' (imp={importance}, topic={topic})")
        return doc_id

    # ------------------------------------------------------------------
    # Recuperar recuerdos
    # ------------------------------------------------------------------

    def search_memories(
        self,
        query: str,
        top_k: Optional[int] = None,
        where: Optional[dict] = None,
    ) -> list[dict]:
        """Busca recuerdos relevantes por similitud semántica.

        Args:
            query: texto de búsqueda
            top_k: cantidad de resultados (default: self._top_k)
            where: filtro adicional (ej: {"topic": "user_preferences"})

        Returns:
            lista de dicts con id, document, metadata, similarity
        """
        if not self._store or not self._store.is_available:
            return []

        k = top_k or self._top_k
        filter_where = {"type": "chat_memory"}
        if where:
            filter_where.update(where)

        results = self._store.search(query=query, top_k=k, where=filter_where)
        self._log(f"[CHAT_MEMORY] Búsqueda '{query[:50]}...': {len(results)} resultados")
        return results

    def get_recent_memories(self, limit: int = 10) -> list[dict]:
        """Retorna los recuerdos más recientes (sin búsqueda semántica)."""
        if not self._store or not self._store.is_available:
            return []
        docs = self._store.get_all_documents()
        docs.sort(key=lambda d: d.get("metadata", {}).get("created_at", ""), reverse=True)
        return docs[:limit]

    # ------------------------------------------------------------------
    # Prompt block
    # ------------------------------------------------------------------

    def format_memories_block(self, memories: list[dict]) -> str:
        """Formatea recuerdos como bloque de texto para el prompt."""
        if not memories:
            return ""

        parts = ["[CHAT MEMORIES — Recuerdos de conversaciones anteriores]"]
        for m in memories:
            sim = m.get("similarity", 0)
            imp = m.get("metadata", {}).get("importance", 0)
            label = "★" if imp > 0.7 else "•"
            parts.append(f"  {label} {m['document']} (rel={sim:.2f})")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Mantenimiento
    # ------------------------------------------------------------------

    def clear_all(self) -> None:
        if self._store:
            self._store.clear()
            self._log("[CHAT_MEMORY] Todos los recuerdos eliminados")

    def delete_by_session(self, session_id: str) -> None:
        """Elimina recuerdos de una sesión específica."""
        if not self._store or not self._store.is_available:
            return
        docs = self._store.get_all_documents()
        to_delete = [
            d["id"] for d in docs
            if d.get("metadata", {}).get("session_id") == session_id
        ]
        if to_delete:
            self._store.delete_ids(to_delete)
            self._log(f"[CHAT_MEMORY] {len(to_delete)} recuerdos de sesión '{session_id}' eliminados")
