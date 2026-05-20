"""Configuration management with hot reload support."""

import logging
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class LLMProviderConfig(BaseModel):
    """Individual LLM provider configuration."""

    id: str
    provider: str
    model: str
    api_key: str
    api_base: str | None = None
    priority: int = Field(default=1, ge=1)
    enabled: bool = True


class LLMConfig(BaseModel):
    """LLM provider configuration with multi-provider support."""

    default_provider: str = "openai"
    providers: list[LLMProviderConfig] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, gt=0)
    enable_failover: bool = True

    @model_validator(mode="after")
    def normalize_legacy_provider(self) -> "LLMConfig":
        """Convert the original single-provider shape into providers[]."""
        if not self.providers and self.model and self.api_key:
            provider_id = self.provider or self.default_provider
            self.providers = [
                LLMProviderConfig(
                    id=provider_id,
                    provider=provider_id,
                    model=self.model,
                    api_key=self.api_key,
                    api_base=self.api_base,
                    priority=1,
                    enabled=True,
                )
            ]
        return self


class TelegramConfig(BaseModel):
    """Telegram platform configuration."""

    enabled: bool = True
    bot_token: str
    allowed_user_ids: list[str] = Field(default_factory=list)
    dm_policy: Literal["pairing", "allowlist", "open"] = "pairing"
    allow_from: list[str] = Field(default_factory=list)


class DiscordConfig(BaseModel):
    """Discord platform configuration."""

    enabled: bool = True
    bot_token: str
    channel_id: str | None = None
    allowed_user_ids: list[str] = Field(default_factory=list)
    dm_policy: Literal["pairing", "allowlist", "open"] = "pairing"
    allow_from: list[str] = Field(default_factory=list)


class SlackConfig(BaseModel):
    """Slack platform configuration."""

    enabled: bool = True
    bot_token: str
    app_token: str = ""
    allowed_channels: list[str] = Field(default_factory=list)
    dm_policy: Literal["pairing", "allowlist", "open"] = "pairing"
    allow_from: list[str] = Field(default_factory=list)


class WhatsAppConfig(BaseModel):
    """WhatsApp Business API configuration."""

    enabled: bool = True
    phone_number_id: str
    access_token: str
    verify_token: str = "cyberclaw-verify"
    allow_from: list[str] = Field(default_factory=list)
    dm_policy: Literal["pairing", "allowlist", "open"] = "pairing"


class MatrixConfig(BaseModel):
    """Matrix platform configuration."""

    enabled: bool = True
    homeserver: str
    user_id: str
    access_token: str
    allowed_rooms: list[str] = Field(default_factory=list)
    allow_from: list[str] = Field(default_factory=list)


class IRCConfig(BaseModel):
    """IRC platform configuration."""

    enabled: bool = True
    server: str
    port: int = 6667
    nick: str = "CyberClaw"
    channels: list[str] = Field(default_factory=list)
    use_ssl: bool = False
    allow_from: list[str] = Field(default_factory=list)


class WebChatConfig(BaseModel):
    """Built-in WebChat configuration."""

    enabled: bool = True


class TTSConfig(BaseModel):
    """Text-to-Speech configuration."""

    enabled: bool = False
    provider: str = "edge-tts"
    api_key: str | None = None
    voice: str = "en-US-AriaNeural"
    voice_id: str | None = None


class STTConfig(BaseModel):
    """Speech-to-Text configuration."""

    enabled: bool = False
    provider: str = "whisper"
    api_key: str | None = None
    model: str = "whisper-1"


class SecurityConfig(BaseModel):
    """Security configuration."""

    gateway_tokens: list[str] = Field(default_factory=list)
    audit_enabled: bool = True
    pairing_enabled: bool = True


class MCPServerConfig(BaseModel):
    """External MCP server to connect to."""

    name: str
    command: list[str]


class BraveWebSearchConfig(BaseModel):
    """Configuration for web search provider."""

    provider: Literal["brave"] = "brave"
    api_key: str


class Crawl4AIWebReadConfig(BaseModel):
    """Configuration for web read provider."""

    provider: Literal["crawl4ai"] = "crawl4ai"


class SourceSessionConfig(BaseModel):
    """Session affinity configuration for a source."""

    session_id: str


class SignalConfig(BaseModel):
    """Signal messenger via signal-cli-rest-api."""

    enabled: bool = True
    api_url: str = "http://localhost:8080"
    phone_number: str
    allow_from: list[str] = Field(default_factory=list)
    dm_policy: Literal["pairing", "allowlist", "open"] = "pairing"


class ChannelConfig(BaseModel):
    """Channel configuration."""

    enabled: bool = False
    telegram: TelegramConfig | None = None
    discord: DiscordConfig | None = None
    slack: SlackConfig | None = None
    whatsapp: WhatsAppConfig | None = None
    matrix: MatrixConfig | None = None
    irc: IRCConfig | None = None
    webchat: WebChatConfig | None = None
    signal: SignalConfig | None = None


