"""Holographic fact store tools for CyberClaw agents."""

import json
import logging
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

from cyberclaw.tools.base import tool
from cyberclaw.core.holographic.store import HolographicStore
from cyberclaw.core.holographic.retrieval import FactRetriever

if TYPE_CHECKING:
    from cyberclaw.core.agent import AgentSession

logger = logging.getLogger(__name__)


def _get_holographic_components(session: "AgentSession") -> Tuple[HolographicStore, FactRetriever]:
    """Retrieve or lazily initialize holographic memory store and retriever on session context."""
    context = session.shared_context
    if not hasattr(context, "_holographic_store") or context._holographic_store is None:
        db_path = context.config.memories_path / "holographic_memory.db"
        store = HolographicStore(db_path)
        retriever = FactRetriever(store)
        context._holographic_store = store
        context._holographic_retriever = retriever
    return context._holographic_store, context._holographic_retriever


@tool(
    name="fact_store",
    description="Manage and search the agent's long-term facts, code heuristics, and entity relationships.",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "delete", "search", "probe", "related", "contradict"],
                "description": "The action to perform on the fact store."
            },
            "content": {
                "type": "string",
                "description": "The textual content of the fact to add, search, or check for contradiction."
            },
            "category": {
                "type": "string",
                "description": "Optional category bank name (e.g. 'general', 'git', 'django'). Default is 'general'.",
                "default": "general"
            },
            "tags": {
                "type": "string",
                "description": "Comma-separated list of tags associated with the fact."
            },
            "trust_score": {
                "type": "number",
                "description": "Reliability/trust of the fact between 0.0 and 1.0. Default is 0.5.",
                "default": 0.5
            },
            "entities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Manual list of entities (proper nouns, code symbols, key terms) in this fact. If omitted, regex extraction is used."
            },
            "entity": {
                "type": "string",
                "description": "The name of a specific entity to probe inside a category memory bank."
            },
            "fact_id": {
                "type": "integer",
                "description": "The target fact ID for deletion or finding related facts."
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of search results to return. Default is 5.",
                "default": 5
            },
            "threshold": {
                "type": "number",
                "description": "Minimum score threshold for retrieved facts. Default is 0.15.",
                "default": 0.15
            }
        },
        "required": ["action"]
    }
)
async def fact_store(
    action: str,
    session: "AgentSession",
    content: Optional[str] = None,
    category: str = "general",
    tags: Optional[str] = None,
    trust_score: float = 0.5,
    entities: Optional[List[str]] = None,
    entity: Optional[str] = None,
    fact_id: Optional[int] = None,
    limit: int = 5,
    threshold: float = 0.15
) -> str:
    """Perform queries, insertions, deletions, and phase unbinding on the holographic fact store."""
    try:
        store, retriever = _get_holographic_components(session)
        
        if action == "add":
            if not content:
                return "Error: 'content' parameter is required to add a fact."
            fact_id_res = store.add_fact(
                content=content,
                category=category,
                tags=tags or "",
                trust_score=trust_score,
                entities=entities
            )
            return json.dumps({
                "status": "success",
                "message": "Fact added successfully",
                "fact_id": fact_id_res,
                "category": category
            })
            
        elif action == "delete":
            if fact_id is None:
                return "Error: 'fact_id' parameter is required to delete a fact."
            success = store.delete_fact(fact_id)
            if success:
                return json.dumps({"status": "success", "message": f"Deleted fact {fact_id}"})
            else:
                return json.dumps({"status": "error", "message": f"Fact {fact_id} not found"})
                
        elif action == "search":
            if not content:
                return "Error: 'content' parameter is required for search query."
            results = retriever.search(content, category=category, limit=limit, threshold=threshold)
            return json.dumps({"results": results}, indent=2)
            
        elif action == "probe":
            if not entity:
                return "Error: 'entity' parameter is required for category probing."
            results = retriever.probe(entity, category=category, limit=limit)
            return json.dumps({"results": results}, indent=2)
            
        elif action == "related":
            if fact_id is None:
                return "Error: 'fact_id' parameter is required to find related facts."
            results = retriever.related(fact_id, limit=limit)
            return json.dumps({"results": results}, indent=2)
            
        elif action == "contradict":
            if not content:
                return "Error: 'content' parameter is required to test contradictions."
            results = retriever.contradict(content, limit=limit)
            return json.dumps({"results": results}, indent=2)
            
        else:
            return f"Error: Unknown action '{action}'"
            
    except Exception as e:
        logger.error(f"Error in fact_store tool: {e}", exc_info=True)
        return f"Error executing fact_store action: {e}"


@tool(
    name="fact_feedback",
    description="Mark retrieved facts as helpful/correct or unhelpful to dynamically adjust trust scores.",
    parameters={
        "type": "object",
        "properties": {
            "fact_id": {
                "type": "integer",
                "description": "The ID of the fact being rated."
            },
            "helpful": {
                "type": "boolean",
                "description": "Whether this fact was useful or correct for solving the current query."
            }
        },
        "required": ["fact_id", "helpful"]
    }
)
async def fact_feedback(
    fact_id: int,
    helpful: bool,
    session: "AgentSession"
) -> str:
    """Submit helpfulness feedback to adjust retrieval counts and helpfulness scores."""
    try:
        store, _ = _get_holographic_components(session)
        store.increment_counters(fact_id, helpful=helpful)
        
        # Optionally adjust trust score slightly
        conn = store._conn
        row = store.get_fact(fact_id)
        if row:
            current_trust = row["trust_score"]
            delta = 0.05 if helpful else -0.05
            new_trust = max(0.1, min(1.0, current_trust + delta))
            conn.execute("UPDATE facts SET trust_score = ? WHERE fact_id = ?", (new_trust, fact_id))
            conn.commit()
            
            return json.dumps({
                "status": "success",
                "message": f"Updated feedback for fact {fact_id}",
                "helpful": helpful,
                "new_trust_score": round(new_trust, 2)
            })
        else:
            return f"Error: Fact {fact_id} not found"
            
    except Exception as e:
        logger.error(f"Error in fact_feedback tool: {e}")
        return f"Error registering fact feedback: {e}"
