"""Unit tests for robust error handling in CLI ChatLoop and DeliveryWorker."""

import sys
from pathlib import Path
import pytest
from unittest.mock import MagicMock, AsyncMock

# Add src directory to python path
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from cyberclaw.core.events import OutboundEvent, CliEventSource, AgentEventSource
from cyberclaw.cli.chat import ChatLoop
from cyberclaw.server.delivery_worker import DeliveryWorker
from cyberclaw.utils.config import Config


@pytest.fixture
def config(tmp_path):
    """Create a minimal workspace config for testing."""
    ws = tmp_path / "workspace"
    ws.mkdir()

    # Create default agent definition files so ChatLoop can load it
    agents_dir = ws / "agents" / "default"
    agents_dir.mkdir(parents=True)
    agent_file = agents_dir / "AGENT.md"
    agent_file.write_text(
        "---\n"
        "name: default\n"
        "description: Default Agent\n"
        "---\n"
        "# Default Agent\n"
        "This is a default test agent.\n",
        encoding="utf-8"
    )

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


def test_chat_loop_display_agent_response_with_error(config):
    """Test displaying error when content is empty."""
    chat_loop = ChatLoop(config)
    chat_loop.console = MagicMock()
    chat_loop.display_agent_response = MagicMock()

    # Event has error and empty content
    event_error = OutboundEvent(
        session_id="sess-1",
        source=AgentEventSource(agent_id="cyberclaw"),
        content="",
        error="Quota exceeded for Gemini API",
    )

    chat_loop.handle_response_display(event_error)

    # Assert display_agent_response was called with the styled error
    chat_loop.display_agent_response.assert_called_once_with(
        "[bold red]Error: Quota exceeded for Gemini API[/bold red]"
    )


def test_chat_loop_display_agent_response_with_error_and_content(config):
    """Test displaying partial content followed by the error message."""
    chat_loop = ChatLoop(config)
    chat_loop.console = MagicMock()
    chat_loop.display_agent_response = MagicMock()

    # Event has error AND content
    event_error_content = OutboundEvent(
        session_id="sess-1",
        source=AgentEventSource(agent_id="cyberclaw"),
        content="Some partial output...",
        error="Connection lost mid-stream",
    )

    chat_loop.handle_response_display(event_error_content)

    # Asserts
    chat_loop.display_agent_response.assert_called_once_with("Some partial output...")
    chat_loop.console.print.assert_called_once_with(
        "[bold red]Error: Connection lost mid-stream[/bold red]"
    )


def test_chat_loop_display_agent_response_empty_no_error(config):
    """Test displaying placeholder message when response content is empty/whitespace-only with no error."""
    chat_loop = ChatLoop(config)
    chat_loop.console = MagicMock()
    chat_loop.display_agent_response = MagicMock()

    # Event has no error, but content is empty
    event_empty = OutboundEvent(
        session_id="sess-1",
        source=AgentEventSource(agent_id="cyberclaw"),
        content="   ",
        error=None,
    )

    chat_loop.handle_response_display(event_empty)

    # Asserts
    chat_loop.display_agent_response.assert_called_once_with(
        "[dim italic]Received empty response from agent[/dim italic]"
    )


@pytest.mark.asyncio
async def test_delivery_worker_handles_empty_content_with_error(config):
    """Test that DeliveryWorker delivers a friendly error message when response content is empty but error is present."""
    from cyberclaw.core.context import SharedContext
    context = SharedContext(config, [])

    worker = DeliveryWorker(context)
    worker.logger = MagicMock()

    # Mock context methods and classes
    mock_session = MagicMock()
    mock_source = MagicMock()
    mock_source.platform_name = "telegram"
    mock_session.source = mock_source
    mock_session.get_source.return_value = mock_source
    worker._get_session_source = MagicMock(return_value=mock_session)
    worker._get_delivery_source = MagicMock(return_value=mock_source)

    mock_channel = AsyncMock()
    mock_channel.platform_name = "telegram"
    worker._get_channel = MagicMock(return_value=mock_channel)

    # Create event with error and empty content
    event = OutboundEvent(
        session_id="sess-1",
        source=AgentEventSource(agent_id="cyberclaw"),
        content="",
        error="LiteLLM quota exceeded",
    )

    await worker.handle_event(event)

    # Ensure channel.reply was called with the decorated error message
    mock_channel.reply.assert_called_once_with(
        "⚠️ CyberClaw Error: LiteLLM quota exceeded", mock_source
    )
