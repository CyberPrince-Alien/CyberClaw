"""CyberClaw v0.2.0 COMPLETE feature test - every single feature."""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))


def test_sqlite_history():
    """Test SQLite history backend."""
    from cyberclaw.core.history_sqlite import SQLiteHistoryStore
    from cyberclaw.core.history import HistoryMessage
    from cyberclaw.core.events import CliEventSource

    with tempfile.TemporaryDirectory() as tmpdir:
        store = SQLiteHistoryStore(Path(tmpdir) / "test.db")
        source = CliEventSource()

        # Create session
        result = store.create_session("cyberclaw", "sess-1", source)
        assert result["id"] == "sess-1"

        # Save messages
        store.save_message("sess-1", HistoryMessage(role="user", content="Hello"))
        store.save_message("sess-1", HistoryMessage(role="assistant", content="Hi there!"))

        # List sessions
        sessions = store.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].message_count == 2
        assert sessions[0].title == "Hello"

        # Get messages
        messages = store.get_messages("sess-1")
        assert len(messages) == 2
        assert messages[0].content == "Hello"
        assert messages[1].content == "Hi there!"

        # Search
        results = store.search_messages("Hello")
        assert len(results) == 1

        # Session info
        info = store.get_session_info("sess-1")
        assert info is not None
        assert info.agent_id == "cyberclaw"

        store.close()
    print("  SQLite history backend: OK")


def test_metrics():
    """Test Prometheus metrics."""
    from cyberclaw.core.metrics import MetricsCollector, record_llm_call

    m = MetricsCollector()

    # Counter
    m.inc("test_counter")
    m.inc("test_counter")
    assert m.get_counter("test_counter") == 2.0

    # Gauge
    m.set_gauge("test_gauge", 42.0)
    assert m.get_gauge("test_gauge") == 42.0
    m.inc_gauge("test_gauge", 8.0)
    assert m.get_gauge("test_gauge") == 50.0
    m.dec_gauge("test_gauge", 10.0)
    assert m.get_gauge("test_gauge") == 40.0

    # Histogram
    m.observe("test_latency", 0.1)
    m.observe("test_latency", 0.2)
    m.observe("test_latency", 0.3)

    # Labels
    m.inc("labeled_counter", labels={"method": "GET", "path": "/health"})
    assert m.get_counter("labeled_counter", labels={"method": "GET", "path": "/health"}) == 1.0

    # Timer
    import time
    with m.timer("test_timer"):
        time.sleep(0.01)

    # Prometheus export
    prom = m.to_prometheus()
    assert "test_counter" in prom
    assert "test_gauge" in prom
    assert "cyberclaw_uptime_seconds" in prom

    # JSON export
    d = m.to_dict()
    assert "counters" in d
    assert "gauges" in d
    assert "histograms" in d
    assert d["uptime_seconds"] >= 0

    # Pre-defined helpers
    record_llm_call("openai", "gpt-4", 1.5, 100, 200)

    print("  Prometheus metrics: OK")


def test_secrets_store():
    """Test encrypted secrets store."""
    from cyberclaw.security.secrets_store import SecretsStore

    with tempfile.TemporaryDirectory() as tmpdir:
        store = SecretsStore(Path(tmpdir) / "vault.json")

        # Set and get
        store.set("openai_key", "sk-test-12345")
        value = store.get("openai_key")
        assert value == "sk-test-12345"

        # List keys
        keys = store.list_keys()
        assert "openai_key" in keys

        # Has
        assert store.has("openai_key")
        assert not store.has("nonexistent")

        # Delete
        assert store.delete("openai_key")
        assert not store.has("openai_key")
        assert store.get("openai_key") is None

        # Import from config
        config = {
            "llm": {
                "providers": [
                    {"api_key": "sk-real-key-1234567890", "model": "gpt-4"},
                ]
            },
            "channels": {
                "telegram": {"bot_token": "1234567890:ABCDEFG"}
            }
        }
        count = store._import_recursive(config)
        assert count >= 2  # api_key + bot_token

    print("  Encrypted secrets store: OK")


def test_signal_channel():
    """Test Signal channel event source."""
    from cyberclaw.channel.signal_channel import SignalEventSource, SignalChannel

    source = SignalEventSource(phone_number="+1234567890")
    assert str(source) == "platform-signal:+1234567890"

    s2 = SignalEventSource.from_string("platform-signal:+1234567890")
    assert s2.phone_number == "+1234567890"

    print("  Signal channel: OK")


