"""MCP gateway used by LangGraph nodes.

The gateway keeps MCP optional. If no MCP servers are configured, the agent graph
still runs normally and records that no external tool context was available.
"""

import json
from typing import Any

import structlog

from config.settings import MCPSettings, get_settings

logger = structlog.get_logger()


INTENT_TOOL_KEYWORDS = {
    "workout": ["exercise", "workout", "training", "movement"],
    "nutrition": ["food", "meal", "nutrition", "macro", "recipe"],
    "meal_photo": ["food", "meal", "nutrition", "macro", "vision"],
    "recovery": ["sleep", "recovery", "readiness", "health", "weather"],
    "accountability": ["calendar", "reminder", "task", "schedule", "location"],
    "document_request": ["pdf", "document", "report", "nutrition", "workout"],
    "morning_plan": ["exercise", "workout", "food", "meal", "calendar", "weather", "pdf"],
    "evening_checkin": ["checkin", "workout", "meal", "sleep", "pdf"],
    "general": ["location", "weather", "pdf"],
}


class MCPGateway:
    """Loads MCP tool metadata for scoped agent use."""

    def __init__(self, settings: MCPSettings | None = None):
        self.settings = settings or get_settings().mcp
        self._tool_cache: list[dict[str, Any]] | None = None
        self._load_error: str | None = None

    def _server_config(self) -> dict[str, Any]:
        config: dict[str, Any] = {}
        if self.settings.servers_json:
            try:
                parsed = json.loads(self.settings.servers_json)
                if isinstance(parsed, dict):
                    config.update(parsed)
            except json.JSONDecodeError as exc:
                self._load_error = f"Invalid MCP_SERVERS_JSON: {exc}"
                logger.warning("Invalid MCP server JSON", error=str(exc))

        if self.settings.internal_stdio_enabled:
            config.setdefault(
                "fitness_internal",
                {
                    "transport": "stdio",
                    "command": self.settings.internal_server_command,
                    "args": self.settings.internal_server_args.split(),
                },
            )
        return config

    async def _load_tools(self) -> list[dict[str, Any]]:
        if self._tool_cache is not None:
            return self._tool_cache
        self._tool_cache = []
        if not self.settings.enabled:
            return self._tool_cache

        server_config = self._server_config()
        if not server_config:
            return self._tool_cache

        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
        except ImportError as exc:
            self._load_error = "langchain-mcp-adapters is not installed"
            logger.warning("MCP adapter unavailable", error=str(exc))
            return self._tool_cache

        try:
            client = MultiServerMCPClient(server_config)
            tools = await client.get_tools()
        except Exception as exc:
            self._load_error = str(exc)
            logger.warning("Failed to load MCP tools", error=str(exc))
            return self._tool_cache

        self._tool_cache = [
            {
                "name": getattr(tool, "name", ""),
                "description": getattr(tool, "description", "") or "",
            }
            for tool in tools
        ]
        return self._tool_cache

    async def describe_tools_for_intent(self, intent: str) -> dict[str, Any]:
        """Return tool metadata scoped to the current agent intent."""
        tools = await self._load_tools()
        keywords = INTENT_TOOL_KEYWORDS.get(intent, [])
        if keywords:
            scoped = [
                tool for tool in tools
                if any(keyword in f"{tool['name']} {tool['description']}".lower() for keyword in keywords)
            ]
        else:
            scoped = tools
        return {
            "enabled": self.settings.enabled,
            "intent": intent,
            "tools": scoped,
            "total_tools": len(tools),
            "error": self._load_error,
        }
