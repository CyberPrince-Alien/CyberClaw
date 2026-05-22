import os
import json
import logging
import asyncio
import tempfile
import re
from pathlib import Path
import httpx
from typing import Callable, Dict, Any, Optional

logger = logging.getLogger(__name__)

class IDECompanion:
    """
    Manages connection and communication with the VS Code IDE Companion extension
    using the Model Context Protocol (MCP) HTTP/SSE transport.
    """

    def __init__(self, context) -> None:
        self.context = context
        self.status = "disconnected"  # connected, disconnected, connecting
        self.port: Optional[int] = None
        self.auth_token: Optional[str] = None
        self.workspace_path: Optional[str] = None
        self.session_id: Optional[str] = None
        self.open_files = []
        self.is_trusted = True
        
        # Pending diff results: dict mapping filePath -> asyncio.Future
        self._pending_diffs: Dict[str, asyncio.Future] = {}
        self._client: Optional[httpx.AsyncClient] = None
        self._listen_task: Optional[asyncio.Task] = None
        self._scan_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start the background directory scan and monitoring loop."""
        self._running = True
        self._scan_task = asyncio.create_task(self._scan_loop())
        logger.info("IDE Companion manager started background scan loop.")

    async def stop(self) -> None:
        """Stop background tasks and close active connections."""
        self._running = False
        if self._scan_task:
            self._scan_task.cancel()
            self._scan_task = None
        if self._listen_task:
            self._listen_task.cancel()
            self._listen_task = None
        if self._client:
            await self._client.aclose()
            self._client = None
        self.status = "disconnected"

    async def _scan_loop(self) -> None:
        """Periodically scan for VS Code port files in temp directory."""
        while self._running:
            try:
                if self.status == "disconnected":
                    await self._discover_and_connect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in IDE Companion scan loop: {e}", exc_info=True)
            await asyncio.sleep(5.0)

    async def _discover_and_connect(self) -> None:
        """Scan temp dir, find a valid IDE companion config, and connect."""
        temp_dir = Path(tempfile.gettempdir()) / "gemini" / "ide"
        if not temp_dir.exists():
            return

        # Find files matching gemini-ide-server-*.json
        config_files = list(temp_dir.glob("gemini-ide-server-*.json"))
        if not config_files:
            return

        # Parse files and find a valid workspace path
        cwd = Path(os.getcwd()).resolve()
        
        for file_path in config_files:
            try:
                content = file_path.read_text(encoding="utf-8")
                config = json.loads(content)
                port = config.get("port")
                workspace_path_str = config.get("workspacePath")
                auth_token = config.get("authToken")

                if not port or not workspace_path_str:
                    continue

                # Check if current directory is a subpath of workspace
                # workspacePath can contain multiple paths separated by delimiter (semicolon on Win, colon on Unix)
                sep = ";" if os.name == "nt" else ":"
                workspace_paths = [Path(p).resolve() for p in workspace_path_str.split(sep) if p]
                
                is_valid_workspace = False
                for wpath in workspace_paths:
                    try:
                        # Check if cwd is subpath of wpath
                        cwd.relative_to(wpath)
                        is_valid_workspace = True
                        break
                    except ValueError:
                        continue

                if is_valid_workspace:
                    logger.info(f"Discovered matching IDE port config at {file_path}")
                    self.port = int(port)
                    self.auth_token = auth_token
                    self.workspace_path = workspace_path_str
                    self.status = "connecting"
                    
                    # Establish connection
                    connected = await self._connect_mcp()
                    if connected:
                        return
            except Exception as e:
                logger.debug(f"Failed to process port file {file_path}: {e}")
                continue

    async def _connect_mcp(self) -> bool:
        """Establish HTTP connection and listen to the SSE stream."""
        self._client = httpx.AsyncClient(timeout=30.0)
        base_url = f"http://127.0.0.1:{self.port}"
        
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        try:
            # 1. Initialize MCP session
            init_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "cyberclaw-companion-client",
                        "version": "0.2.0"
                    }
                }
            }
            logger.info(f"Sending initialize request to IDE companion at {base_url}/mcp")
            resp = await self._client.post(f"{base_url}/mcp", json=init_payload, headers=headers)
            
            if resp.status_code != 200:
                logger.error(f"Failed to initialize IDE Companion. Status code: {resp.status_code}")
                await self._client.aclose()
                self._client = None
                self.status = "disconnected"
                return False

            self.session_id = resp.headers.get("mcp-session-id")
            if not self.session_id:
                # Try to parse session_id from response JSON or query parameters if not in headers
                logger.error("No mcp-session-id header in initialize response.")
                await self._client.aclose()
                self._client = None
                self.status = "disconnected"
                return False

            logger.info(f"Initialized IDE session: {self.session_id}")

            # 2. Send notifications/initialized
            initialized_headers = headers.copy()
            initialized_headers["mcp-session-id"] = self.session_id
            await self._client.post(
                f"{base_url}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized"
                },
                headers=initialized_headers
            )

            # 3. Start background listener task for SSE stream
            self._listen_task = asyncio.create_task(self._listen_sse_stream())
            self.status = "connected"
            return True

        except Exception as e:
            logger.error(f"Error connecting to IDE Companion: {e}")
            await self._client.aclose()
            self._client = None
            self.status = "disconnected"
            return False

    async def _listen_sse_stream(self) -> None:
        """Listen to the Server-Sent Events stream from the IDE Companion."""
        base_url = f"http://127.0.0.1:{self.port}"
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        headers["mcp-session-id"] = self.session_id

        logger.info("Listening to IDE Companion SSE stream...")
        try:
            # We use an async request with stream=True
            async with self._client.stream("GET", f"{base_url}/mcp", headers=headers) as response:
                if response.status_code != 200:
                    logger.error(f"SSE stream returned status {response.status_code}")
                    self.status = "disconnected"
                    return

                buffer = ""
                async for line in response.iter_lines():
                    # Parse Server-Sent Events (SSE)
                    line = line.strip()
                    if not line:
                        continue
                    
                    if line.startswith("data:"):
                        data_content = line[5:].strip()
                        await self._handle_incoming_message(data_content)
        except asyncio.CancelledError:
            logger.info("SSE listener cancelled.")
        except Exception as e:
            logger.error(f"Error in SSE stream listener: {e}")
        finally:
            self.status = "disconnected"
            self.session_id = None
            self.open_files = []
            logger.info("IDE Companion disconnected.")

    async def _handle_incoming_message(self, raw_msg: str) -> None:
        """Process messages received from the IDE Companion server."""
        try:
            msg = json.loads(raw_msg)
            method = msg.get("method")
            params = msg.get("params", {})

            if method == "ide/contextUpdate":
                # Context update notification containing open files and workspace trust status
                workspace_state = params.get("workspaceState", {})
                self.open_files = workspace_state.get("openFiles", [])
                self.is_trusted = workspace_state.get("isTrusted", True)
                
                # Push event to websocket if websocket_worker is available
                if self.context.websocket_worker:
                    await self.context.websocket_worker.broadcast({
                        "type": "ide_context_update",
                        "open_files": self.open_files,
                        "is_trusted": self.is_trusted
                    })
                logger.debug(f"Received ide/contextUpdate with {len(self.open_files)} open files.")

            elif method == "ide/diffAccepted":
                file_path = params.get("filePath")
                content = params.get("content")
                if file_path in self._pending_diffs:
                    self._pending_diffs[file_path].set_result({"status": "accepted", "content": content})
                    del self._pending_diffs[file_path]
                logger.info(f"Diff accepted for {file_path}")

            elif method in ("ide/diffRejected", "ide/diffClosed"):
                file_path = params.get("filePath")
                if file_path in self._pending_diffs:
                    self._pending_diffs[file_path].set_result({"status": "rejected", "content": None})
                    del self._pending_diffs[file_path]
                logger.info(f"Diff rejected/closed for {file_path}")

        except Exception as e:
            logger.error(f"Error parsing incoming message: {raw_msg}. Error: {e}")

    async def open_diff(self, file_path: str, new_content: str) -> Dict[str, Any]:
        """
        Request VS Code Companion to open a side-by-side diff.
        Returns a dictionary indicating whether the diff was accepted or rejected.
        """
        if self.status != "connected":
            return {"status": "error", "error": "IDE Companion is not connected"}

        # Absolute path string normalization
        file_path_abs = str(Path(file_path).resolve())
        
        # Create a Future to wait for the user decision
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending_diffs[file_path_abs] = fut

        base_url = f"http://127.0.0.1:{self.port}"
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        headers["mcp-session-id"] = self.session_id

        payload = {
            "jsonrpc": "2.0",
            "id": int(asyncio.get_event_loop().time() * 1000),
            "method": "tools/call",
            "params": {
                "name": "openDiff",
                "arguments": {
                    "filePath": file_path_abs,
                    "newContent": new_content
                }
            }
        }

        try:
            resp = await self._client.post(f"{base_url}/mcp", json=payload, headers=headers)
            if resp.status_code != 200:
                self._pending_diffs.pop(file_path_abs, None)
                return {"status": "error", "error": f"OpenDiff request failed with status {resp.status_code}"}
            
            # Check response body for internal JSON-RPC error
            resp_json = resp.json()
            if "error" in resp_json:
                self._pending_diffs.pop(file_path_abs, None)
                return {"status": "error", "error": resp_json["error"].get("message", "Unknown error")}

            # Wait for user decision via SSE notification callbacks
            result = await fut
            return result

        except Exception as e:
            self._pending_diffs.pop(file_path_abs, None)
            logger.error(f"Error opening diff: {e}")
            return {"status": "error", "error": str(e)}

    async def close_diff(self, file_path: str) -> Dict[str, Any]:
        """Request VS Code Companion to close a diff."""
        if self.status != "connected":
            return {"status": "error", "error": "IDE Companion is not connected"}

        file_path_abs = str(Path(file_path).resolve())
        
        base_url = f"http://127.0.0.1:{self.port}"
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        headers["mcp-session-id"] = self.session_id

        payload = {
            "jsonrpc": "2.0",
            "id": int(asyncio.get_event_loop().time() * 1000),
            "method": "tools/call",
            "params": {
                "name": "closeDiff",
                "arguments": {
                    "filePath": file_path_abs,
                    "suppressNotification": True
                }
            }
        }

        try:
            resp = await self._client.post(f"{base_url}/mcp", json=payload, headers=headers)
            if resp.status_code != 200:
                return {"status": "error", "error": f"CloseDiff request failed with status {resp.status_code}"}
            return {"status": "ok"}
        except Exception as e:
            logger.error(f"Error closing diff: {e}")
            return {"status": "error", "error": str(e)}
