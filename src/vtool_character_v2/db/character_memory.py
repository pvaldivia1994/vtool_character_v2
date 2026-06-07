"""character_memory.py - Persistencia SQLite para memorias del character.

Esta tabla guarda la memoria fija/relevante del personaje.
Se usa como fuente principal y puede migrar desde legacy long_term.json
si la base está vacía.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from ..types import ContextSummary, MemoryEntry


class CharacterMemoryStore:
    """Almacén SQLite de memorias persistentes del character."""

    def __init__(self, db_path: Path, log_fn: Optional[Callable[[str], None]] = None):
        self._db_path = Path(db_path)
        self._log = log_fn or (lambda msg: None)

    @property
    def db_path(self) -> Path:
        return self._db_path

    def initialize(self) -> bool:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            self._ensure_schema(conn)
            self._migrate_context_summaries_if_needed(conn)
            conn.commit()
        return True

    def _migrate_context_summaries_if_needed(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='context_summaries'"
        ).fetchone()
        if not row:
            return

        info = conn.execute("PRAGMA table_info(context_summaries)").fetchall()
        has_id = any(col[1] == "id" for col in info)
        if has_id:
            return

        conn.execute("ALTER TABLE context_summaries RENAME TO context_summaries_legacy")
        conn.execute(
            """
            CREATE TABLE context_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                summarized_message_count INTEGER NOT NULL DEFAULT 0,
                summary_version INTEGER NOT NULL DEFAULT 1,
                character_name TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                model_name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(session_id, summary_version)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_context_summaries_character_name
            ON context_summaries(character_name, updated_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_context_summaries_session
            ON context_summaries(session_id, summary_version DESC, updated_at DESC)
            """
        )
        legacy_rows = conn.execute("SELECT * FROM context_summaries_legacy ORDER BY updated_at ASC").fetchall()
        for row in legacy_rows:
            conn.execute(
                """
                INSERT INTO context_summaries (
                    session_id, summary, summarized_message_count, summary_version,
                    character_name, title, model_name, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["session_id"],
                    row["summary"] or "",
                    int(row["summarized_message_count"] or 0),
                    int(row["summary_version"] or 1),
                    row["character_name"] or "",
                    row["title"] or "",
                    row["model_name"] or "",
                    row["created_at"] or self._now(),
                    row["updated_at"] or self._now(),
                ),
            )
        conn.execute("DROP TABLE context_summaries_legacy")

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS character_memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                priority REAL NOT NULL DEFAULT 0.5,
                always_include INTEGER NOT NULL DEFAULT 0,
                tags TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_character_memories_priority
            ON character_memories(priority DESC, always_include DESC, created_at DESC)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS context_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                summarized_message_count INTEGER NOT NULL DEFAULT 0,
                summary_version INTEGER NOT NULL DEFAULT 1,
                character_name TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                model_name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(session_id, summary_version)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_context_summaries_character_name
            ON context_summaries(character_name, updated_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_context_summaries_session
            ON context_summaries(session_id, summary_version DESC, updated_at DESC)
            """
        )

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def count(self) -> int:
        if not self._db_path.exists():
            return 0
        with self._connect() as conn:
            self._ensure_schema(conn)
            row = conn.execute("SELECT COUNT(*) AS count FROM character_memories").fetchone()
            return int(row["count"]) if row else 0

    def load_all(self) -> list[MemoryEntry]:
        if not self._db_path.exists():
            return []
        with self._connect() as conn:
            self._ensure_schema(conn)
            rows = conn.execute(
                """
                SELECT id, content, priority, always_include, tags
                FROM character_memories
                ORDER BY always_include DESC, priority DESC, created_at ASC
                """
            ).fetchall()

        memories: list[MemoryEntry] = []
        for row in rows:
            try:
                tags = json.loads(row["tags"]) if row["tags"] else []
            except Exception:
                tags = []
            if not isinstance(tags, list):
                tags = []
            memories.append(
                MemoryEntry(
                    id=row["id"] or "",
                    content=row["content"] or "",
                    priority=float(row["priority"] or 0.5),
                    always_include=bool(row["always_include"]),
                    tags=[str(tag) for tag in tags],
                )
            )
        return memories

    def replace_all(self, memories: list[MemoryEntry]) -> None:
        with self._connect() as conn:
            self._ensure_schema(conn)
            conn.execute("DELETE FROM character_memories")
            for mem in memories:
                self._insert_or_replace(conn, mem)
            conn.commit()

    def add_memory(self, memory: MemoryEntry) -> None:
        with self._connect() as conn:
            self._ensure_schema(conn)
            self._insert_or_replace(conn, memory)
            conn.commit()

    def upsert_context_summary(
        self,
        session_id: str,
        summary: str,
        summarized_message_count: int,
        character_name: str = "",
        title: str = "",
        model_name: str = "",
    ) -> None:
        now = self._now()
        with self._connect() as conn:
            self._ensure_schema(conn)
            row = conn.execute(
                "SELECT MAX(summary_version) AS version FROM context_summaries WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            version = int(row["version"] or 0) + 1 if row else 1
            conn.execute(
                """
                INSERT INTO context_summaries (
                    session_id, summary, summarized_message_count, summary_version,
                    character_name, title, model_name, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    summary,
                    max(0, int(summarized_message_count)),
                    version,
                    character_name,
                    title,
                    model_name,
                    now,
                    now,
                ),
            )
            conn.commit()

    def get_context_summary(self, session_id: str) -> ContextSummary | None:
        if not self._db_path.exists():
            return None
        with self._connect() as conn:
            self._ensure_schema(conn)
            row = conn.execute(
                """
                SELECT * FROM context_summaries
                WHERE session_id = ?
                ORDER BY summary_version DESC, updated_at DESC, id DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if not row:
                return None
            return ContextSummary(
                session_id=row["session_id"],
                summary=row["summary"] or "",
                summarized_message_count=int(row["summarized_message_count"] or 0),
                summary_version=int(row["summary_version"] or 1),
                character_name=row["character_name"] or "",
                title=row["title"] or "",
                model_name=row["model_name"] or "",
                created_at=row["created_at"] or "",
                updated_at=row["updated_at"] or "",
            )

    def list_context_summaries(self, character_name: str | None = None) -> list[ContextSummary]:
        if not self._db_path.exists():
            return []
        with self._connect() as conn:
            self._ensure_schema(conn)
            parts = ["SELECT * FROM context_summaries WHERE 1=1"]
            params: list[object] = []
            if character_name is not None:
                parts.append("AND character_name = ?")
                params.append(character_name)
            parts.append("ORDER BY session_id ASC, summary_version ASC, updated_at ASC, id ASC")
            rows = conn.execute(" ".join(parts), params).fetchall()
            return [
                ContextSummary(
                    session_id=row["session_id"],
                    summary=row["summary"] or "",
                    summarized_message_count=int(row["summarized_message_count"] or 0),
                    summary_version=int(row["summary_version"] or 1),
                    character_name=row["character_name"] or "",
                    title=row["title"] or "",
                    model_name=row["model_name"] or "",
                    created_at=row["created_at"] or "",
                    updated_at=row["updated_at"] or "",
                )
                for row in rows
            ]

    def delete_context_summary(self, session_id: str) -> bool:
        with self._connect() as conn:
            self._ensure_schema(conn)
            cur = conn.execute("DELETE FROM context_summaries WHERE session_id = ?", (session_id,))
            conn.commit()
            return cur.rowcount > 0

    def clear(self) -> None:
        if not self._db_path.exists():
            return
        with self._connect() as conn:
            self._ensure_schema(conn)
            conn.execute("DELETE FROM character_memories")
            conn.execute("DELETE FROM context_summaries")
            conn.commit()

    def _insert_or_replace(self, conn: sqlite3.Connection, memory: MemoryEntry) -> None:
        stamp = self._now()
        conn.execute(
            """
            INSERT INTO character_memories (
                id, content, priority, always_include, tags, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                content=excluded.content,
                priority=excluded.priority,
                always_include=excluded.always_include,
                tags=excluded.tags,
                updated_at=excluded.updated_at
            """,
            (
                memory.id,
                memory.content,
                float(memory.priority),
                1 if memory.always_include else 0,
                json.dumps(memory.tags or [], ensure_ascii=False),
                stamp,
                stamp,
            ),
        )