class ApiConfig(BaseModel):
    """HTTP API configuration."""

    host: str = "127.0.0.1"
    port: int = Field(default=8000, gt=0, lt=65536)


class Config(BaseModel):
    """Main configuration with hot reload support."""

    workspace: Path
    llm: LLMConfig
    default_agent: str
    agents_path: Path = Field(default=Path("agents"))
    skills_path: Path = Field(default=Path("skills"))
    crons_path: Path = Field(default=Path("crons"))
    memories_path: Path = Field(default=Path("memories"))
    logging_path: Path = Field(default=Path(".logs"))
    history_path: Path = Field(default=Path(".history"))
    event_path: Path = Field(default=Path(".event"))
    websearch: BraveWebSearchConfig | None = None
    webread: Crawl4AIWebReadConfig | None = None
    channels: ChannelConfig = Field(default_factory=ChannelConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    sources: dict[str, SourceSessionConfig] = Field(default_factory=dict)
    routing: dict = Field(default_factory=lambda: {"bindings": []})
    default_delivery_source: str | None = None
    tts: TTSConfig = Field(default_factory=TTSConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)
    plugins_path: Path = Field(default=Path("plugins"))

    @model_validator(mode="after")
    def resolve_paths(self) -> "Config":
        """Resolve relative paths to absolute using workspace."""
        for field_name in (
            "agents_path",
            "skills_path",
            "crons_path",
            "memories_path",
            "logging_path",
            "history_path",
            "event_path",
            "plugins_path",
        ):
            path = getattr(self, field_name)
            if not path.is_absolute():
                setattr(self, field_name, self.workspace / path)
        return self

    @classmethod
    def load(cls, workspace_dir: Path) -> "Config":
        """Load configuration from workspace directory."""
        workspace_dir = Path(workspace_dir).resolve()
        config_data = cls._load_merged_configs(workspace_dir)
        config_data["workspace"] = workspace_dir
        return cls.model_validate(config_data)

    @classmethod
    def _load_merged_configs(cls, workspace_dir: Path) -> dict[str, Any]:
        """Load and merge user and runtime config files."""
        config_data: dict[str, Any] = {}

        user_config = workspace_dir / "config.user.yaml"
        runtime_config = workspace_dir / "config.runtime.yaml"

        if user_config.exists():
            with open(user_config) as f:
                config_data = cls._deep_merge(config_data, yaml.safe_load(f) or {})

        if runtime_config.exists():
            with open(runtime_config) as f:
                config_data = cls._deep_merge(config_data, yaml.safe_load(f) or {})

        return config_data

    @staticmethod
    def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Deep merge override dict into base dict."""
        result = base.copy()

        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = Config._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def _set_nested(self, obj: dict, key: str, value: Any) -> None:
        """Set a nested value in a dict using dot notation."""
        keys = key.split(".")
        for k in keys[:-1]:
            if k not in obj or not isinstance(obj[k], dict):
                obj[k] = {}
            obj = obj[k]
        obj[keys[-1]] = value

    def _set_config_value(self, config_path: Path, key: str, value: Any) -> None:
        """Update a config value in a YAML file."""
        # Load existing or start fresh
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}

        if isinstance(value, BaseModel):
            value = value.model_dump()

        # Update the key (supports nested via dot notation)
        self._set_nested(data, key, value)

        # Write back
        with open(config_path, "w") as f:
            yaml.dump(data, f)

    def set_user(self, key: str, value: Any) -> None:
        """Update a config value in config.user.yaml."""
        self._set_config_value(self.workspace / "config.user.yaml", key, value)

    def set_runtime(self, key: str, value: Any) -> None:
        """Update a runtime value in config.runtime.yaml."""
        self._set_config_value(self.workspace / "config.runtime.yaml", key, value)

    def reload(self) -> bool:
        """Re-read config.user.yaml and merge with runtime."""
        try:
            config_data = self._load_merged_configs(self.workspace)
            config_data["workspace"] = self.workspace

            # Create new instance and copy values
            new_config = Config.model_validate(config_data)

            # Update all fields from new config
            for field_name in Config.model_fields:
                setattr(self, field_name, getattr(new_config, field_name))

            return True
        except Exception as e:
            logging.debug("Config reload failed: %s", e)
            return False


class ConfigHandler(FileSystemEventHandler):
    """Handles config file modification events."""

    def __init__(self, config: Config):
        self._config = config

    def on_modified(self, event):
        """Reload config when config.user.yaml changes."""
        if not event.is_directory and event.src_path.endswith("config.user.yaml"):
            self._config.reload()


class ConfigReloader:
    """Manages watchdog observer for config hot reload."""

    def __init__(self, config: Config):
        self._config = config
        self._observer = Observer()

    def start(self) -> None:
        """Start watching config file for changes."""
        handler = ConfigHandler(self._config)
        self._observer.schedule(handler, str(self._config.workspace), recursive=False)
        self._observer.start()

    def stop(self) -> None:
        """Stop watching."""
        self._observer.stop()
        self._observer.join()
        del self._observer
