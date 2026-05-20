"""Encrypted secrets store for API keys and tokens.

Uses Fernet symmetric encryption (from cryptography library) with a
machine-specific key derived from OS details + a user passphrase.
Falls back to base64 obfuscation if cryptography is not installed.
"""

import base64
import hashlib
import json
import logging
import os
import platform
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_machine_fingerprint() -> bytes:
    """Generate a deterministic fingerprint from machine-specific data."""
    parts = [
        platform.node(),
        platform.machine(),
        platform.processor(),
        os.environ.get("USERNAME", os.environ.get("USER", "")),
        os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", "")),
    ]
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).digest()


def _derive_key(passphrase: str = "") -> bytes:
    """Derive a 32-byte encryption key from machine fingerprint + passphrase."""
    fingerprint = _get_machine_fingerprint()
    combined = fingerprint + passphrase.encode("utf-8")
    # Use PBKDF2-like stretching
    key = hashlib.pbkdf2_hmac("sha256", combined, b"cyberclaw-salt-v1", 100_000)
    return base64.urlsafe_b64encode(key)


class SecretsStore:
    """Encrypted key-value store for sensitive configuration.

    Stores secrets in a local JSON file with values encrypted using
    machine-specific key derivation.
    """

    def __init__(self, store_path: Path, passphrase: str = ""):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._key = _derive_key(passphrase)
        self._fernet = None
        self._use_fernet = False

        try:
            from cryptography.fernet import Fernet
            self._fernet = Fernet(self._key)
            self._use_fernet = True
        except ImportError:
            logger.warning(
                "cryptography library not installed. "
                "Using base64 obfuscation (not secure). "
                "Install: pip install cryptography"
            )

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt a string."""
        if self._use_fernet and self._fernet:
            return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
        # Fallback: base64 obfuscation (not secure, but better than plaintext)
        return "b64:" + base64.b64encode(plaintext.encode("utf-8")).decode("ascii")

    def _decrypt(self, ciphertext: str) -> str:
        """Decrypt a string."""
        if ciphertext.startswith("b64:"):
            return base64.b64decode(ciphertext[4:]).decode("utf-8")
        if self._use_fernet and self._fernet:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        raise ValueError("Cannot decrypt: cryptography library not available")

    def _load(self) -> dict[str, str]:
        """Load the encrypted store."""
        if not self.store_path.exists():
            return {}
        try:
            return json.loads(self.store_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return {}

    def _save(self, data: dict[str, str]) -> None:
        """Save the encrypted store."""
        self.store_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def set(self, key: str, value: str) -> None:
        """Store an encrypted secret."""
        data = self._load()
        data[key] = self._encrypt(value)
        self._save(data)
        logger.info("Secret stored: %s", key)

    def get(self, key: str) -> str | None:
        """Retrieve and decrypt a secret."""
        data = self._load()
        encrypted = data.get(key)
        if encrypted is None:
            return None
        try:
            return self._decrypt(encrypted)
        except Exception as e:
            logger.error("Failed to decrypt secret %s: %s", key, e)
            return None

    def delete(self, key: str) -> bool:
        """Delete a secret."""
        data = self._load()
        if key in data:
            del data[key]
            self._save(data)
            return True
        return False

    def list_keys(self) -> list[str]:
        """List all stored secret keys (not values)."""
        return list(self._load().keys())

    def has(self, key: str) -> bool:
        """Check if a secret exists."""
        return key in self._load()

    def import_from_config(self, config_data: dict[str, Any]) -> int:
        """Import API keys from a config dict and encrypt them.

        Scans for keys with 'api_key', 'token', 'secret' in the name.
        """
        count = 0
        self._scan_and_import(config_data, "", count_ref=[0])
        return count_ref[0] if hasattr(self, '_count') else self._import_recursive(config_data)

    def _import_recursive(self, data: Any, prefix: str = "") -> int:
        """Recursively scan and import sensitive values."""
        count = 0
        if isinstance(data, dict):
            for key, value in data.items():
                full_key = f"{prefix}.{key}" if prefix else key
                lowered = key.lower()
                if isinstance(value, str) and value and any(
                    marker in lowered
                    for marker in ("api_key", "token", "secret", "password")
                ):
                    # Don't import placeholders
                    if not any(p in value for p in ("your-", "here", "xxx")):
                        self.set(full_key, value)
                        count += 1
                elif isinstance(value, (dict, list)):
                    count += self._import_recursive(value, full_key)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                count += self._import_recursive(item, f"{prefix}[{i}]")
        return count

    def export_redacted(self) -> dict[str, str]:
        """Export all keys with redacted values (for display)."""
        data = self._load()
        return {
            key: "***" + self._decrypt(val)[-4:] if len(self._decrypt(val)) > 4 else "****"
            for key, val in data.items()
        }
