"""Commitments -- AI promises/follow-ups with persistent tracking."""

import json, logging, time, re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

@dataclass
class Commitment:
    id: str; session_id: str; content: str; due_description: str = ""
    created_at: float = field(default_factory=time.time)
    checked_at: float = 0.0; fulfilled: bool = False; fulfilled_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "session_id": self.session_id, "content": self.content,
                "due": self.due_description, "created_at": self.created_at,
                "fulfilled": self.fulfilled, "age_hours": (time.time() - self.created_at) / 3600}

class CommitmentStore:
    """JSON-file backed commitment persistence."""
    def __init__(self, store_path: Path):
        self.path = store_path; store_path.parent.mkdir(parents=True, exist_ok=True)
        self._commitments: list[Commitment] = []; self._load()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self._commitments = [Commitment(**c) for c in data]
            except Exception: self._commitments = []

    def _save(self):
        self.path.write_text(json.dumps([
            {"id": c.id, "session_id": c.session_id, "content": c.content,
             "due_description": c.due_description, "created_at": c.created_at,
             "checked_at": c.checked_at, "fulfilled": c.fulfilled,
             "fulfilled_at": c.fulfilled_at}
            for c in self._commitments
        ], indent=2))

    def add(self, session_id: str, content: str, due: str = "") -> Commitment:
        c = Commitment(id=f"cmt-{int(time.time())}", session_id=session_id,
                       content=content, due_description=due)
        self._commitments.append(c); self._save(); return c

    def fulfill(self, commitment_id: str) -> bool:
        for c in self._commitments:
            if c.id == commitment_id:
                c.fulfilled = True; c.fulfilled_at = time.time()
                self._save(); return True
        return False

    def list_pending(self) -> list[Commitment]:
        return [c for c in self._commitments if not c.fulfilled]

    def list_all(self) -> list[Commitment]:
        return list(self._commitments)

    def check_overdue(self, max_age_hours: float = 24) -> list[Commitment]:
        cutoff = time.time() - max_age_hours * 3600
        return [c for c in self._commitments if not c.fulfilled and c.created_at < cutoff]

def extract_commitments(text: str) -> list[str]:
    """Extract commitment-like phrases from AI response."""
    patterns = [
        r"I(?:'ll| will) (?:follow up|check|remind|get back|look into|investigate)(.*?)(?:\.|$)",
        r"(?:Let me|I'll) (?:schedule|set up|prepare|create)(.*?)(?:\.|$)",
        r"I(?:'ll| will) (?:send|share|provide|update)(.*?)(?:later|tomorrow|soon|by)(?:.*?)(?:\.|$)",
    ]
    found = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            cleaned = m.strip().rstrip(".")
            if len(cleaned) > 5: found.append(cleaned)
    return found
