"""Test all 12 gap features."""
import asyncio, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_model_catalog():
    from cyberclaw.core.model_catalog import get_catalog, ModelStatus
    cat = get_catalog()
    models = cat.list_models()
    assert len(models) >= 24, f"Expected 24+ models, got {len(models)}"
    # Cost estimation
    cost = cat.estimate_cost("openai", "gpt-4o-mini", 1000, 500)
    assert cost > 0
    # Find cheapest
    cheapest = cat.find_cheapest(needs_vision=True)
    assert cheapest is not None
    # Find best
    best = cat.find_best(needs_reasoning=True)
    assert best is not None
    # Providers
    providers = cat.list_providers()
    assert "openai" in providers and "gemini" in providers
    # Status filter
    available = cat.list_models(only_available=True)
    assert all(m.status == ModelStatus.AVAILABLE for m in available)
    print(f"  Model catalog: OK ({len(models)} models, {len(providers)} providers)")

def test_task_system():
    from cyberclaw.core.tasks import TaskStore, TaskExecutor, Task, TaskStatus
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "tasks.db")
        # Create and save
        t = Task(id="t1", name="Test", agent_id="cyberclaw", instruction="Do something")
        store.save(t)
        assert store.get("t1") is not None
        # Update status
        store.update_status("t1", TaskStatus.RUNNING)
        t2 = store.get("t1")
        assert t2.status == TaskStatus.RUNNING
        store.update_status("t1", TaskStatus.COMPLETED, result="Done!")
        t3 = store.get("t1")
        assert t3.status == TaskStatus.COMPLETED and t3.result == "Done!"
        # List
        assert len(store.list_tasks()) == 1
        assert len(store.list_tasks(TaskStatus.COMPLETED)) == 1
        # Cleanup
        assert store.cleanup_stale(0) == 1  # 0 hours = everything is stale
        store.close()
    print("  Task system (SQLite store, status, cleanup): OK")

def test_context_engine():
    from cyberclaw.core.context_engine import ContextEngine, ContextRequest
    engine = ContextEngine()
    engine.add_static("system", "You are CyberClaw.", priority=10)
    engine.register_provider("time", lambda r: __import__('cyberclaw.core.context_engine', fromlist=['ContextContribution']).ContextContribution(source="time", content=f"Current time: {__import__('time').strftime('%H:%M')}"))
    request = ContextRequest(agent_id="cyberclaw", user_message="hello")
    text = engine.build_text(request)
    assert "CyberClaw" in text
    assert "time" in engine.provider_names
    print("  Context engine: OK")

def test_commitments():
    from cyberclaw.core.commitments import CommitmentStore, extract_commitments
    with tempfile.TemporaryDirectory() as d:
        store = CommitmentStore(Path(d) / "commitments.json")
        c = store.add("sess1", "Follow up on the report", "tomorrow")
        assert c.id.startswith("cmt-")
        assert len(store.list_pending()) == 1
        store.fulfill(c.id)
        assert len(store.list_pending()) == 0
    # Extraction
    text = "Sure, I'll follow up on that tomorrow. I will also check the logs."
    found = extract_commitments(text)
    assert len(found) >= 1
    print("  Commitments (store + extraction): OK")

def test_trajectory():
    from cyberclaw.core.history import HistoryStore, HistoryMessage
    from cyberclaw.core.trajectory import TrajectoryManager
    from cyberclaw.core.events import CliEventSource
    with tempfile.TemporaryDirectory() as d:
        hist = HistoryStore(Path(d) / "hist")
        source = CliEventSource()
        hist.create_session("cyberclaw", "traj-test", source)
        hist.save_message("traj-test", HistoryMessage(role="user", content="Hello"))
        hist.save_message("traj-test", HistoryMessage(role="assistant", content="Hi!"))
        mgr = TrajectoryManager(hist, Path(d) / "exports")
        # Export JSON
        path = mgr.export_session("traj-test", "json")
        assert path and path.exists()
        # Export Markdown
        md_path = mgr.export_session("traj-test", "markdown")
        assert md_path and md_path.exists()
        assert "Hello" in md_path.read_text()
        # List exports
        assert len(mgr.list_exports()) == 2
        # Import
        sid = mgr.import_trajectory(path)
        assert sid and sid.startswith("imported-")
    print("  Trajectory (export JSON/MD, import): OK")

