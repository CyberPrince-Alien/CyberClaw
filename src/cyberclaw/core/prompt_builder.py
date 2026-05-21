"""Prompt builder that assembles system prompt from layers."""

from datetime import datetime
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from cyberclaw.core.context import SharedContext
    from cyberclaw.core.events import EventSource
    from cyberclaw.core.session_state import SessionState


class PromptBuilder:
    """Assembles system prompt from layered sources."""

    def __init__(self, context: "SharedContext"):
        self.context = context

    def build(self, state: "SessionState") -> str:
        """Build the full system prompt from layers."""
        layers = []

        # Layer 1: Identity
        layers.append(state.agent.agent_def.agent_md)

        # Layer 2: Soul (optional)
        if state.agent.agent_def.soul_md:
            layers.append(f"## Personality\n\n{state.agent.agent_def.soul_md}")

        # Layer 3: Bootstrap context
        bootstrap = self._load_bootstrap_context()
        if bootstrap:
            layers.append(bootstrap)

        # Layer 4: Runtime context
        layers.append(
            self._build_runtime_context(
                state.agent.agent_def.id,
                datetime.now(),
            )
        )

        # Layer 5: Channel hint
        layers.append(self._build_channel_hint(state.source))

        return "\n\n".join(layers)

    def _load_bootstrap_context(self) -> str:
        """Load BOOTSTRAP.md + AGENTS.md + cron list."""
        parts = []

        bootstrap_path = self.context.config.workspace / "BOOTSTRAP.md"
        if bootstrap_path.exists():
            parts.append(bootstrap_path.read_text().strip())

        agents_path = self.context.config.workspace / "AGENTS.md"
        if agents_path.exists():
            parts.append(agents_path.read_text().strip())

        # Dynamic cron list
        cron_list = self._format_cron_list()
        if cron_list:
            parts.append(cron_list)

        return "\n\n".join(parts)

    def _format_cron_list(self) -> str:
        """Format crons as markdown list."""
        crons = self.context.cron_loader.discover_crons()
        if not crons:
            return ""

        lines = ["## Scheduled Tasks\n"]
        for cron in crons:
            lines.append(f"- **{cron.name}**: {cron.description}")
        return "\n".join(lines)

    def _build_runtime_context(self, agent_id: str, timestamp: datetime) -> str:
        """Build runtime info section."""
        import platform
        os_info = f"{platform.system()} {platform.release()}"
        return f"## Runtime\n\nAgent: {agent_id}\nTime: {timestamp.isoformat()}\nOS: {os_info}"

    def _build_channel_hint(self, source: "EventSource") -> str:
        """Build platform hint."""
        if source.is_cron:
            return "You are running as a background cron job. Your response will not be sent to user directly."
        if source.is_agent:
            return "You are running as a dispatched subagent. Your response will be sent to main agent."
        elif source.is_platform:
            return f"You are responding via {source.platform_name}."
        else:
            raise ValueError(f"Unknown source type: {source}")
