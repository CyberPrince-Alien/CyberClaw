"""Comprehensive test suite for Hermes power-ups in CyberClaw.

Tests VSA/HRR memory, Context Guard compression, POSIX Shell translation, and Skill Curator.
"""
import sys
import os
import asyncio
import tempfile
import shutil
import time
from pathlib import Path
import numpy as np

# Ensure src/ is in the python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from cyberclaw.core.holographic.holographic import (
    encode_atom,
    bind,
    unbind,
    bundle,
    similarity,
    encode_text,
    encode_fact,
)
from cyberclaw.core.holographic.store import HolographicStore
from cyberclaw.core.holographic.retrieval import FactRetriever
from cyberclaw.core.context_guard import ContextGuard
from cyberclaw.tools.builtin_tools import bash
from cyberclaw.core.skill_curator import SkillCurator
from cyberclaw.utils.config import Config


# =====================================================================
# 1. HOLOGRAPHIC MEMORY & VSA TESTS
# =====================================================================
def test_vsa_algebra():
    print("Testing VSA Algebra...")
    dim = 1024
    
    # Deterministic generation
    atom_a1 = encode_atom("python", dim)
    atom_a2 = encode_atom("python", dim)
    atom_b = encode_atom("javascript", dim)
    
    assert np.allclose(atom_a1, atom_a2), "Atom generation must be deterministic"
    assert not np.allclose(atom_a1, atom_b), "Different concepts must have different phases"
    assert atom_a1.shape == (dim,), "Vector dimension must match"
    
    # Similarity
    sim_self = similarity(atom_a1, atom_a1)
    sim_other = similarity(atom_a1, atom_b)
    
    assert np.isclose(sim_self, 1.0), f"Self similarity should be close to 1.0, got {sim_self}"
    assert abs(sim_other) < 0.15, f"Orthogonal similarity should be low, got {sim_other}"
    
    # Binding & Unbinding
    # Key-Value binding: bind(key, value)
    key = encode_atom("language", dim)
    val = encode_atom("python", dim)
    
    bound = bind(key, val)
    retrieved = unbind(bound, key)
    
    sim_retrieved = similarity(retrieved, val)
    assert np.isclose(sim_retrieved, 1.0), f"Unbinding retrieved wrong vector, similarity {sim_retrieved}"
    
    # Bundling (Superposition)
    bundled = bundle(atom_a1, atom_b)
    sim_with_a = similarity(bundled, atom_a1)
    sim_with_b = similarity(bundled, atom_b)
    
    assert sim_with_a > 0.4, f"Bundled similarity to element A should be high, got {sim_with_a}"
    assert sim_with_b > 0.4, f"Bundled similarity to element B should be high, got {sim_with_b}"
    
    print("  VSA Algebra: OK")


def test_holographic_store_and_retrieval():
    print("Testing Holographic Store and Retrieval...")
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "holographic_memory.db"
        store = HolographicStore(db_path, dim=1024)
        retriever = FactRetriever(store)
        
        # Add facts
        fact_id_1 = store.add_fact(
            content="Django uses settings.py for project configurations.",
            category="django",
            tags="framework,python,web",
            trust_score=0.8,
            entities=["Django", "settings_py"]
        )
        fact_id_2 = store.add_fact(
            content="FastAPI uses pydantic for request validation.",
            category="fastapi",
            tags="framework,python,api",
            trust_score=0.9,
            entities=["FastAPI", "Pydantic"]
        )
        
        # Verify SQLite insertion and entity tables
        entities = store.get_entities()
        entity_names = [e["name"] for e in entities]
        assert "Django" in entity_names, "Entity Django was not registered"
        assert "FastAPI" in entity_names, "Entity FastAPI was not registered"
        
        # Rebuild and check category bank
        bank_django = store.get_category_bank("django")
        assert bank_django is not None, "Category bank not created"
        assert bank_django.shape == (1024,), "Category bank vector has incorrect shape"
        
        # Retrieval / Search
        search_res = retriever.search("Which file does Django use for configuration?", category="django")
        assert len(search_res) > 0, "Search returned no results"
        assert "django" in search_res[0]["content"].lower(), "Incorrect fact retrieved"
        
        # VSA Probing
        probe_res = retriever.probe("Django", category="django")
        assert len(probe_res) > 0, "VSA probe returned no results"
        assert "settings.py" in probe_res[0]["content"], "VSA probe did not match expected content"
        
        # Contradiction
        contradict_res = retriever.contradict("Django configuration uses setup.py instead of settings.py")
        assert len(contradict_res) > 0, "Contradiction detector returned no results"
        assert contradict_res[0]["contradiction_score"] > 0.1, "Contradiction score should be high"
        
        # Close connection to free file handle on Windows
        store.close()
        
        print("  Holographic Store & Retrieval: OK")