def test_auto_reply():
    from cyberclaw.core.auto_reply import AutoReplyPipeline, SendPolicy, InboundMessage
    pipeline = AutoReplyPipeline(SendPolicy(max_message_length=100, rate_limit_per_minute=5))
    # Should reply (DM)
    msg = InboundMessage(content="hi", source_id="user1", channel="telegram")
    assert pipeline.should_reply(msg)
    # Group without mention
    group_msg = InboundMessage(content="hi", source_id="user2", channel="discord", is_group=True)
    assert not pipeline.should_reply(group_msg)
    # Group with mention
    group_msg.mentions_bot = True
    assert pipeline.should_reply(group_msg)
    # Rate limiting
    for _ in range(5):
        pipeline.should_reply(InboundMessage(content="spam", source_id="spammer", channel="irc"))
    assert not pipeline.should_reply(InboundMessage(content="6th", source_id="spammer", channel="irc"))
    # Split reply
    long_text = "Line\n" * 50
    chunks = pipeline.split_reply(long_text)
    assert len(chunks) > 1
    print("  Auto-reply (pipeline, rate limit, split, group filter): OK")

def test_link_understanding():
    from cyberclaw.core.link_understanding import extract_urls
    urls = extract_urls("Check https://example.com and http://test.org/page?q=1 out")
    assert len(urls) == 2
    assert "https://example.com" in urls
    # No URLs
    assert extract_urls("no links here") == []
    # Max links
    text = " ".join(f"https://site{i}.com" for i in range(20))
    assert len(extract_urls(text, max_links=3)) == 3
    print("  Link understanding (URL extraction): OK")

def test_web_search_registry():
    from cyberclaw.core.web_search import get_search_registry
    reg = get_search_registry()
    providers = reg.list_providers()
    assert len(providers) == 3
    ids = [p.id for p in providers]
    assert "brave" in ids and "tavily" in ids and "duckduckgo" in ids
    # Auto-detect (should find DuckDuckGo as keyless fallback)
    auto = reg.auto_detect()
    assert auto is not None and auto.id == "duckduckgo"
    print("  Web search registry (3 providers, auto-detect): OK")

def test_music_tool():
    from cyberclaw.tools.music_tool import MUSIC_TOOL_SCHEMA, MusicGenerationRegistry
    assert MUSIC_TOOL_SCHEMA["function"]["name"] == "generate_music"
    reg = MusicGenerationRegistry()
    assert len(reg.list_providers()) == 0  # None registered yet
    print("  Music generation tool: OK")

def test_video_tool():
    from cyberclaw.tools.video_tool import VIDEO_TOOL_SCHEMA, VideoGenerationRegistry
    assert VIDEO_TOOL_SCHEMA["function"]["name"] == "generate_video"
    reg = VideoGenerationRegistry()
    assert len(reg.list_providers()) == 0
    print("  Video generation tool: OK")

def test_realtime_stt():
    from cyberclaw.voice.realtime_stt import RealtimeTranscriptionManager, TranscriptSegment
    mgr = RealtimeTranscriptionManager()
    session = mgr.create_session("test-session", "deepgram", "test-key")
    assert session.provider == "deepgram"
    assert mgr.get_session("test-session") is not None
    print("  Realtime transcription manager: OK")

if __name__ == "__main__":
    print("CyberClaw Gap Features Test")
    print("=" * 50)
    tests = [test_model_catalog, test_task_system, test_context_engine,
             test_commitments, test_trajectory, test_auto_reply,
             test_link_understanding, test_web_search_registry,
             test_music_tool, test_video_tool, test_realtime_stt]
    passed = failed = 0
    for t in tests:
        try: t(); passed += 1
        except Exception as e:
            print(f"  FAILED: {t.__name__}: {e}")
            import traceback; traceback.print_exc(); failed += 1
    print("=" * 50)
    print(f"Results: {passed}/{len(tests)} passed, {failed} failed")
    if failed: print("\nSome tests FAILED!"); sys.exit(1)
    else: print("\nALL GAP FEATURES TESTED AND PASSED!")
