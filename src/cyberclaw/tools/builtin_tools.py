"""Built-in tools for agent capabilities."""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from cyberclaw.tools.base import tool

if TYPE_CHECKING:
    from cyberclaw.core.agent import AgentSession


# Filesystem tools


@tool(
    name="read",
    description="Read the contents of a text file, optionally specifying offset and limit",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read"},
            "offset": {
                "type": "integer",
                "description": "The 1-indexed line number to start reading from (default is 1)",
                "default": 1,
            },
            "limit": {
                "type": "integer",
                "description": "The maximum number of lines to read (optional)",
            },
        },
        "required": ["path"],
    },
)
async def read_file(
    path: str,
    session: "AgentSession",
    offset: int = 1,
    limit: int | None = None,
) -> str:
    """Read and return the contents of a file at the given path, optionally with offset and limit."""
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines(keepends=True)
        
        start = max(0, offset - 1)
        if limit is not None:
            end = start + max(0, limit)
            selected_lines = lines[start:end]
        else:
            selected_lines = lines[start:]
            
        return "".join(selected_lines)
    except FileNotFoundError:
        return f"Error: File not found: {path}"
    except PermissionError:
        return f"Error: Permission denied reading: {path}"
    except IsADirectoryError:
        return f"Error: Path is a directory, not a file: {path}"
    except Exception as e:
        return f"Error reading file: {e}"


@tool(
    name="write",
    description="Write content to a file",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to write"},
            "content": {
                "type": "string",
                "description": "Content to write to the file",
            },
        },
        "required": ["path", "content"],
    },
)
async def write_file(path: str, content: str, session: "AgentSession") -> str:
    """Write content to a file at the given path."""
    try:
        Path(path).write_text(content)
        return f"Successfully wrote to: {path}"
    except PermissionError:
        return f"Error: Permission denied writing to: {path}"
    except IsADirectoryError:
        return f"Error: Path is a directory, not a file: {path}"
    except Exception as e:
        return f"Error writing file: {e}"


@tool(
    name="edit",
    description="Edit a file by replacing a string with new content",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to edit"},
            "old_text": {"type": "string", "description": "The text to replace"},
            "new_text": {
                "type": "string",
                "description": "The new text to replace with",
            },
        },
        "required": ["path", "old_text", "new_text"],
    },
)
async def edit_file(
    path: str, old_text: str, new_text: str, session: "AgentSession"
) -> str:
    """Edit a file by replacing old_text with new_text."""
    try:
        content = Path(path).read_text()
        if old_text not in content:
            return f"Error: '{old_text}' not found in {path}"
        new_content = content.replace(old_text, new_text)
        Path(path).write_text(new_content)
        return f"Successfully edited {path}"
    except FileNotFoundError:
        return f"Error: File not found: {path}"
    except PermissionError:
        return f"Error: Permission denied editing: {path}"
    except Exception as e:
        return f"Error editing file: {e}"


# Shell tool


@tool(
    name="bash",
    description="Execute a bash shell command",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The bash command to execute"},
        },
        "required": ["command"],
    },
)
async def bash(command: str, session: "AgentSession") -> str:
    """Execute a bash command and return the output."""
    import sys
    import re
    
    if sys.platform.startswith("win"):
        # Translate unix style /dev/null redirection to Windows nul redirection
        command = command.replace(">/dev/null", ">nul")
        command = command.replace("2>/dev/null", "2>nul")
        
        # Map Unix open/xdg-open to Windows start
        command = re.sub(r"(^|[\s;&|])open\b", r"\1start", command)
        command = re.sub(r"(^|[\s;&|])xdg-open\b", r"\1start", command)
        
        # Map google-chrome to start chrome
        command = re.sub(r"(^|[\s;&|])google-chrome\b", r"\1start chrome", command)
        
        # Avoid cmd.exe start window title quirk:
        # If start is followed by a quoted argument, insert "" as the first parameter.
        command = re.sub(r"\bstart\s+(\"[^\"]+\")", r'start "" \1', command)

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        output = stdout.decode() if stdout else ""
        error = stderr.decode() if stderr else ""
        if output and error:
            return f"{output}\n{error}"
        return output or error or "Command completed with no output"
    except Exception as e:
        return f"Error executing command: {e}"


@tool(
    name="sleep",
    description="Pause execution for a given number of seconds",
    parameters={
        "type": "object",
        "properties": {
            "seconds": {
                "type": "number",
                "description": "Number of seconds to sleep",
            }
        },
        "required": ["seconds"],
    },
)
async def sleep_tool(seconds: float, session: "AgentSession") -> str:
    """Pause execution for a given number of seconds."""
    try:
        await asyncio.sleep(seconds)
        return f"Successfully slept for {seconds} seconds"
    except Exception as e:
        return f"Error sleeping: {e}"


@tool(
    name="todowrite",
    description="Write tasks or todo items to a file in the workspace",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the todo/task file to write or update",
            },
            "content": {
                "type": "string",
                "description": "Content or task lists to write to the todo file",
            },
        },
        "required": ["path", "content"],
    },
)
async def todo_write(path: str, content: str, session: "AgentSession") -> str:
    """Write todo list/tasks to a file relative to the workspace."""
    try:
        workspace = Path(session.shared_context.config.workspace).resolve()
        target = (workspace / path).resolve()
        
        if not str(target).startswith(str(workspace)):
            return f"Error: Path '{path}' escapes workspace"
            
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Successfully wrote todo tasks to {path}"
    except Exception as e:
        return f"Error writing todo: {e}"


@tool(
    name="repl",
    description="Run Python code in a persistent interactive interpreter environment across chat turns",
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute",
            }
        },
        "required": ["code"],
    },
)
async def repl(code: str, session: "AgentSession") -> str:
    """Execute Python code in a persistent environment for the active session."""
    import sys
    import io
    import traceback

    if not hasattr(session, "_repl_locals"):
        session._repl_locals = {
            "__builtins__": __builtins__,
            "session": session,
        }

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    
    try:
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture
        
        try:
            compiled_code = compile(code.strip(), "<repl>", "eval")
            result = eval(compiled_code, session._repl_locals)
            if result is not None:
                print(repr(result))
        except Exception:
            compiled_code = compile(code, "<repl>", "exec")
            exec(compiled_code, session._repl_locals)
            
        stdout_val = stdout_capture.getvalue()
        stderr_val = stderr_capture.getvalue()
        
        output = stdout_val
        if stderr_val:
            if output:
                output += "\n"
            output += f"Stderr:\n{stderr_val}"
            
        return output or "Code executed successfully with no output"
    except Exception:
        return traceback.format_exc()
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


@tool(
    name="powershell",
    description="Execute a PowerShell command on the Windows shell",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The PowerShell command to execute",
            }
        },
        "required": ["command"],
    },
)
async def powershell(command: str, session: "AgentSession") -> str:
    """Execute a PowerShell command and return output."""
    try:
        process = await asyncio.create_subprocess_exec(
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        output = stdout.decode(errors="replace") if stdout else ""
        error = stderr.decode(errors="replace") if stderr else ""
        if output and error:
            return f"{output}\n{error}"
        return output or error or "Command completed with no output"
    except Exception as e:
        return f"Error executing PowerShell command: {e}"

