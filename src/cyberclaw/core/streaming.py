"""Streaming protocol for real-time token delivery."""

from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Any


class ChunkType(str, Enum):
    """Types of streaming chunks."""
    TOKEN = "token"           # Partial text token
    TOOL_START = "tool_start" # Tool call initiated
    TOOL_END = "tool_end"     # Tool call completed
    DONE = "done"             # Stream finished
    ERROR = "error"           # Stream error


@dataclass
class StreamChunk:
    """A single chunk in a streaming response."""
    type: ChunkType
    content: str = ""
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_args: str | None = None
    tool_result: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> str:
        """Convert to SSE data line."""
        import json
        data = {"type": self.type.value, "content": self.content}
        if self.tool_name:
            data["tool_name"] = self.tool_name
        if self.tool_call_id:
            data["tool_call_id"] = self.tool_call_id
        if self.tool_args:
            data["tool_args"] = self.tool_args
        if self.tool_result:
            data["tool_result"] = self.tool_result
        if self.error:
            data["error"] = self.error
        return f"data: {json.dumps(data)}\n\n"


async def collect_stream(stream: AsyncIterator[StreamChunk]) -> str:
    """Collect all tokens from a stream into a single string."""
    parts: list[str] = []
    async for chunk in stream:
        if chunk.type == ChunkType.TOKEN:
            parts.append(chunk.content)
        elif chunk.type == ChunkType.ERROR:
            raise RuntimeError(chunk.error or "Stream error")
    return "".join(parts)
