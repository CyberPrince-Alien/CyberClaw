"""File system tools for safe workspace operations."""

import os
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _validate_path(workspace: Path, target: str) -> Path:
    """Ensure the path stays within the workspace."""
    resolved = (workspace / target).resolve()
    if not str(resolved).startswith(str(workspace.resolve())):
        raise ValueError(f"Path escapes workspace: {target}")
    return resolved


async def read_file_handler(path: str, workspace: str = ".", **kwargs: Any) -> str:
    """Read a file's content."""
    ws = Path(workspace).resolve()
    target = _validate_path(ws, path)
    if not target.exists():
        return f"Error: File not found: {path}"
    if not target.is_file():
        return f"Error: Not a file: {path}"
    content = target.read_text(encoding="utf-8", errors="replace")
    if len(content) > 50000:
        content = content[:50000] + "\n...[truncated]"
    return content


async def write_file_handler(path: str, content: str, workspace: str = ".", **kwargs: Any) -> str:
    """Write content to a file."""
    ws = Path(workspace).resolve()
    target = _validate_path(ws, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {path}"


async def list_dir_handler(path: str = ".", workspace: str = ".", **kwargs: Any) -> str:
    """List directory contents."""
    ws = Path(workspace).resolve()
    target = _validate_path(ws, path)
    if not target.exists():
        return f"Error: Directory not found: {path}"
    if not target.is_dir():
        return f"Error: Not a directory: {path}"

    entries = []
    for entry in sorted(target.iterdir()):
        if entry.name.startswith("."):
            continue
        kind = "dir" if entry.is_dir() else "file"
        size = entry.stat().st_size if entry.is_file() else ""
        entries.append(f"  {kind:4s}  {size:>8}  {entry.name}")

    return f"Contents of {path}:\n" + "\n".join(entries) if entries else f"{path} is empty"


async def search_files_handler(
    query: str, path: str = ".", workspace: str = ".", **kwargs: Any,
) -> str:
    """Search for files containing a text pattern."""
    ws = Path(workspace).resolve()
    target = _validate_path(ws, path)
    if not target.exists():
        return f"Error: Path not found: {path}"

    matches = []
    files_searched = 0

    for root, dirs, files in os.walk(target):
        # Skip hidden dirs
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            if fname.startswith("."):
                continue
            fpath = Path(root) / fname
            files_searched += 1
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(content.split("\n"), 1):
                    if query.lower() in line.lower():
                        rel = fpath.relative_to(target)
                        matches.append(f"  {rel}:{i}: {line.strip()[:120]}")
                        if len(matches) >= 50:
                            break
            except (UnicodeDecodeError, PermissionError):
                continue
            if len(matches) >= 50:
                break
        if len(matches) >= 50:
            break

    header = f"Searched {files_searched} files in {path} for '{query}':\n"
    if matches:
        return header + "\n".join(matches)
    return header + "No matches found."


FILE_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file in the workspace. Creates parent directories if needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories in a workspace path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path", "default": "."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for text patterns across files in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Text to search for"},
                    "path": {"type": "string", "description": "Directory to search in", "default": "."},
                },
                "required": ["query"],
            },
        },
    },
]
