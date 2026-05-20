"""Security subsystem — auth, audit, secrets."""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AuditLogger:
    """Audit log for security-sensitive actions."""

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self.log_dir / "audit.jsonl"

    def log(self, action: str, actor: str, details: dict[str, Any] | None = None) -> None:
        entry = {
            "timestamp": time.time(),
            "action": action,
            "actor": actor,
            "details": details or {},
        }
        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_recent(self, count: int = 50) -> list[dict[str, Any]]:
        if not self._log_file.exists():
            return []
        lines = self._log_file.read_text(encoding="utf-8").strip().split("\n")
        entries = []
        for line in lines[-count:]:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries


class GatewayAuth:
    """Simple token-based auth for the gateway API."""

    def __init__(self, tokens: list[str] | None = None):
        self._token_hashes: set[str] = set()
        if tokens:
            for token in tokens:
                self._token_hashes.add(self._hash(token))

    @property
    def enabled(self) -> bool:
        return len(self._token_hashes) > 0

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def validate(self, token: str) -> bool:
        if not self.enabled:
            return True  # No auth configured
        return self._hash(token) in self._token_hashes

    def add_token(self, token: str) -> None:
        self._token_hashes.add(self._hash(token))

    def revoke_token(self, token: str) -> None:
        self._token_hashes.discard(self._hash(token))


class PairingStore:
    """Manages DM pairing codes for channel access control."""

    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.store_path.mkdir(parents=True, exist_ok=True)
        self._pending_file = store_path / "pending.json"
        self._approved_file = store_path / "approved.json"

    def _load(self, path: Path) -> dict[str, Any]:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def _save(self, path: Path, data: dict[str, Any]) -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def generate_code(self, channel: str, sender_id: str) -> str:
        """Generate a pairing code for a new sender."""
        import secrets
        code = secrets.token_hex(3).upper()  # 6-char hex code
        pending = self._load(self._pending_file)
        pending[f"{channel}:{sender_id}"] = {
            "code": code,
            "channel": channel,
            "sender_id": sender_id,
            "created_at": time.time(),
        }
        self._save(self._pending_file, pending)
        return code

    def approve(self, channel: str, code: str) -> str | None:
        """Approve a pairing code. Returns sender_id if found, None otherwise."""
        pending = self._load(self._pending_file)
        approved = self._load(self._approved_file)

        for key, entry in list(pending.items()):
            if entry["channel"] == channel and entry["code"] == code:
                sender_id = entry["sender_id"]
                approved[key] = {
                    "channel": channel,
                    "sender_id": sender_id,
                    "approved_at": time.time(),
                }
                del pending[key]
                self._save(self._pending_file, pending)
                self._save(self._approved_file, approved)
                return sender_id
        return None

    def is_approved(self, channel: str, sender_id: str) -> bool:
        approved = self._load(self._approved_file)
        return f"{channel}:{sender_id}" in approved

    def revoke(self, channel: str, sender_id: str) -> bool:
        approved = self._load(self._approved_file)
        key = f"{channel}:{sender_id}"
        if key in approved:
            del approved[key]
            self._save(self._approved_file, approved)
            return True
        return False

    def list_pending(self) -> list[dict[str, Any]]:
        return list(self._load(self._pending_file).values())

    def list_approved(self) -> list[dict[str, Any]]:
        return list(self._load(self._approved_file).values())
