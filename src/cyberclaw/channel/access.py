"""Channel access control and pairing support."""

import json
import secrets
import time
from pathlib import Path
from typing import Any

from cyberclaw.core.events import EventSource
from cyberclaw.utils.config import Config


class ChannelAccessManager:
    """Manages CyberClaw-secure channel allowlists and pairing codes."""

    def __init__(self, config: Config):
        self.config = config
        self.path = config.workspace / ".pairings.json"

    def is_allowed(self, platform: str, source: EventSource) -> bool:
        """Return whether an inbound source may be processed."""
        channel_config = self._channel_config(platform)
        policy = getattr(channel_config, "dm_policy", "open")
        allow_from = set(getattr(channel_config, "allow_from", []) or [])
        allowed_user_ids = set(getattr(channel_config, "allowed_user_ids", []) or [])
        source_str = str(source)
        user_id = getattr(source, "user_id", None)

        if policy == "open" or "*" in allow_from:
            return True
        if source_str in allow_from or (user_id and user_id in allow_from):
            return True
        if user_id and user_id in allowed_user_ids:
            return True
        if source_str in self._load().get("approved", {}).get(platform, []):
            return True

        return False

    def requires_pairing(self, platform: str) -> bool:
        """Return whether the platform should create pairing challenges."""
        channel_config = self._channel_config(platform)
        return getattr(channel_config, "dm_policy", "open") == "pairing"

    def get_or_create_code(self, platform: str, source: EventSource) -> str:
        """Create or reuse a short pairing code for a source."""
        source_str = str(source)
        data = self._load()
        pending: dict[str, dict[str, Any]] = data.setdefault("pending", {})

        for code, record in pending.items():
            if record.get("platform") == platform and record.get("source") == source_str:
                return code

        code = self._new_code(pending)
        pending[code] = {
            "platform": platform,
            "source": source_str,
            "created_at": time.time(),
        }
        self._save(data)
        return code

    def approve(self, platform: str, code: str) -> str:
        """Approve a pending pairing code and return the approved source."""
        normalized_code = code.strip().upper()
        data = self._load()
        pending: dict[str, dict[str, Any]] = data.setdefault("pending", {})
        record = pending.get(normalized_code)

        if not record or record.get("platform") != platform:
            raise ValueError(f"No pending {platform} pairing for code {normalized_code}")

        source = str(record["source"])
        approved = data.setdefault("approved", {}).setdefault(platform, [])
        if source not in approved:
            approved.append(source)

        del pending[normalized_code]
        self._save(data)
        return source

    def list_pairings(self) -> dict[str, Any]:
        """Return the raw pairing state for status commands."""
        return self._load()

    def _channel_config(self, platform: str) -> Any:
        channel_config = getattr(self.config.channels, platform, None)
        if channel_config is None:
            raise ValueError(f"Channel `{platform}` is not configured")
        return channel_config

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"pending": {}, "approved": {}}
        try:
            return json.loads(self.path.read_text())
        except json.JSONDecodeError:
            return {"pending": {}, "approved": {}}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True))

    @staticmethod
    def _new_code(pending: dict[str, Any]) -> str:
        while True:
            code = secrets.token_hex(3).upper()
            if code not in pending:
                return code