# =====================================================================
# 2. CONTEXT GUARD COMPRESSION TESTS
# =====================================================================
def test_context_guard_compression():
    print("Testing Context Guard Compression...")
    # Mock context and configuration
    class MockConfig:
        workspace = Path(".")
    class MockSharedContext:
        config = MockConfig()
    
    shared_context = MockSharedContext()
    guard = ContextGuard(shared_context=shared_context, token_threshold=2000, max_tool_result_chars=100)
    
    # 1. Output pruning & condensation
    messages = [
        {"role": "user", "content": "Run some commands"},
        {
            "role": "assistant",
            "content": "Executing python commands",
            "tool_calls": [
                {
                    "id": "tc-1",
                    "type": "function",
                    "function": {"name": "bash", "arguments": '{"command": "echo hello"}'}
                }
            ]
        },
        {
            "role": "tool",
            "tool_call_id": "tc-1",
            "content": "line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\nline9\nline10"
        }
    ]
    
    pruned = guard._prune_and_condense_messages(messages)
    assert "[shell] ran 'echo hello'" in pruned[2]["content"], f"Pruning output failed, got: {pruned[2]['content']}"
    
    # 2. Duplicate read deduplication
    messages_dup = [
        {
            "role": "assistant",
            "content": "Checking files",
            "tool_calls": [
                {
                    "id": "tc-read-1",
                    "type": "function",
                    "function": {"name": "read", "arguments": '{"path": "src/main.py"}'}
                },
                {
                    "id": "tc-read-2",
                    "type": "function",
                    "function": {"name": "read", "arguments": '{"path": "src/main.py"}'}
                }
            ]
        },
        {
            "role": "tool",
            "tool_call_id": "tc-read-1",
            "content": "old content in file"
        },
        {
            "role": "tool",
            "tool_call_id": "tc-read-2",
            "content": "newer content in file"
        }
    ]
    
    deduplicated = guard._prune_and_condense_messages(messages_dup)
    assert "[Duplicate tool output" in deduplicated[1]["content"], "Older duplicate read was not pruned"
    assert "newer content" in deduplicated[2]["content"] or "[read_file]" in deduplicated[2]["content"], "Newer read was incorrectly pruned"
    
    # 3. Base64 payload stripping
    messages_b64 = [
        {"role": "user", "content": "data:image/png;base64," + "A" * 150},
        {"role": "user", "content": "keep this last turn intact: data:image/png;base64,iVBORw0KGgoAAA"},
        {"role": "user", "content": "dummy 3"},
        {"role": "user", "content": "dummy 4"},
        {"role": "user", "content": "dummy 5"},
        {"role": "user", "content": "dummy 6"},
    ]
    
    stripped = guard._prune_and_condense_messages(messages_b64)
    # The first message is older than the last 4 turns, so it should be stripped
    assert "[PRUNED_IMAGE_PAYLOAD]" in stripped[0]["content"], f"B64 image pruning failed, got {stripped[0]['content']}"
    
    # 4. JSON argument truncation
    massive_code = "a" * 3000
    messages_large_arg = [
        {
            "role": "assistant",
            "content": "Write script",
            "tool_calls": [
                {
                    "id": "tc-write",
                    "type": "function",
                    "function": {
                        "name": "write",
                        "arguments": f'{{"path": "test.py", "content": "{massive_code}"}}'
                    }
                }
            ]
        }
    ]
    
    condensed_args = guard._prune_and_condense_messages(messages_large_arg)
    tc_args = condensed_args[0]["tool_calls"][0]["function"]["arguments"]
    assert "Truncated" in tc_args, f"JSON arguments was not truncated, got {tc_args}"
    
    print("  Context Guard Compression: OK")


