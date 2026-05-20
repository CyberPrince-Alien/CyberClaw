"""MCP (Model Context Protocol) server and client for CyberClaw."""

import json
import logging
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class MCPTool:
    """An MCP tool descriptor."""

    def __init__(self, name: str, description: str, input_schema: dict[str, Any],
                 handler: Callable[..., Awaitable[str]]):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.handler = handler

    def to_mcp_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


class MCPServer:
    """CyberClaw as an MCP server — expose tools to external MCP clients.
    
    Implements the MCP protocol over stdio (JSON-RPC 2.0).
    External tools like Claude Desktop or other MCP clients can connect.
    """

    def __init__(self):
        self._tools: dict[str, MCPTool] = {}

    def register_tool(self, tool: MCPTool) -> None:
        self._tools[tool.name] = tool

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a JSON-RPC 2.0 MCP request."""
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            return self._success(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "cyberclaw", "version": "0.1.0"},
            })

        elif method == "tools/list":
            tools = [t.to_mcp_schema() for t in self._tools.values()]
            return self._success(req_id, {"tools": tools})

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            tool = self._tools.get(tool_name)
            if not tool:
                return self._error(req_id, -32602, f"Unknown tool: {tool_name}")
            try:
                result = await tool.handler(**arguments)
                return self._success(req_id, {
                    "content": [{"type": "text", "text": result}],
                })
            except Exception as e:
                return self._error(req_id, -32603, str(e))

        elif method == "ping":
            return self._success(req_id, {})

        return self._error(req_id, -32601, f"Method not found: {method}")

    @staticmethod
    def _success(req_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    @staticmethod
    def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


class MCPClient:
    """Connect to external MCP servers to import their tools.
    
    Wraps an MCP server's tools as CyberClaw tools.
    """

    def __init__(self, server_command: list[str]):
        self.server_command = server_command
        self._process = None
        self._tools: list[dict[str, Any]] = []

    async def connect(self) -> None:
        """Start the MCP server process and initialize."""
        import asyncio
        self._process = await asyncio.create_subprocess_exec(
            *self.server_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # Send initialize
        response = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "cyberclaw", "version": "0.1.0"},
        })
        logger.info("MCP server initialized: %s", response.get("result", {}).get("serverInfo", {}))

        # List tools
        tools_response = await self._send_request("tools/list", {})
        self._tools = tools_response.get("result", {}).get("tools", [])
        logger.info("MCP server provides %d tools", len(self._tools))

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on the MCP server."""
        response = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        result = response.get("result", {})
        content = result.get("content", [])
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        return "\n".join(texts)

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self._process or not self._process.stdin or not self._process.stdout:
            raise RuntimeError("MCP server not connected")

        import secrets
        req_id = secrets.token_hex(4)
        request = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        line = json.dumps(request) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

        response_line = await self._process.stdout.readline()
        return json.loads(response_line.decode())

    async def disconnect(self) -> None:
        if self._process:
            self._process.terminate()
            await self._process.wait()

    @property
    def tools(self) -> list[dict[str, Any]]:
        return self._tools
