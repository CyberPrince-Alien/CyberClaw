"""Trajectory -- conversation export/replay as shareable artifacts."""

import json, time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from cyberclaw.core.history import HistoryStore, HistoryMessage, HistorySession

@dataclass
class TrajectoryExport:
    session_id: str; agent_id: str; title: str
    messages: list[dict[str, Any]]; exported_at: float
    metadata: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps({"session_id": self.session_id, "agent_id": self.agent_id,
            "title": self.title, "messages": self.messages, "exported_at": self.exported_at,
            "metadata": self.metadata, "format_version": "1.0"}, indent=2, ensure_ascii=False)

    def to_markdown(self) -> str:
        lines = [f"# Conversation: {self.title or self.session_id}", f"Agent: {self.agent_id}", ""]
        for m in self.messages:
            role = m.get("role", "unknown").upper()
            content = m.get("content", "")
            ts = m.get("timestamp", "")
            lines.append(f"## {role} ({ts})")
            lines.append(content); lines.append("")
        return "\n".join(lines)

class TrajectoryManager:
    """Export and import conversation trajectories."""
    def __init__(self, history_store: HistoryStore, export_dir: Path):
        self.history = history_store
        self.export_dir = export_dir; export_dir.mkdir(parents=True, exist_ok=True)

    def export_session(self, session_id: str, format: str = "json") -> Path | None:
        session = self.history.get_session_info(session_id)
        if not session: return None
        messages = self.history.get_messages(session_id)
        export = TrajectoryExport(
            session_id=session_id, agent_id=session.agent_id,
            title=session.title or "", exported_at=time.time(),
            messages=[{"role": m.role, "content": m.content, "timestamp": m.timestamp,
                       "tool_calls": m.tool_calls, "tool_call_id": m.tool_call_id}
                      for m in messages],
            metadata={"message_count": len(messages), "source": session.source})
        ext = "md" if format == "markdown" else "json"
        filename = f"trajectory-{session_id}.{ext}"
        path = self.export_dir / filename
        content = export.to_markdown() if format == "markdown" else export.to_json()
        path.write_text(content, encoding="utf-8")
        return path

    def import_trajectory(self, path: Path) -> str | None:
        """Import a trajectory JSON file and create a new session."""
        try:
            data = json.loads(path.read_text())
            from cyberclaw.core.events import CliEventSource
            source = CliEventSource()
            sid = f"imported-{int(time.time())}"
            self.history.create_session(data.get("agent_id", "cyberclaw"), sid, source)
            for m in data.get("messages", []):
                self.history.save_message(sid, HistoryMessage(
                    role=m["role"], content=m.get("content", ""),
                    timestamp=m.get("timestamp", "")))
            return sid
        except Exception: return None

    def list_exports(self) -> list[str]:
        return [f.name for f in self.export_dir.glob("trajectory-*")]
