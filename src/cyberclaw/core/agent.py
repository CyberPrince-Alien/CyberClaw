import uuid
import json
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, AsyncIterator

from cyberclaw.core.context_guard import ContextGuard
from cyberclaw.core.session_state import SessionState
from cyberclaw.core.events import EventSource
from cyberclaw.provider.llm import LLMProvider, MultiLLMProvider
from cyberclaw.tools.registry import ToolRegistry
from cyberclaw.tools.skill_tool import create_skill_tool
from cyberclaw.tools.websearch_tool import create_websearch_tool
from cyberclaw.tools.webread_tool import create_webread_tool
from cyberclaw.tools.post_message_tool import create_post_message_tool
from cyberclaw.tools.subagent_tool import create_subagent_dispatch_tool

from litellm.types.completion import (
    ChatCompletionMessageParam as Message,
    ChatCompletionMessageToolCallParam,
)
from cyberclaw.core.streaming import StreamChunk, ChunkType

if TYPE_CHECKING:
    from cyberclaw.core.context import SharedContext
    from cyberclaw.core.agent_loader import AgentDef
    from cyberclaw.provider.llm import LLMToolCall


class Agent:
    """A configured agent that creates and manages conversation sessions."""

    def __init__(self, agent_def: "AgentDef", context: "SharedContext") -> None:
        self.agent_def = agent_def
        self.context = context
        self.llm = MultiLLMProvider(agent_def.llm)

    def _build_tools(self, include_post_message: bool) -> ToolRegistry:
        """Build a ToolRegistry with tools appropriate for the session."""
        registry = ToolRegistry.with_builtins()

        # Register skill tool if allowed
        if self.agent_def.allow_skills:
            skill_tool = create_skill_tool(self.context.skill_loader)
            if skill_tool:
                registry.register(skill_tool)

        websearch_tool = create_websearch_tool(self.context)
        if websearch_tool:
            registry.register(websearch_tool)

        webread_tool = create_webread_tool(self.context)
        if webread_tool:
            registry.register(webread_tool)

        if include_post_message:
            post_tool = create_post_message_tool(self.context)
            if post_tool:
                registry.register(post_tool)

        # Register subagent dispatch tool
        subagent_tool = create_subagent_dispatch_tool(
            self.agent_def.id, self.context
        )
        if subagent_tool:
            registry.register(subagent_tool)

        return registry

    def _get_token_threshold(self) -> int:
        """Get token threshold based on actual model context window."""
        try:
            info = self.llm.get_model_info()
            return info.safe_token_threshold
        except Exception:
            return 160000  # fallback

    def new_session(
        self,
        source: EventSource,
        session_id: str | None = None,
    ) -> "AgentSession":
        """Create a new conversation session."""
        session_id = session_id or str(uuid.uuid4())

        include_post_message = source.is_cron
        tools = self._build_tools(include_post_message)

        # Create context guard for this session
        context_guard = ContextGuard(
            shared_context=self.context,
            token_threshold=self._get_token_threshold(),
        )

        state = SessionState(
            session_id=session_id,
            agent=self,
            messages=[],
            source=source,
            shared_context=self.context,
        )

        session = AgentSession(
            agent=self,
            state=state,
            context_guard=context_guard,
            tools=tools,
        )

        self.context.history_store.create_session(
            self.agent_def.id, session_id, source
        )
        return session

    def resume_session(self, session_id: str) -> "AgentSession":
        """Load an existing conversation session."""
        session_query = [
            session
            for session in self.context.history_store.list_sessions()
            if session.id == session_id
        ]
        if not session_query:
            raise ValueError(f"Session not found: {session_id}")

        session_info = session_query[0]
        source = session_info.get_source()
        include_post_message = source.is_cron

        # Get all messages (no max_history limit)
        history_messages = self.context.history_store.get_messages(session_id)

        # Convert HistoryMessage to litellm Message format
        messages: list[Message] = [msg.to_message() for msg in history_messages]

        # Build tools for resumed session
        tools = self._build_tools(include_post_message)

        # Create context guard
        context_guard = ContextGuard(
            shared_context=self.context,
            token_threshold=self._get_token_threshold(),
        )

        # Create SessionState with loaded messages
        state = SessionState(
            session_id=session_info.id,
            agent=self,
            messages=messages,
            source=source,
            shared_context=self.context,
        )

        return AgentSession(
            agent=self,
            state=state,
            context_guard=context_guard,
            tools=tools,
        )