def test_image_tool():
    """Test image tool schema."""
    from cyberclaw.tools.image_tool import IMAGE_TOOL_SCHEMA

    fn = IMAGE_TOOL_SCHEMA["function"]
    assert fn["name"] == "generate_image"
    assert "prompt" in fn["parameters"]["properties"]
    assert "dall-e" in fn["parameters"]["properties"]["provider"]["enum"]
    assert "stability" in fn["parameters"]["properties"]["provider"]["enum"]

    print("  Image generation tool: OK")


def test_vision_tool():
    """Test vision and document tools."""
    from cyberclaw.tools.vision_tool import (
        VISION_TOOL_SCHEMA, DOCUMENT_TOOL_SCHEMA,
        document_read_handler,
    )

    # Schemas
    assert VISION_TOOL_SCHEMA["function"]["name"] == "analyze_image"
    assert DOCUMENT_TOOL_SCHEMA["function"]["name"] == "read_document"

    # Document reader - text file
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("Hello document world!")
        result = asyncio.run(document_read_handler("test.txt", workspace=tmpdir))
        assert "Hello document world!" in result

        # CSV file
        csv_file = Path(tmpdir) / "data.csv"
        csv_file.write_text("name,age\nAlice,30\nBob,25")
        result = asyncio.run(document_read_handler("data.csv", workspace=tmpdir))
        assert "Alice" in result

        # JSON file
        json_file = Path(tmpdir) / "config.json"
        json_file.write_text('{"key": "value"}')
        result = asyncio.run(document_read_handler("config.json", workspace=tmpdir))
        assert "value" in result

        # Missing file
        result = asyncio.run(document_read_handler("missing.txt", workspace=tmpdir))
        assert "Error" in result

    print("  Vision + document understanding: OK")


def test_wake_word():
    """Test wake word detector creation."""
    from cyberclaw.voice.wake_word import WakeWordDetector

    detector = WakeWordDetector(wake_words=["hey cyberclaw"])
    assert "hey cyberclaw" in detector.wake_words
    assert detector.sensitivity == 0.5
    assert not detector._running

    print("  Wake word detector: OK")


def test_windows_service():
    """Test service manager creation."""
    from cyberclaw.utils.service import WindowsServiceManager

    mgr = WindowsServiceManager(Path("."))
    assert mgr.SERVICE_NAME == "CyberClawGateway"
    assert mgr.DISPLAY_NAME == "CyberClaw AI Assistant Gateway"

    # Status check (won't fail even if not installed)
    status = mgr.status()
    assert isinstance(status, str)

    print("  Windows service manager: OK")


def test_signal_config():
    """Test Signal config model."""
    from cyberclaw.utils.config import SignalConfig

    cfg = SignalConfig(phone_number="+1234567890")
    assert cfg.api_url == "http://localhost:8080"
    assert cfg.dm_policy == "pairing"
    assert cfg.enabled

    print("  Signal config model: OK")


def test_sqlite_migration():
    """Test JSONL to SQLite migration."""
    from cyberclaw.core.history import HistoryStore, HistoryMessage
    from cyberclaw.core.history_sqlite import SQLiteHistoryStore
    from cyberclaw.core.events import CliEventSource

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create JSONL store with data
        jsonl_store = HistoryStore(tmppath / "jsonl")
        source = CliEventSource()
        jsonl_store.create_session("cyberclaw", "migrate-test", source)
        jsonl_store.save_message("migrate-test", HistoryMessage(role="user", content="migrate me"))
        jsonl_store.save_message("migrate-test", HistoryMessage(role="assistant", content="done!"))

        # Migrate to SQLite
        sqlite_store = SQLiteHistoryStore(tmppath / "test.db")
        count = sqlite_store.migrate_from_jsonl(jsonl_store)
        assert count == 1

        # Verify
        sessions = sqlite_store.list_sessions()
        assert len(sessions) == 1
        messages = sqlite_store.get_messages("migrate-test")
        assert len(messages) == 2
        assert messages[0].content == "migrate me"

        sqlite_store.close()

    print("  JSONL -> SQLite migration: OK")


if __name__ == "__main__":
    print("CyberClaw v0.2.0 COMPLETE Feature Tests")
    print("=" * 50)

    tests = [
        test_sqlite_history,
        test_metrics,
        test_secrets_store,
        test_signal_channel,
        test_image_tool,
        test_vision_tool,
        test_wake_word,
        test_windows_service,
        test_signal_config,
        test_sqlite_migration,
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
        print("\nALL REMAINING FEATURES TESTED AND PASSED!")
