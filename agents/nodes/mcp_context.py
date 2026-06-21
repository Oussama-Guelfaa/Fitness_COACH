"""MCP discovery node."""

from sqlalchemy.ext.asyncio import AsyncSession

from agents.nodes.events import record_event
from agents.state import CoachState
from agents.tools.mcp_gateway import MCPGateway


async def load_mcp_context(
    state: CoachState,
    session: AsyncSession,
    gateway: MCPGateway,
) -> dict:
    """Load scoped MCP tool metadata for the selected intent."""
    context = await gateway.describe_tools_for_intent(state.get("intent", "general"))
    await record_event(
        session,
        state,
        "mcp_gateway",
        "tools_described",
        {
            "enabled": context.get("enabled", False),
            "tool_count": len(context.get("tools", [])),
            "intent": state.get("intent"),
        },
    )
    return {"mcp_tool_context": context}
