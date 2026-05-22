"""Test suite for CyberClaw holographic memory store."""

import sys
from pathlib import Path

import pytest

src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from cyberclaw.core.holographic.store import HolographicStore


@pytest.fixture
def store(tmp_path):
    """Create a temporary holographic store for testing."""
    db = tmp_path / "test_memory.db"
    s = HolographicStore(db)
    yield s
    s.close()


def test_add_fact(store):
    fid = store.add_fact("Python uses indentation for blocks", category="programming")
    assert fid > 0


def test_duplicate_fact_no_crash(store):
    """Adding the same fact twice should update, not crash with FOREIGN KEY error."""
    fid1 = store.add_fact("FastAPI runs on port 8000", category="backend")
    fid2 = store.add_fact("FastAPI runs on port 8000", category="backend", trust_score=0.9)
    assert fid1 > 0
    assert fid2 > 0


def test_entity_extraction(store):
    entities = store.extract_entities("The FastAPI backend uses Python and SQLite")
    assert "FastAPI" in entities
    assert "Python" in entities
    assert "SQLite" in entities


def test_category_bank_rebuild(store):
    store.add_fact("Fact one about databases", category="db")
    store.add_fact("Fact two about databases", category="db")
    bank = store.get_category_bank("db")
    assert bank is not None


def test_delete_fact(store):
    fid = store.add_fact("Temporary fact", category="temp")
    result = store.delete_fact(fid)
    assert result is True
    assert store.get_fact(fid) is None
