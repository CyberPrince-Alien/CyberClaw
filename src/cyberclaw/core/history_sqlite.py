"""SQLite-based conversation history backend.

Drop-in replacement for the JSONL HistoryStore. Provides faster queries,
proper concurrent access, and ACID guarantees.
"""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from pydantic import BaseModel

from cyberclaw.core.events import EventSource
from cyberclaw.core.history import HistorySession, HistoryMessage, _now_iso

if TYPE_CHECKING:
    from cyberclaw.utils.config import Config


class SQLiteHistoryStore:
    """SQLite-backed history storage.

    Thread-safe via a per-thread connection + WAL mode for concurrent readers.
    """

    @staticmethod
    def from_config(config: "Config") -> "SQLiteHistoryStore":
        db_path = config.history_path / "history.db"
        return SQLiteHistoryStore(db_path)

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_schema()

    @property
    def _conn(self) -> sqlite3.Connection:
        """Per-thread connection (auto-created)."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self) -> None:
        """Create tables if they do not exist."""
        conn = self._conn
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                agent_id    TEXT NOT NULL,
                source      TEXT NOT NULL,
                title       TEXT,
                message_count INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL REFERENCES sessions(id),
                timestamp   TEXT NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL DEFAULT '',
                tool_calls  TEXT,          -- JSON-serialised list
                tool_call_id TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_updated
                ON sessions(updated_at DESC);
        """)
        conn.commit()

    # ── Session CRUD ───────────────────────────────────────────────

    def create_session(
        self,
        agent_id: str,
        session_id: str,
        source: "EventSource",
    ) -> dict[str, Any]:
        """Create a new conversation session."""
        now = _now_iso()
        self._conn.execute(
            """INSERT OR IGNORE INTO sessions
               (id, agent_id, source, title, message_count, created_at, updated_at)
               VALUES (?, ?, ?, NULL, 0, ?, ?)""",
            (session_id, agent_id, str(source), now, now),
        )
        self._conn.commit()
        return {
            "id": session_id,
            "agent_id": agent_id,
            "source": str(source),
            "title": None,
            "message_count": 0,
            "created_at": now,
            "updated_at": now,
        }

    def list_sessions(self) -> list[HistorySession]:
        """List all sessions, most recently updated first."""
        rows = self._conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
        return [
            HistorySession(
                id=r["id"],
                agent_id=r["agent_id"],
                source=r["source"],
                title=r["title"],
                message_count=r["message_count"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def get_session_info(self, session_id: str) -> HistorySession | None:
        """Get session metadata."""
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not row:
            return None
        return HistorySession(
            id=row["id"],
            agent_id=row["agent_id"],
            source=row["source"],
            title=row["title"],
            message_count=row["message_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ── Messages ───────────────────────────────────────────────────

    def save_message(self, session_id: str, message: HistoryMessage) -> None:
        """Save a message to history."""
        tool_calls_json = (
            json.dumps(message.tool_calls, ensure_ascii=False)
            if message.tool_calls
            else None
        )
        self._conn.execute(
            """INSERT INTO messages
               (session_id, timestamp, role, content, tool_calls, tool_call_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                message.timestamp,
                message.role,
                message.content,
                tool_calls_json,
                message.tool_call_id,
            ),
        )

        # Update session
        now = _now_iso()
        update_sql = "UPDATE sessions SET message_count = message_count + 1, updated_at = ? WHERE id = ?"
        self._conn.execute(update_sql, (now, session_id))

        # Auto-title from first user message
        if message.role == "user":
            row = self._conn.execute(
                "SELECT title FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if row and row["title"] is None:
                title = message.content[:50]
                if len(message.content) > 50:
                    title += "..."
                self._conn.execute(
                    "UPDATE sessions SET title = ? WHERE id = ?",
                    (title, session_id),
                )

        self._conn.commit()

    def get_messages(self, session_id: str) -> list[HistoryMessage]:
        """Get all messages for a session."""
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        result = []
        for r in rows:
            tool_calls = None
            if r["tool_calls"]:
                try:
                    tool_calls = json.loads(r["tool_calls"])
                except json.JSONDecodeError:
                    pass
            result.append(
                HistoryMessage(
                    timestamp=r["timestamp"],
                    role=r["role"],
                    content=r["content"],
                    tool_calls=tool_calls,
                    tool_call_id=r["tool_call_id"],
                )
            )
        return result

    # ── Search ─────────────────────────────────────────────────────

    def search_messages(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Full-text search across all messages."""
        rows = self._conn.execute(
            """SELECT m.*, s.agent_id, s.title as session_title
               FROM messages m
               JOIN sessions s ON m.session_id = s.id
               WHERE m.content LIKE ?
               ORDER BY m.id DESC
               LIMIT ?""",
            (f"%{query}%", limit),
        ).fetchall()
        return [
            {
                "session_id": r["session_id"],
                "agent_id": r["agent_id"],
                "session_title": r["session_title"],
                "role": r["role"],
                "content": r["content"][:200],
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]

    # ── Migration ──────────────────────────────────────────────────

    def migrate_from_jsonl(self, jsonl_store: "HistoryStore") -> int:
        """Import all sessions and messages from a JSONL HistoryStore."""
        from cyberclaw.core.history import HistoryStore as JSONLStore

        count = 0
        for session in jsonl_store.list_sessions():
            # Check if session already imported
            if self.get_session_info(session.id):
                continue

            self.create_session(
                agent_id=session.agent_id,
                session_id=session.id,
                source=session.get_source(),
            )
            # Update title and timestamps
            self._conn.execute(
                "UPDATE sessions SET title=?, created_at=?, updated_at=? WHERE id=?",
                (session.title, session.created_at, session.updated_at, session.id),
            )

            for msg in jsonl_store.get_messages(session.id):
                self.save_message(session.id, msg)

            count += 1

        self._conn.commit()
        return count

    def close(self) -> None:
        """Close the connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
