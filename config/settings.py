"""Application configuration using pydantic-settings."""

from pydantic_settings import BaseSettings
from pydantic import Field


class LLMSettings(BaseSettings):
    """LLM provider configuration."""

    provider: str = Field(default="ollama", alias="LLM_PROVIDER")
    base_url: str = Field(default="http://localhost:11434", alias="LLM_BASE_URL")
    model: str = Field(default="llama3.1", alias="LLM_MODEL")
    api_key: str = Field(default="", alias="LLM_API_KEY")
    temperature: float = 0.7
    max_tokens: int = 2048

    model_config = {"env_file": ".env", "extra": "ignore"}


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    url: str = Field(
        default="sqlite+aiosqlite:///./fitness_coach.db", alias="DATABASE_URL"
    )

    model_config = {"env_file": ".env", "extra": "ignore"}


class TelegramSettings(BaseSettings):
    """Telegram bot configuration.

    Supports multiple bot tokens via a comma-separated list in TELEGRAM_BOT_TOKENS.
    Falls back to single TELEGRAM_BOT_TOKEN for backward compatibility.
    """

    bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    bot_tokens: str = Field(default="", alias="TELEGRAM_BOT_TOKENS")

    model_config = {"env_file": ".env", "extra": "ignore"}

    def get_tokens(self) -> list[str]:
        """Return deduplicated list of bot tokens to use."""
        tokens: list[str] = []
        seen: set[str] = set()
        # Merge both sources, deduplicate, preserve order
        raw = []
        if self.bot_tokens:
            raw.extend(t.strip() for t in self.bot_tokens.split(",") if t.strip())
        if self.bot_token and self.bot_token.strip():
            raw.append(self.bot_token.strip())
        for t in raw:
            if t not in seen:
                seen.add(t)
                tokens.append(t)
        return tokens


class VisionSettings(BaseSettings):
    """Vision LLM configuration for meal photo analysis."""

    provider: str = Field(default="gemini", alias="VISION_PROVIDER")
    api_key: str = Field(default="", alias="VISION_API_KEY")
    model: str = Field(default="gemini-2.5-flash", alias="VISION_MODEL")

    model_config = {"env_file": ".env", "extra": "ignore"}


class SchedulerSettings(BaseSettings):
    """Scheduler configuration."""

    morning_hour: int = Field(default=7, alias="MORNING_HOUR")
    morning_minute: int = Field(default=30, alias="MORNING_MINUTE")
    evening_hour: int = Field(default=21, alias="EVENING_HOUR")
    evening_minute: int = Field(default=0, alias="EVENING_MINUTE")
    timezone: str = Field(default="Europe/Paris", alias="TIMEZONE")

    model_config = {"env_file": ".env", "extra": "ignore"}


class MCPSettings(BaseSettings):
    """MCP integration configuration."""

    enabled: bool = Field(default=False, alias="MCP_ENABLED")
    servers_json: str = Field(default="", alias="MCP_SERVERS_JSON")
    internal_stdio_enabled: bool = Field(default=False, alias="MCP_INTERNAL_STDIO_ENABLED")
    internal_server_command: str = Field(default="python", alias="MCP_INTERNAL_SERVER_COMMAND")
    internal_server_args: str = Field(
        default="-m agents.mcp.internal_server",
        alias="MCP_INTERNAL_SERVER_ARGS",
    )

    model_config = {"env_file": ".env", "extra": "ignore"}


class AppSettings(BaseSettings):
    """Top-level application settings."""

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    debug: bool = Field(default=False, alias="DEBUG")

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def llm(self) -> LLMSettings:
        return LLMSettings()

    @property
    def database(self) -> DatabaseSettings:
        return DatabaseSettings()

    @property
    def telegram(self) -> TelegramSettings:
        return TelegramSettings()

    @property
    def scheduler(self) -> SchedulerSettings:
        return SchedulerSettings()

    @property
    def vision(self) -> VisionSettings:
        return VisionSettings()

    @property
    def mcp(self) -> MCPSettings:
        return MCPSettings()


def get_settings() -> AppSettings:
    """Get application settings singleton."""
    return AppSettings()
