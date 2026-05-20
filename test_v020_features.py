"""Comprehensive test for CyberClaw v0.2.0 new features."""

import asyncio
import json
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def test_streaming():
    """Test streaming protocol."""
    from cyberclaw.core.streaming import StreamChunk, ChunkType, collect_stream

    # Test chunk creation
    chunk = StreamChunk(type=ChunkType.TOKEN, content="Hello")
    assert chunk.type == ChunkType.TOKEN
    assert chunk.content == "Hello"
    
    # Test SSE conversion
    sse = chunk.to_sse()
    assert sse.startswith("data: ")
    data = json.loads(sse.replace("data: ", "").strip())
    assert data["type"] == "token"
    assert data["content"] == "Hello"

    # Test stream collection
    async def mock_stream():
        yield StreamChunk(type=ChunkType.TOKEN, content="Hello ")
        yield StreamChunk(type=ChunkType.TOKEN, content="World")
        yield StreamChunk(type=ChunkType.DONE)

    result = asyncio.run(collect_stream(mock_stream()))
    assert result == "Hello World"
    print("  Streaming protocol: OK")


def test_model_info():
    """Test ModelInfo."""
    from cyberclaw.provider.llm.base import ModelInfo

    info = ModelInfo(
        model="gpt-4",
        max_tokens=8192,
        supports_tools=True,
        supports_vision=True,
        supports_streaming=True,
        context_window=128000,
    )
    assert info.safe_token_threshold == 102400  # 80% of 128000
    print("  ModelInfo: OK")


def test_plugin_system():
    """Test plugin SDK and registry."""
    from cyberclaw.plugins.sdk import Plugin, PluginManifest, PluginCapability
    from cyberclaw.plugins.registry import PluginRegistry

    # Test manifest
    manifest = PluginManifest(
        name="test-plugin",
        version="1.0.0",
        description="Test plugin",
        capabilities=[PluginCapability.TOOL],
    )
    assert manifest.name == "test-plugin"
    assert PluginCapability.CHANNEL.value == "channel"
    print("  Plugin SDK: OK")


def test_security():
    """Test security subsystem."""
    import tempfile
    from cyberclaw.security import PairingStore, AuditLogger, GatewayAuth

    # Test GatewayAuth
    auth = GatewayAuth(["secret-token-1"])
    assert auth.enabled
    assert auth.validate("secret-token-1")
    assert not auth.validate("wrong-token")

    no_auth = GatewayAuth()
    assert not no_auth.enabled
    assert no_auth.validate("anything")  # No auth = everything passes

    # Test PairingStore
    with tempfile.TemporaryDirectory() as tmpdir:
        store = PairingStore(Path(tmpdir))
        code = store.generate_code("telegram", "user123")
        assert len(code) == 6
        assert not store.is_approved("telegram", "user123")

        # Approve
        result = store.approve("telegram", code)
        assert result == "user123"
        assert store.is_approved("telegram", "user123")

        # Revoke
        assert store.revoke("telegram", "user123")
        assert not store.is_approved("telegram", "user123")

    # Test AuditLogger
    with tempfile.TemporaryDirectory() as tmpdir:
        audit = AuditLogger(Path(tmpdir))
        audit.log("login", "admin", {"ip": "127.0.0.1"})
        entries = audit.get_recent()
        assert len(entries) == 1
        assert entries[0]["action"] == "login"

    print("  Security (auth, pairing, audit): OK")


def test_mcp():
    """Test MCP server."""
    from cyberclaw.mcp import MCPServer, MCPTool

    server = MCPServer()

    async def echo_handler(text: str = "") -> str:
        return f"Echo: {text}"

    server.register_tool(MCPTool(
        name="echo",
        description="Echo text",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        handler=echo_handler,
    ))

    # Test initialize
    result = asyncio.run(server.handle_request({
        "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}
    }))
    assert result["result"]["serverInfo"]["name"] == "cyberclaw"

    # Test tools/list
    result = asyncio.run(server.handle_request({
        "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}
    }))
    tools = result["result"]["tools"]
    assert len(tools) == 1
    assert tools[0]["name"] == "echo"

    # Test tools/call
    result = asyncio.run(server.handle_request({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "echo", "arguments": {"text": "hello"}}
    }))
    assert "Echo: hello" in result["result"]["content"][0]["text"]

    print("  MCP server: OK")