# =====================================================================
# 3. POSIX SHELL INTEGRATION TESTS
# =====================================================================
async def test_posix_shell_integration():
    print("Testing POSIX Windows Shell Integration...")
    # Since we are on Windows, let's verify if Git Bash translation rules execute orPowerShell translates.
    class MockConfig:
        workspace = Path(".")
    class MockSharedContext:
        config = MockConfig()
    class MockSessionState:
        shared_context = MockSharedContext()
    class MockSession:
        shared_context = MockSharedContext()
        state = MockSessionState()
        
    # Test path and command translation.
    # We will trigger the translator by running a mock command.
    # Note: On Windows, we'll try to run bash. If it fails or works, we'll confirm translation paths.
    test_command = "echo 'hello' > /dev/null"
    res = await bash.execute(MockSession(), command=test_command)
    assert "Error executing" not in res, f"Bash tool failed: {res}"
    
    print("  POSIX Shell Integration: OK")


# =====================================================================
# 4. SKILL CURATOR TESTS
# =====================================================================
def test_skill_curator():
    print("Testing Skill Curator Lifecycle...")
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace_dir = Path(temp_dir)
        skills_dir = workspace_dir / "skills"
        skills_dir.mkdir()
        
        # Create an active skill (recent timestamp)
        active_skill = skills_dir / "active-skill"
        active_skill.mkdir()
        (active_skill / "SKILL.md").write_text(
            "---\nname: Active Skill\ndescription: Recently modified\n---\nDo active stuff.",
            encoding="utf-8"
        )
        
        # Create a stale skill (modified 35 days ago)
        stale_skill = skills_dir / "stale-skill"
        stale_skill.mkdir()
        stale_file = stale_skill / "SKILL.md"
        stale_file.write_text(
            "---\nname: Stale Skill\ndescription: Modified a month ago\n---\nDo stale stuff.",
            encoding="utf-8"
        )
        # Shift modification time back 35 days
        mtime = time.time() - (35 * 86400)
        os.utime(str(stale_file), (mtime, mtime))
        
        # Create an archived skill (modified 95 days ago)
        archived_skill = skills_dir / "archived-skill"
        archived_skill.mkdir()
        archived_file = archived_skill / "SKILL.md"
        archived_file.write_text(
            "---\nname: Archived Skill\ndescription: Modified long ago\n---\nDo old stuff.",
            encoding="utf-8"
        )
        # Shift modification time back 95 days
        mtime = time.time() - (95 * 86400)
        os.utime(str(archived_file), (mtime, mtime))
        
        # Setup configuration
        from cyberclaw.utils.config import LLMConfig, ChannelConfig, ApiConfig
        config = Config(
            workspace=workspace_dir,
            default_agent="cyberclaw",
            llm=LLMConfig(),
            channels=ChannelConfig(),
            api=ApiConfig()
        )
        # Override skills path
        config.skills_path = skills_dir
        
        curator = SkillCurator(config)
        actions = curator.run_lifecycle_transition()
        
        # Check transitions
        assert any("Marked skill 'stale-skill' as stale" in act for act in actions), "stale-skill was not flagged stale"
        assert any("Archived skill 'archived-skill'" in act for act in actions), "archived-skill was not moved to archived"
        
        # Verify files on disk
        assert (skills_dir / "active-skill" / "SKILL.md").exists(), "Active skill was incorrectly modified or moved"
        
        # Verify stale-skill content contains [stale] prefix
        stale_content = (skills_dir / "stale-skill" / "SKILL.md").read_text(encoding="utf-8")
        assert "name: '[stale] Stale Skill'" in stale_content or "name: [stale] Stale Skill" in stale_content, "Stale skill name not updated"
        
        # Verify archived-skill directory was moved
        assert not (skills_dir / "archived-skill").exists(), "Archived skill directory still exists in skills_path"
        assert (workspace_dir / "archived_skills" / "archived-skill").exists(), "Archived skill directory not found in archived_skills"
        
        print("  Skill Curator Lifecycle: OK")


# =====================================================================
# MAIN RUNNER
# =====================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  CYBERCLAW HERMES POWER-UPS INTEGRATION TEST SUITE")
    print("=" * 60)
    
    test_vsa_algebra()
    test_holographic_store_and_retrieval()
    test_context_guard_compression()
    asyncio.run(test_posix_shell_integration())
    test_skill_curator()
    
    print("=" * 60)
    print("  ALL HERMES POWER-UP INTEGRATION TESTS PASSED!")
    print("=" * 60)
