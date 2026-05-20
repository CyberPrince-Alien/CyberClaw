#!/usr/bin/env python3
"""Regression checks for CyberClaw operator features."""

from pathlib import Path
import tempfile

from cyberclaw.channel.access import ChannelAccessManager
from cyberclaw.channel.telegram_channel import TelegramEventSource
from cyberclaw.core.context import SharedContext
from cyberclaw.server.app import _redact_config
from cyberclaw.utils.config import Config, LLMConfig, TelegramConfig


def check_legacy_llm_config() -> None:
    config = LLMConfig(
        provider="openai",
        model="gpt-4",
        api_key="sk-test",
    )
    assert len(config.providers) == 1
    assert config.providers[0].id == "openai"
    assert config.providers[0].model == "gpt-4"


def check_redaction() -> None:
    redacted = _redact_config(
        {
            "api_key": "secret",
            "nested": {"bot_token": "token", "safe": "value"},
            "items": [{"secret_value": "hidden"}],
        }
    )
    assert redacted["api_key"] == "***REDACTED***"
    assert redacted["nested"]["bot_token"] == "***REDACTED***"
    assert redacted["nested"]["safe"] == "value"
    assert redacted["items"][0]["secret_value"] == "***REDACTED***"


def check_pairing_flow() -> None:
    cfg = Config.load(Path("workspace"))
    cfg.channels.telegram = TelegramConfig(
        enabled=True, bot_token="test", dm_policy="pairing"
    )
    source = TelegramEventSource(user_id="100", chat_id="200")

    with tempfile.TemporaryDirectory() as temp_dir:
        manager = ChannelAccessManager(cfg)
        manager.path = Path(temp_dir) / "pairings.json"
        assert manager.is_allowed("telegram", source) is False
        code = manager.get_or_create_code("telegram", source)
        assert len(code) == 6
        assert manager.approve("telegram", code) == str(source)
        assert manager.is_allowed("telegram", source) is True


def check_command_registry() -> None:
    cfg = Config.load(Path("workspace"))
    context = SharedContext(cfg, [])
    commands = {command.name for command in context.command_registry.list_commands()}
    assert "pairing" in commands


def main() -> int:
    checks = [
        check_legacy_llm_config,
        check_redaction,
        check_pairing_flow,
        check_command_registry,
    ]
    for check in checks:
        check()
        print(f"PASS {check.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
