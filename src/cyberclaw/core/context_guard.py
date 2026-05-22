"""Context guard for proactive context window management."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from litellm import token_counter
from litellm.types.completion import (
    ChatCompletionMessageParam as Message,
    ChatCompletionAssistantMessageParam,
    ChatCompletionToolMessageParam,
)

from cyberclaw.core.session_state import SessionState

if TYPE_CHECKING:
    from cyberclaw.core.context import SharedContext
    from cyberclaw.core.session_state import SessionState


# Default max size for tool result content before truncation
MAX_TOOL_RESULT_CHARS = 10000


@dataclass
class ContextGuard:
    """Manages context window size with proactive compaction."""

    shared_context: "SharedContext"
    token_threshold: int = 160000  # 80% of 200k context
    max_tool_result_chars: int = MAX_TOOL_RESULT_CHARS

    def estimate_tokens(self, state: "SessionState") -> int:
        """Estimate token count for session state."""
        if not state.messages:
            return 0
        return token_counter(
            model=state.agent.agent_def.llm.model, messages=state.build_messages()
        )

    async def check_and_compact(
        self,
        state: "SessionState",
    ) -> "SessionState":
        """Check token count, compact and roll session if needed."""
        # 1. Apply pre-compaction output pruning, deduplication, base64 stripping, and JSON truncation
        state.messages = self._prune_and_condense_messages(state.messages)
        
        token_count = self.estimate_tokens(state)

        if token_count < self.token_threshold:
            return state

        return await self.compact_and_roll(state)

    def _get_compaction_index(self, state: "SessionState") -> int:
        """Calculate the compaction boundary dynamically based on token budget.

        Keeps detailed turns at the tail end of the session that fit in budget.
        """
        messages = state.messages
        if not messages:
            return 0

        model = state.agent.agent_def.llm.model
        tail_budget = 12000  # safe token tail budget (detailed history size)

        cumulative_tokens = 0
        compact_index = 0

        for i in range(len(messages) - 1, -1, -1):
            try:
                msg_tokens = token_counter(model=model, messages=[messages[i]])
            except Exception:
                # Approximation fallback
                content_str = str(messages[i].get("content") or "")
                msg_tokens = len(content_str) // 4 + 10

            cumulative_tokens += msg_tokens
            if cumulative_tokens > tail_budget:
                compact_index = i + 1
                break

        # Keep at least 4 messages to preserve immediate conversation turn context
        min_keep = 4
        compact_index = min(compact_index, len(messages) - min_keep)
        compact_index = max(0, compact_index)

        return compact_index

    def _prune_and_condense_messages(self, messages: list[Message]) -> list[Message]:
        """Apply pre-compaction output pruning, deduplication, base64 stripping, and JSON truncation."""
        import json
        import re

        result: list[Message] = []
        tool_calls_map = {}

        # Scan for assistant tool calls, map their details, and truncate large payload parameters
        for msg in messages:
            msg_copy = dict(msg)
            if msg_copy.get("role") == "assistant" and "tool_calls" in msg_copy:
                tcs = msg_copy["tool_calls"]
                new_tcs = []
                for tc in tcs:
                    tc_copy = dict(tc)
                    tc_id = tc_copy.get("id")
                    fn = dict(tc_copy.get("function", {}))
                    name = fn.get("name")
                    args_str = fn.get("arguments", "{}")

                    if tc_id:
                        tool_calls_map[tc_id] = (name, args_str)

                    # Truncate large code/content arguments to prevent JSON syntax issues and token bloat
                    try:
                        args = json.loads(args_str)
                        changed = False
                        for key in ["content", "text", "new_text", "code"]:
                            if key in args and isinstance(args[key], str) and len(args[key]) > 2000:
                                original_len = len(args[key])
                                args[key] = args[key][:500] + f"\n... [Truncated {original_len - 1000} chars of code parameter] ...\n" + args[key][-500:]
                                changed = True
                        if changed:
                            fn["arguments"] = json.dumps(args)
                            tc_copy["function"] = fn
                    except Exception:
                        pass
                    new_tcs.append(tc_copy)
                msg_copy["tool_calls"] = new_tcs
            result.append(msg_copy)

        # Deduplicate identical file reads and condense outputs
        read_paths_seen = set()
        for i in range(len(result) - 1, -1, -1):
            msg = result[i]
            if msg.get("role") == "tool":
                tc_id = msg.get("tool_call_id")
                content = msg.get("content", "")
                if not isinstance(content, str):
                    continue

                tool_name = ""
                args_str = "{}"
                if tc_id in tool_calls_map:
                    tool_name, args_str = tool_calls_map[tc_id]

                # Check for duplicate file reads
                if tool_name in ["read", "read_file"]:
                    try:
                        args = json.loads(args_str)
                        path = args.get("path")
                        if path:
                            if path in read_paths_seen:
                                msg["content"] = f"[Duplicate tool output — same file '{path}' was re-read in a more recent turn]"
                                continue
                            else:
                                read_paths_seen.add(path)
                    except Exception:
                        pass

                # Condense tool response using regex rule engine
                if len(content) > self.max_tool_result_chars or tool_name in ["bash", "powershell", "read", "read_file"]:
                    msg["content"] = self._summarize_tool_result(tool_name, args_str, content)

        # Base64 image payload stripping in older messages (keep last 4 turns untouched)
        for i in range(len(result) - 4):
            msg = result[i]
            content = msg.get("content")
            if isinstance(content, list):
                new_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        img_url_dict = part.get("image_url", {})
                        url = img_url_dict.get("url", "")
                        if url.startswith("data:image/") and len(url) > 150:
                            part["image_url"]["url"] = "data:image/png;base64,[PRUNED_IMAGE_PAYLOAD]"
                    new_parts.append(part)
                msg["content"] = new_parts
            elif isinstance(content, str) and "data:image/" in content:
                msg["content"] = re.sub(
                    r"data:image/[a-zA-Z+]+;base64,[a-zA-Z0-9+/=]{100,}",
                    "data:image/png;base64,[PRUNED_IMAGE_PAYLOAD]",
                    content
                )

        return result

    def _summarize_tool_result(self, tool_name: str, args_str: str, content: str) -> str:
        """Create a condensed 1-line description of the tool result."""
        import json
        try:
            args = json.loads(args_str)
        except Exception:
            args = {}

        char_len = len(content)
        lines = content.splitlines()
        line_len = len(lines)

        if tool_name in ["bash", "powershell"]:
            cmd = args.get("command", "shell command")
            if len(cmd) > 60:
                cmd = cmd[:57] + "..."
            return f"[shell] ran '{cmd}' -> {line_len} lines output ({char_len} chars)"

        elif tool_name in ["read", "read_file"]:
            path = args.get("path", "file")
            offset = args.get("offset", 1)
            limit = args.get("limit")
            limit_str = f" lines {offset} to {offset + limit - 1}" if limit else ""
            return f"[read_file] read {path}{limit_str} -> {line_len} lines ({char_len} chars)"

        elif tool_name in ["write", "write_file"]:
            path = args.get("path", "file")
            return f"[write_file] wrote to {path}"

        elif tool_name in ["edit", "edit_file"]:
            path = args.get("path", "file")
            return f"[edit_file] edited {path}"

        elif tool_name in ["websearch", "websearch_tool"]:
            q = args.get("query", "")
            return f"[websearch] searched for '{q}' -> {line_len} lines of results ({char_len} chars)"

        # Fallback standard truncation
        if char_len > self.max_tool_result_chars:
            truncated = content[:self.max_tool_result_chars]
            return f"{truncated}\n\n[Truncated - original size: {char_len} chars]"

        return content

    def _serialize_messages_for_summary(self, messages: list[Message]) -> str:
        """Serialize messages to plain text for summarization."""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "assistant" and msg.get("tool_calls"):
                tool_names = [
                    tc.get("function", {}).get("name", "unknown")
                    for tc in (cast(ChatCompletionAssistantMessageParam, msg)).get(
                        "tool_calls", []
                    )
                ]
                lines.append(
                    f"ASSISTANT: [used tools: {', '.join(tool_names)}] {content}"
                )
            else:
                lines.append(f"{role.upper()}: {content}")
        return "\n".join(lines)

    async def compact_and_roll(
        self,
        state: "SessionState",
    ) -> "SessionState":
        """Compact history, roll to new session, return new messages."""
        new_session = state.agent.new_session(state.source)
        self.shared_context.routing_table.config_source_session_cache(
            str(state.source), new_session.session_id
        )

        compacted_history = await self._build_compacted_messages(state)
        for message in compacted_history:
            new_session.state.add_message(message)

        return new_session.state

    async def _build_compacted_messages(
        self,
        state: "SessionState",
    ) -> list[Message]:
        """Generate summary of older messages using agent's LLM."""
        compress_count = self._get_compaction_index(state)

        if compress_count <= 0:
            return state.messages

        old_messages = state.messages[:compress_count]
        old_text = self._serialize_messages_for_summary(old_messages)

        summary_prompt = f"""Summarize the conversation so far. Keep it factual and concise. Focus on key decisions, facts, and user preferences discovered:

{old_text}"""

        response, _ = await state.agent.llm.chat(
            [{"role": "user", "content": summary_prompt}],
            [],
        )

        messages: list[Message] = []
        messages.append(
            {
                "role": "user",
                "content": f"[Previous conversation summary]\n{response}",
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": "Understood, I have the context.",
            }
        )
        messages.extend(state.messages[compress_count:])
        return messages
