"""SQLite-backed fact and entity holographic memory store."""

import sqlite3
import threading
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, List, Dict, Optional, Tuple
import re

import numpy as np

from cyberclaw.core.holographic.holographic import (
    bundle,
    bytes_to_phases,
    phases_to_bytes,
    encode_fact
)

logger = logging.getLogger(__name__)


class HolographicStore:
    """SQLite-backed fact and entity holographic memory store.

    Manages DB lifecycle, triggers, entity extraction, and category bank rebuilding.
    """

    def __init__(self, db_path: Path, dim: int = 1024):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.dim = dim
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
        """Create tables and triggers if they do not exist."""
        conn = self._conn
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS facts (
                fact_id         INTEGER PRIMARY KEY AUTOINCREMENT,
                content         TEXT NOT NULL UNIQUE,
                category        TEXT DEFAULT 'general',
                tags            TEXT DEFAULT '',
                trust_score     REAL DEFAULT 0.5,
                retrieval_count INTEGER DEFAULT 0,
                helpful_count   INTEGER DEFAULT 0,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                hrr_vector      BLOB
            );

            CREATE TABLE IF NOT EXISTS entities (
                entity_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                entity_type TEXT DEFAULT 'unknown',
                aliases     TEXT DEFAULT '',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS fact_entities (
                fact_id   INTEGER REFERENCES facts(fact_id) ON DELETE CASCADE,
                entity_id INTEGER REFERENCES entities(entity_id) ON DELETE CASCADE,
                PRIMARY KEY (fact_id, entity_id)
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts
                USING fts5(content, tags, content=facts, content_rowid=fact_id);

            CREATE TABLE IF NOT EXISTS memory_banks (
                bank_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                bank_name  TEXT NOT NULL UNIQUE,
                vector     BLOB NOT NULL,
                dim        INTEGER NOT NULL,
                fact_count INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Add FTS triggers
        conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
                INSERT INTO facts_fts(rowid, content, tags) VALUES (new.fact_id, new.content, new.tags);
            END;
            CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
                INSERT INTO facts_fts(facts_fts, rowid, content, tags) VALUES ('delete', old.fact_id, old.content, old.tags);
            END;
            CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
                INSERT INTO facts_fts(facts_fts, rowid, content, tags) VALUES ('delete', old.fact_id, old.content, old.tags);
                INSERT INTO facts_fts(rowid, content, tags) VALUES (new.fact_id, new.content, new.tags);
            END;
        """)
        conn.commit()

    def extract_entities(self, text: str) -> List[str]:
        """Simple regex-based entity extraction fallback.

        Extracts capitalized terms, code identifiers, proper nouns.
        """
        # Match words with upper case letters, code variables, words with underscores
        candidates = re.findall(r"\b[A-Za-z_][a-zA-Z0-9_]*\b", text)
        entities = []
        for c in candidates:
            # Exclude standard common English stopwords
            if len(c) > 2 and c.lower() not in {
                "the", "and", "for", "you", "that", "this", "with", "from",
                "was", "were", "are", "but", "not", "she", "they", "them"
            }:
                # Ensure it's either capitalized or contains an underscore/camelCase (indicating an entity or code identifier)
                is_entity = (
                    c[0].isupper() or
                    "_" in c or
                    (any(x.isupper() for x in c[1:]) and any(x.islower() for x in c))
                )
                if is_entity and c not in entities:
                    entities.append(c)
        return entities

    def add_fact(
        self,
        content: str,
        category: str = "general",
        tags: str = "",
        trust_score: float = 0.5,
        entities: Optional[List[str]] = None,
    ) -> int:
        """Insert or update a fact, resolve its entities, generate VSA phase vector, and rebuild category bank."""
        content_stripped = content.strip()
        if not content_stripped:
            raise ValueError("Fact content cannot be empty")

        if entities is None:
            entities = self.extract_entities(content_stripped)

        cleaned_entities = list(set([e.strip() for e in entities if e.strip()]))

        # Generate HRR vector for fact
        fact_vector = encode_fact(content_stripped, cleaned_entities, self.dim)
        vector_bytes = phases_to_bytes(fact_vector)

        conn = self._conn
        cursor = conn.cursor()
        try:
            now = datetime.utcnow().isoformat()
            cursor.execute(
                """
                INSERT INTO facts (content, category, tags, trust_score, hrr_vector, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(content) DO UPDATE SET
                    category=excluded.category,
                    tags=excluded.tags,
                    trust_score=excluded.trust_score,
                    hrr_vector=excluded.hrr_vector,
                    updated_at=excluded.updated_at
                """,
                (content_stripped, category, tags, trust_score, vector_bytes, now)
            )
            fact_id = cursor.lastrowid

            if not fact_id or fact_id == 0:
                row = cursor.execute("SELECT fact_id FROM facts WHERE content = ?", (content_stripped,)).fetchone()
                fact_id = row["fact_id"]
                # Clean up existing entity associations
                cursor.execute("DELETE FROM fact_entities WHERE fact_id = ?", (fact_id,))

            for ent_name in cleaned_entities:
                cursor.execute(
                    """
                    INSERT INTO entities (name, entity_type)
                    VALUES (?, 'extracted')
                    ON CONFLICT(name) DO UPDATE SET name=name
                    """,
                    (ent_name,)
                )
                ent_row = cursor.execute("SELECT entity_id FROM entities WHERE name = ?", (ent_name,)).fetchone()
                ent_id = ent_row["entity_id"]

                cursor.execute(
                    """
                    INSERT OR IGNORE INTO fact_entities (fact_id, entity_id)
                    VALUES (?, ?)
                    """,
                    (fact_id, ent_id)
                )

            conn.commit()

            # Rebuild category memory bank
            self.rebuild_category_bank(category)
            return fact_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to add fact to store: {e}")
            raise

    def delete_fact(self, fact_id: int) -> bool:
        """Delete a fact by ID and rebuild its category memory bank."""
        conn = self._conn
        cursor = conn.cursor()
        row = cursor.execute("SELECT category FROM facts WHERE fact_id = ?", (fact_id,)).fetchone()
        if not row:
            return False
        category = row["category"]

        try:
            cursor.execute("DELETE FROM facts WHERE fact_id = ?", (fact_id,))
            conn.commit()
            self.rebuild_category_bank(category)
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete fact: {e}")
            raise

    def rebuild_category_bank(self, category: str) -> None:
        """Select all facts in the category, bundle vectors, and update memory_banks table."""
        conn = self._conn
        cursor = conn.cursor()

        rows = cursor.execute("SELECT hrr_vector FROM facts WHERE category = ?", (category,)).fetchall()
        if not rows:
            cursor.execute("DELETE FROM memory_banks WHERE bank_name = ?", (category,))
            conn.commit()
            return

        vectors = [bytes_to_phases(row["hrr_vector"]) for row in rows]
        bundled_vector = bundle(*vectors)
        vector_bytes = phases_to_bytes(bundled_vector)

        cursor.execute(
            """
            INSERT INTO memory_banks (bank_name, vector, dim, fact_count, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(bank_name) DO UPDATE SET
                vector=excluded.vector,
                dim=excluded.dim,
                fact_count=excluded.fact_count,
                updated_at=excluded.updated_at
            """,
            (category, vector_bytes, self.dim, len(vectors), datetime.utcnow().isoformat())
        )
        conn.commit()

    def get_category_bank(self, category: str) -> Optional[np.ndarray]:
        """Retrieve the bundled phase vector for a category bank."""
        row = self._conn.execute(
            "SELECT vector FROM memory_banks WHERE bank_name = ?", (category,)
        ).fetchone()
        if not row:
            return None
        return bytes_to_phases(row["vector"])

    def get_fact(self, fact_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a specific fact by ID."""
        row = self._conn.execute("SELECT * FROM facts WHERE fact_id = ?", (fact_id,)).fetchone()
        if not row:
            return None
        return dict(row)

    def increment_counters(self, fact_id: int, helpful: bool = False) -> None:
        """Increment retrieval and helpful counters for a fact."""
        conn = self._conn
        if helpful:
            conn.execute(
                "UPDATE facts SET retrieval_count = retrieval_count + 1, helpful_count = helpful_count + 1 WHERE fact_id = ?",
                (fact_id,)
            )
        else:
            conn.execute("UPDATE facts SET retrieval_count = retrieval_count + 1 WHERE fact_id = ?", (fact_id,))
        conn.commit()

    def get_entities(self) -> List[Dict[str, Any]]:
        """Retrieve all resolved entities."""
        rows = self._conn.execute("SELECT * FROM entities").fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        """Close connections."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
