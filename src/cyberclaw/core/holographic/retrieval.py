"""Hybrid retrieval engine for holographic memory facts and entities."""

import re
import math
import logging
from datetime import datetime
from typing import Any, List, Dict, Optional, Tuple

import numpy as np

from cyberclaw.core.holographic.holographic import (
    encode_text,
    encode_atom,
    bind,
    unbind,
    similarity,
    bytes_to_phases
)
from cyberclaw.core.holographic.store import HolographicStore

logger = logging.getLogger(__name__)


class FactRetriever:
    """Retrieves and reasons over facts in the HolographicStore using hybrid search."""

    def __init__(
        self,
        store: HolographicStore,
        w_fts: float = 0.3,
        w_jaccard: float = 0.3,
        w_hrr: float = 0.4,
        decay_rate: float = 0.005
    ):
        self.store = store
        self.w_fts = w_fts
        self.w_jaccard = w_jaccard
        self.w_hrr = w_hrr
        self.decay_rate = decay_rate
        self.dim = store.dim

    def _tokenize(self, text: str) -> List[str]:
        """Normalize and tokenize text for Jaccard similarity."""
        words = re.findall(r"\b\w+\b", text.lower())
        return [w for w in words if len(w) > 1]

    def _compute_jaccard(self, query: str, content: str) -> float:
        """Compute token-level Jaccard similarity."""
        q_tokens = set(self._tokenize(query))
        c_tokens = set(self._tokenize(content))
        if not q_tokens or not c_tokens:
            return 0.0
        return len(q_tokens & c_tokens) / len(q_tokens | c_tokens)

    def _compute_fts_score(self, rank: Optional[float]) -> float:
        """Normalize FTS5 BM25 rank (where lower/negative is better) to [0, 1]."""
        if rank is None:
            return 0.0
        # BM25 rank is usually negative for matches. Lower rank = better.
        # Shift using sigmoid on negative rank
        return 1.0 / (1.0 + math.exp(rank))

    def _compute_temporal_decay(self, updated_at_str: str) -> float:
        """Compute exponential temporal decay factor."""
        try:
            # SQLite timestamps can have different formats. Try common ones:
            for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    updated_at = datetime.strptime(updated_at_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                return 1.0
            
            age_seconds = (datetime.utcnow() - updated_at).total_seconds()
            age_days = max(0.0, age_seconds / 86400.0)
            return math.exp(-self.decay_rate * age_days)
        except Exception as e:
            logger.debug(f"Failed to compute temporal decay: {e}")
            return 1.0

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 5,
        threshold: float = 0.15
    ) -> List[Dict[str, Any]]:
        """Perform hybrid search incorporating FTS5, Jaccard, VSA cosine similarity, and trust scores."""
        query_stripped = query.strip()
        if not query_stripped:
            return []

        # 1. Lexical Filtering (FTS5 with LIKE fallback)
        conn = self.store._conn
        cursor = conn.cursor()

        # Clean query for FTS5 (escape special MATCH chars)
        clean_q = re.sub(r'[^\w\s]', ' ', query_stripped).strip()
        
        candidates: List[Tuple[Dict[str, Any], Optional[float]]] = []
        seen_ids = set()

        if clean_q:
            # Format query for prefix matching on each term
            fts_query = " AND ".join([f"{term}*" for term in clean_q.split()])
            try:
                sql = """
                    SELECT f.*, fts.rank
                    FROM facts f
                    JOIN facts_fts fts ON f.fact_id = fts.rowid
                    WHERE facts_fts MATCH ?
                """
                params = [fts_query]
                if category:
                    sql += " AND f.category = ?"
                    params.append(category)
                sql += f" ORDER BY rank LIMIT {limit * 3}"

                rows = cursor.execute(sql, params).fetchall()
                for r in rows:
                    fact_dict = dict(r)
                    candidates.append((fact_dict, fact_dict.pop("rank", None)))
                    seen_ids.add(fact_dict["fact_id"])
            except sqlite3.OperationalError:
                # If MATCH syntax fails, fallback
                pass

        # Fallback / expansion: if candidates are few, query using LIKE
        if len(candidates) < limit:
            like_sql = "SELECT * FROM facts WHERE 1=1"
            like_params = []
            if category:
                like_sql += " AND category = ?"
                like_params.append(category)
            
            # Simple content match or just general list
            like_sql += " AND content LIKE ?"
            like_params.append(f"%{query_stripped}%")
            like_sql += f" LIMIT {limit * 3}"

            rows = cursor.execute(like_sql, like_params).fetchall()
            for r in rows:
                f_id = r["fact_id"]
                if f_id not in seen_ids:
                    candidates.append((dict(r), None))
                    seen_ids.add(f_id)

        # If still empty, grab last N facts from category/global
        if not candidates:
            backup_sql = "SELECT * FROM facts WHERE 1=1"
            backup_params = []
            if category:
                backup_sql += " AND category = ?"
                backup_params.append(category)
            backup_sql += f" ORDER BY updated_at DESC LIMIT {limit * 3}"
            rows = cursor.execute(backup_sql, backup_params).fetchall()
            for r in rows:
                candidates.append((dict(r), None))

        # 2. VSA phase encoding for the query
        query_vector = encode_text(query_stripped, self.dim)

        results = []
        for fact, rank in candidates:
            # Jaccard
            jaccard = self._compute_jaccard(query_stripped, fact["content"])
            
            # FTS BM25
            fts_score = self._compute_fts_score(rank)
            
            # VSA similarity
            fact_vector = bytes_to_phases(fact["hrr_vector"])
            vsa_sim = similarity(query_vector, fact_vector)
            vsa_score = (vsa_sim + 1.0) / 2.0  # Shift to [0, 1]

            # Trust and decay
            trust = fact.get("trust_score", 0.5)
            decay = self._compute_temporal_decay(fact["updated_at"])

            # Hybrid Score calculation
            raw_score = (self.w_fts * fts_score) + (self.w_jaccard * jaccard) + (self.w_hrr * vsa_score)
            final_score = raw_score * trust * decay

            if final_score >= threshold:
                results.append({
                    "fact_id": fact["fact_id"],
                    "content": fact["content"],
                    "category": fact["category"],
                    "tags": fact["tags"],
                    "trust_score": trust,
                    "fts_score": fts_score,
                    "jaccard_score": jaccard,
                    "hrr_similarity": vsa_sim,
                    "final_score": final_score,
                    "updated_at": fact["updated_at"]
                })

        # Sort by final score descending
        results.sort(key=lambda x: x["final_score"], reverse=True)
        return results[:limit]

    def probe(self, entity_name: str, category: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Perform vector-space unbinding on a category memory bank to retrieve associated facts.

        Formula:
          probe_vector = unbind(M_bank, bind(E_atom, ROLE_ENTITY))
          similarity(probe_vector, bind(encode_text(fact_content), ROLE_CONTENT))
        """
        bank_vector = self.store.get_category_bank(category)
        if bank_vector is None:
            return []

        # Atom and key representations
        role_entity = encode_atom("__hrr_role_entity__", self.dim)
        role_content = encode_atom("__hrr_role_content__", self.dim)
        entity_atom = encode_atom(entity_name.lower(), self.dim)
        
        # Unbind the entity key from the category bank
        bind_key = bind(entity_atom, role_entity)
        probe_vector = unbind(bank_vector, bind_key)

        # Retrieve all facts in this category to score them
        conn = self.store._conn
        rows = conn.execute("SELECT * FROM facts WHERE category = ?", (category,)).fetchall()
        
        scored_facts = []
        for r in rows:
            fact = dict(r)
            # Create content representation
            fact_content_vector = encode_text(fact["content"], self.dim)
            fact_content_bound = bind(fact_content_vector, role_content)
            
            # Compute cosine similarity between probe and bound content
            sim = similarity(probe_vector, fact_content_bound)
            scored_facts.append((fact, sim))

        # Sort by similarity descending
        scored_facts.sort(key=lambda x: x[1], reverse=True)
        
        results = []
        for fact, sim in scored_facts[:limit]:
            results.append({
                "fact_id": fact["fact_id"],
                "content": fact["content"],
                "category": fact["category"],
                "tags": fact["tags"],
                "probe_similarity": sim,
                "trust_score": fact["trust_score"]
            })
            
        return results

    def related(self, fact_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """Find facts related to a given fact by VSA phase vector similarity."""
        target_fact = self.store.get_fact(fact_id)
        if not target_fact:
            return []

        target_vector = bytes_to_phases(target_fact["hrr_vector"])
        
        conn = self.store._conn
        rows = conn.execute("SELECT * FROM facts WHERE fact_id != ?", (fact_id,)).fetchall()
        
        scored = []
        for r in rows:
            fact = dict(r)
            vector = bytes_to_phases(fact["hrr_vector"])
            sim = similarity(target_vector, vector)
            scored.append((fact, sim))
            
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return [
            {
                "fact_id": f["fact_id"],
                "content": f["content"],
                "category": f["category"],
                "tags": f["tags"],
                "similarity": sim
            }
            for f, sim in scored[:limit]
        ]

    def contradict(self, statement: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Identify stored facts that potentially contradict a statement.

        Looks for facts with high lexical overlap but low/negative VSA phase similarity.
        """
        statement_stripped = statement.strip()
        if not statement_stripped:
            return []

        # VSA phase vector for the statement
        statement_vector = encode_text(statement_stripped, self.dim)
        
        conn = self.store._conn
        rows = conn.execute("SELECT * FROM facts").fetchall()
        
        scored = []
        for r in rows:
            fact = dict(r)
            # Lexical overlap
            jaccard = self._compute_jaccard(statement_stripped, fact["content"])
            
            # If there is lexical overlap, let's look at the phase similarity
            if jaccard >= 0.2:
                fact_vector = bytes_to_phases(fact["hrr_vector"])
                vsa_sim = similarity(statement_vector, fact_vector)
                
                # Potential contradiction index: high lexical overlap but low/opposite vector direction
                # (1.0 - VSA similarity) weighted by Jaccard overlap
                contradiction_score = jaccard * (1.0 - vsa_sim)
                scored.append((fact, contradiction_score, vsa_sim, jaccard))
                
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return [
            {
                "fact_id": f["fact_id"],
                "content": f["content"],
                "category": f["category"],
                "tags": f["tags"],
                "contradiction_score": score,
                "similarity": sim,
                "jaccard_overlap": jac
            }
            for f, score, sim, jac in scored[:limit]
        ]
