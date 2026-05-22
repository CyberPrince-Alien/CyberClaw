"""Test suite for the CyberClaw 3-pane TUI dashboard."""

import sys
from pathlib import Path

import pytest

# Add src directory to python path
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from cyberclaw.utils.config import Config
from cyberclaw.cli.tui import CyberClawTUI, _build_workspace_tree, _build_chat_panel, _build_telemetry_panel


@pytest.fixture
def config(tmp_path):
    """Create a minimal workspace config for testing."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    config_file = ws / "config.user.yaml"
    config_file.write_text(
        "llm:\n"
        "  default_provider: groq\n"
        "  providers:\n"
        "    - id: groq\n"
        "      provider: groq\n"
        "      model: llama-3.3-70b-versatile\n"
        "      api_key: test-key\n"
        "      enabled: true\n"
        "default_agent: default\n",
        encoding="utf-8",
    )
    return Config.load(ws)


def test_draw_dashboard_returns_layout(config):
    tui = CyberClawTUI(config)
    layout = tui.draw_dashboard()
    assert layout is not None


def test_layout_has_three_body_panes(config):
    tui = CyberClawTUI(config)
    layout = tui.draw_dashboard()
    assert layout["left"] is not None
    assert layout["center"] is not None
    assert layout["right"] is not None


def test_layout_has_header_and_footer(config):
    tui = CyberClawTUI(config)
    layout = tui.draw_dashboard()
    assert layout["header"] is not None
    assert layout["footer"] is not None


def test_workspace_tree_builder(config):
    tree = _build_workspace_tree(config.workspace, max_depth=1)
    assert tree is not None


def test_chat_panel_builder():
    panel = _build_chat_panel()
    assert panel is not None


def test_telemetry_panel_builder(config):
    panel = _build_telemetry_panel(config)
    assert panel is not None


def test_config_has_sandbox_field(config):
    assert hasattr(config, "sandbox")
    assert config.sandbox in ("danger-full-access", "docker", "workspace-write")