@dataclass
class AgentSession:
    """Chat orchestrator - operates on swappable SessionState."""

    agent: Agent
    state: SessionState
    context_guard: ContextGuard
    tools: ToolRegistry
    started_at: datetime = field(default_factory=datetime.now)

    @property
    def session_id(self) -> str:
        """Delegate to state."""
        return self.state.session_id

    @property
    def source(self) -> "EventSource":
        return self.state.source

    @property
    def shared_context(self) -> "SharedContext":
        """Delegate to state."""
        return self.state.shared_context

    async def chat(self, message: str) -> str:
        """Send a message to the LLM and get a response."""
        user_msg: Message = {"role": "user", "content": message}
        self.state.add_message(user_msg)

        tool_schemas = self.tools.get_tool_schemas()

        while True:
            messages = self.state.build_messages()
            self.state = await self.context_guard.check_and_compact(self.state)
            try:
                content, tool_calls = await self.agent.llm.chat(messages, tool_schemas)
            except Exception:
                if not tool_schemas:
                    raise
                content, tool_calls = await self.agent.llm.chat(messages, None)

            tool_call_dicts: list[ChatCompletionMessageToolCallParam] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in tool_calls
            ]
            assistant_msg: Message = {
                "role": "assistant",
                "content": content,
            }
            if tool_call_dicts:
                assistant_msg["tool_calls"] = tool_call_dicts

            self.state.add_message(assistant_msg)

            if not tool_calls:
                break

            await self._handle_tool_calls(tool_calls)

            continue

        return content

    async def chat_stream(self, message: str) -> AsyncIterator[StreamChunk]:
        """Send a message and stream the response tokens."""
        user_msg: Message = {"role": "user", "content": message}
        self.state.add_message(user_msg)

        tool_schemas = self.tools.get_tool_schemas()
        messages = self.state.build_messages()
        self.state = await self.context_guard.check_and_compact(self.state)

        collected_content = ""
        collected_tool_calls: list["LLMToolCall"] = []

        async for chunk in self.agent.llm.chat_stream(messages, tool_schemas):
            if chunk.type == ChunkType.TOKEN:
                collected_content += chunk.content
                yield chunk
            elif chunk.type == ChunkType.TOOL_START:
                collected_tool_calls.append(
                    LLMToolCall(
                        id=chunk.tool_call_id or "",
                        name=chunk.tool_name or "",
                        arguments=chunk.tool_args or "{}",
                    )
                )
                yield chunk
            elif chunk.type == ChunkType.ERROR:
                yield chunk
                return
            elif chunk.type == ChunkType.DONE:
                pass  # Handle below

        # Record assistant message
        tool_call_dicts: list[ChatCompletionMessageToolCallParam] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": tc.arguments},
            }
            for tc in collected_tool_calls
        ]
        assistant_msg: Message = {"role": "assistant", "content": collected_content}
        if tool_call_dicts:
            assistant_msg["tool_calls"] = tool_call_dicts
        self.state.add_message(assistant_msg)

        # If there were tool calls, execute them and do another round (non-streaming)
        if collected_tool_calls:
            await self._handle_tool_calls(collected_tool_calls)
            # Do a non-streaming follow-up for the tool results
            followup = await self.chat(".")
            yield StreamChunk(type=ChunkType.TOKEN, content=followup)

        yield StreamChunk(type=ChunkType.DONE)

    async def _handle_tool_calls(
        self,
        tool_calls: list["LLMToolCall"],
    ) -> None:
        """Handle tool calls from the LLM response."""
        tool_call_results = await asyncio.gather(
            *[self._execute_tool_call(tool_call) for tool_call in tool_calls]
        )

        for tool_call, result in zip(tool_calls, tool_call_results):
            tool_msg: Message = {
                "role": "tool",
                "content": result,
                "tool_call_id": tool_call.id,
            }
            self.state.add_message(tool_msg)

    async def _execute_tool_call(
        self,
        tool_call: "LLMToolCall",
    ) -> str:
        """Execute a single tool call."""
        try:
            args = json.loads(tool_call.arguments)
        except json.JSONDecodeError:
            args = {}

        try:
            result = await self.tools.execute_tool(tool_call.name, session=self, **args)
        except Exception as e:
            result = f"Error executing tool: {e}"

        return result