def test_file_tools():
    """Test file tools."""
    import tempfile
    from cyberclaw.tools.file_tools import (
        read_file_handler, write_file_handler,
        list_dir_handler, search_files_handler,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write
        result = asyncio.run(write_file_handler("test.txt", "Hello World", workspace=tmpdir))
        assert "Wrote" in result

        # Read
        result = asyncio.run(read_file_handler("test.txt", workspace=tmpdir))
        assert result == "Hello World"

        # List
        result = asyncio.run(list_dir_handler(".", workspace=tmpdir))
        assert "test.txt" in result

        # Search
        result = asyncio.run(search_files_handler("Hello", ".", workspace=tmpdir))
        assert "Hello World" in result

        # Path escape protection
        try:
            asyncio.run(read_file_handler("../../etc/passwd", workspace=tmpdir))
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    print("  File tools (read/write/list/search): OK")


def test_config_new_models():
    """Test that new config models load correctly."""
    from cyberclaw.utils.config import (
        SlackConfig, WhatsAppConfig, MatrixConfig, IRCConfig, WebChatConfig,
        TTSConfig, STTConfig, SecurityConfig, MCPServerConfig,
        ChannelConfig,
    )

    # All new channel configs
    slack = SlackConfig(bot_token="xoxb-test")
    assert slack.enabled
    assert slack.dm_policy == "pairing"

    whatsapp = WhatsAppConfig(phone_number_id="123", access_token="abc")
    assert whatsapp.verify_token == "cyberclaw-verify"

    matrix = MatrixConfig(homeserver="https://matrix.org", user_id="@bot:matrix.org", access_token="t")
    assert matrix.homeserver == "https://matrix.org"

    irc = IRCConfig(server="irc.libera.chat")
    assert irc.port == 6667
    assert irc.nick == "CyberClaw"

    webchat = WebChatConfig()
    assert webchat.enabled

    # Channel config with all channels
    channel_cfg = ChannelConfig(
        enabled=True,
        slack=slack,
        whatsapp=whatsapp,
        matrix=matrix,
        irc=irc,
        webchat=webchat,
    )
    assert channel_cfg.slack is not None
    assert channel_cfg.whatsapp is not None

    # Voice configs
    tts = TTSConfig(enabled=True, provider="edge-tts")
    assert tts.voice == "en-US-AriaNeural"

    stt = STTConfig(enabled=True, provider="whisper")
    assert stt.model == "whisper-1"

    # Security config
    sec = SecurityConfig(gateway_tokens=["token1"])
    assert sec.audit_enabled

    # MCP config
    mcp = MCPServerConfig(name="test", command=["node", "server.js"])
    assert mcp.name == "test"

    print("  Config models (all channels, voice, security, MCP): OK")


def test_channel_event_sources():
    """Test new channel event sources."""
    from cyberclaw.channel.slack_channel import SlackEventSource
    from cyberclaw.channel.whatsapp_channel import WhatsAppEventSource
    from cyberclaw.channel.webchat_channel import WebChatEventSource
    from cyberclaw.channel.matrix_channel import MatrixEventSource
    from cyberclaw.channel.irc_channel import IRCEventSource

    # Slack
    s = SlackEventSource(user_id="U123", channel_id="C456")
    assert str(s) == "platform-slack:C456:U123"
    s2 = SlackEventSource.from_string("platform-slack:C456:U123")
    assert s2.user_id == "U123"

    # WhatsApp
    w = WhatsAppEventSource(phone_number="+1234567890")
    assert str(w) == "platform-whatsapp:+1234567890"

    # WebChat
    wc = WebChatEventSource(session_token="abc123")
    assert str(wc) == "platform-webchat:abc123"

    # Matrix
    m = MatrixEventSource(user_id="@user:matrix.org", room_id="!room:matrix.org")
    assert "matrix" in str(m)

    # IRC
    i = IRCEventSource(nick="user", channel_name="#test")
    assert "irc" in str(i)

    print("  Channel event sources (Slack, WhatsApp, WebChat, Matrix, IRC): OK")


def test_voice_managers():
    """Test voice manager infrastructure (not actual TTS/STT)."""
    from cyberclaw.voice import TTSManager, STTManager

    tts = TTSManager()
    assert tts.get() is None  # No provider registered

    stt = STTManager()
    assert stt.get() is None  # No provider registered

    print("  Voice managers: OK")


def test_browser_tool_schema():
    """Test browser tool schema is valid."""
    from cyberclaw.tools.browser_tool import BROWSER_TOOL_SCHEMA

    assert BROWSER_TOOL_SCHEMA["type"] == "function"
    fn = BROWSER_TOOL_SCHEMA["function"]
    assert fn["name"] == "browser"
    actions = fn["parameters"]["properties"]["action"]["enum"]
    assert "navigate" in actions
    assert "screenshot" in actions
    assert "click" in actions
    print("  Browser tool schema: OK")


if __name__ == "__main__":
    print("CyberClaw v0.2.0 Feature Tests")
    print("=" * 50)

    tests = [
        test_streaming,
        test_model_info,
        test_plugin_system,
        test_security,
        test_mcp,
        test_file_tools,
        test_config_new_models,
        test_channel_event_sources,
        test_voice_managers,
        test_browser_tool_schema,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAILED: {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("=" * 50)
    print(f"Results: {passed}/{len(tests)} passed, {failed} failed")

    if failed:
        print("\nSome tests FAILED!")
        sys.exit(1)
    else:
        print("\nALL v0.2.0 TESTS PASSED!")
