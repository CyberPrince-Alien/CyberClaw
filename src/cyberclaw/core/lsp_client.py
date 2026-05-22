"""Asynchronous Python LSP Client utilizing jsonrpc communication over subprocess stdin/stdout."""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class LSPClient:
    """Asynchronous Language Server Protocol (LSP) client.
    
    Spawns language server executables and handles JSON-RPC standard messaging.
    """

    def __init__(self, command: str, args: List[str], root_path: Path, language: str):
        self.command = command
        self.args = args
        self.root_path = Path(root_path)
        self.root_uri = self.root_path.as_uri()
        self.language = language
        
        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._read_task: Optional[asyncio.Task] = None
        self._initialized = False
        
        # Maps document URI to list of active diagnostics
        self.diagnostics: Dict[str, List[Dict[str, Any]]] = {}
        self._document_versions: Dict[str, int] = {}

    async def start(self) -> bool:
        """Start the LSP server process and initialize it."""
        try:
            logger.info(f"Starting LSP server for {self.language}: {self.command} {' '.join(self.args)}")
            self._process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=str(self.root_path)
            )
            
            # Start reader task
            self._read_task = asyncio.create_task(self._read_loop())
            
            # Send initialize request
            initialize_result = await self.send_request("initialize", {
                "processId": None,
                "rootUri": self.root_uri,
                "capabilities": {
                    "textDocument": {
                        "synchronization": {
                            "dynamicRegistration": False,
                            "willSave": False,
                            "willSaveWaitUntil": False,
                            "didSave": True
                        },
                        "completion": {
                            "dynamicRegistration": False,
                            "completionItem": {
                                "snippetSupport": True
                            }
                        },
                        "hover": {
                            "dynamicRegistration": False
                        },
                        "definition": {
                            "dynamicRegistration": False
                        }
                    }
                },
                "workspaceFolders": [{"uri": self.root_uri, "name": self.root_path.name}]
            })
            
            # Send initialized notification
            self.send_notification("initialized", {})
            self._initialized = True
            logger.info(f"LSP server for {self.language} initialized successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to start LSP server '{self.command}': {e}")
            await self.stop()
            return False

    async def _read_loop(self) -> None:
        """Asynchronously read JSON-RPC headers and content from LSP server output stream."""
        buffer = b""
        try:
            while self._process and self._process.stdout:
                chunk = await self._process.stdout.read(4096)
                if not chunk:
                    break
                buffer += chunk
                
                while b"Content-Length: " in buffer:
                    try:
                        idx = buffer.index(b"Content-Length: ")
                        end_idx = buffer.index(b"\r\n\r\n", idx)
                    except ValueError:
                        # Wait for more bytes to complete the header
                        break
                    
                    header_block = buffer[idx:end_idx].decode("ascii", errors="ignore")
                    match = re.search(r"Content-Length:\s*(\d+)", header_block)
                    if not match:
                        # Malformed header, discard bytes before end_idx to recover
                        buffer = buffer[end_idx + 4:]
                        continue
                        
                    content_length = int(match.group(1))
                    msg_start = end_idx + 4
                    msg_end = msg_start + content_length
                    
                    if len(buffer) < msg_end:
                        # Wait for full payload message content
                        break
                        
                    msg_bytes = buffer[msg_start:msg_end]
                    buffer = buffer[msg_end:]
                    
                    try:
                        message = json.loads(msg_bytes.decode("utf-8"))
                        self._handle_message(message)
                    except Exception as e:
                        logger.error(f"Error parsing JSON payload from LSP: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"LSP read loop exception: {e}")

    def _handle_message(self, msg: Dict[str, Any]) -> None:
        """Handle incoming message matching Request/Response/Notification schema."""
        # 1. Handle Response
        if "id" in msg:
            req_id = msg["id"]
            if req_id in self._pending_requests:
                fut = self._pending_requests.pop(req_id)
                if "error" in msg:
                    fut.set_exception(RuntimeError(msg["error"].get("message", "LSP internal error")))
                else:
                    fut.set_result(msg.get("result"))
        # 2. Handle Notifications
        elif "method" in msg:
            method = msg["method"]
            params = msg.get("params", {})
            if method == "textDocument/publishDiagnostics":
                uri = params.get("uri")
                diags = params.get("diagnostics", [])
                if uri:
                    self.diagnostics[uri] = diags
                    logger.debug(f"Received diagnostics for {uri}: {len(diags)} items.")

    async def send_request(self, method: str, params: Any = None) -> Any:
        """Send JSON-RPC request to language server and await result."""
        if not self._process or not self._process.stdin:
            raise RuntimeError("LSP client not connected.")
            
        self._request_id += 1
        req_id = self._request_id
        
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending_requests[req_id] = fut
        
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params
        }
        
        payload_bytes = json.dumps(payload).encode("utf-8")
        headers = f"Content-Length: {len(payload_bytes)}\r\n\r\n".encode("ascii")
        
        try:
            self._process.stdin.write(headers + payload_bytes)
            await self._process.stdin.drain()
        except Exception as e:
            self._pending_requests.pop(req_id, None)
            fut.set_exception(e)
            raise
            
        return await fut

    def send_notification(self, method: str, params: Any = None) -> None:
        """Send standard JSON-RPC notification (no response expected)."""
        if not self._process or not self._process.stdin:
            return
            
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        payload_bytes = json.dumps(payload).encode("utf-8")
        headers = f"Content-Length: {len(payload_bytes)}\r\n\r\n".encode("ascii")
        
        try:
            self._process.stdin.write(headers + payload_bytes)
        except Exception as e:
            logger.error(f"Error sending notification {method}: {e}")

    # --- Document Synchronizations & Queries ---

    async def open_document(self, file_path: Path, content: str) -> None:
        """Notify language server that a document has been opened."""
        if not self._initialized:
            return
        uri = file_path.as_uri()
        self._document_versions[uri] = 1
        
        # Match language mapping
        lang_id = self.language.lower()
        if lang_id == "typescript":
            lang_id = "typescript"
        elif lang_id == "python":
            lang_id = "python"
            
        self.send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": lang_id,
                "version": 1,
                "text": content
            }
        })

    async def update_document(self, file_path: Path, content: str) -> None:
        """Notify language server of document changes."""
        if not self._initialized:
            return
        uri = file_path.as_uri()
        version = self._document_versions.get(uri, 1) + 1
        self._document_versions[uri] = version
        
        self.send_notification("textDocument/didChange", {
            "textDocument": {
                "uri": uri,
                "version": version
            },
            "contentChanges": [{"text": content}]
        })

    async def get_completions(self, file_path: Path, line: int, character: int) -> List[Dict[str, Any]]:
        """Request auto-completions at specific cursor index."""
        if not self._initialized:
            return []
        uri = file_path.as_uri()
        try:
            result = await self.send_request("textDocument/completion", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character}
            })
            if isinstance(result, list):
                return result
            elif isinstance(result, dict):
                return result.get("items", [])
            return []
        except Exception as e:
            logger.error(f"LSP completion request failed: {e}")
            return []

    async def get_definition(self, file_path: Path, line: int, character: int) -> Optional[Any]:
        """Query definition location (Go-to-Definition)."""
        if not self._initialized:
            return None
        uri = file_path.as_uri()
        try:
            return await self.send_request("textDocument/definition", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character}
            })
        except Exception as e:
            logger.error(f"LSP definition request failed: {e}")
            return None

    async def get_hover(self, file_path: Path, line: int, character: int) -> Optional[str]:
        """Retrieve symbol tooltip documentation."""
        if not self._initialized:
            return None
        uri = file_path.as_uri()
        try:
            result = await self.send_request("textDocument/hover", {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character}
            })
            if not result:
                return None
            contents = result.get("contents")
            if isinstance(contents, dict) and "value" in contents:
                return contents["value"]
            elif isinstance(contents, list):
                return "\n".join([c if isinstance(c, str) else c.get("value", "") for c in contents])
            elif isinstance(contents, str):
                return contents
            return None
        except Exception as e:
            logger.error(f"LSP hover request failed: {e}")
            return None

    def get_diagnostics(self, file_path: Path) -> List[Dict[str, Any]]:
        """Fetch accumulated publishDiagnostics for document."""
        uri = file_path.as_uri()
        return self.diagnostics.get(uri, [])

    async def stop(self) -> None:
        """Shutdown connection and terminate subprocess."""
        if self._initialized:
            try:
                await self.send_request("shutdown")
                self.send_notification("exit")
            except Exception:
                pass
                
        if self._read_task:
            self._read_task.cancel()
            
        if self._process:
            try:
                self._process.terminate()
                await self._process.wait()
            except Exception:
                pass
            self._process = None
            
        self._initialized = False
        self._pending_requests.clear()
