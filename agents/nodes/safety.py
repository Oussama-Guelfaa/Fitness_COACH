"""Safety sentinel node."""

from sqlalchemy.ext.asyncio import AsyncSession

from agents.nodes.events import record_event
from agents.state import CoachState
from coaching.safety import detect_safety_concerns, get_safety_instructions
from database.repositories import AgentRepository


async def safety_sentinel(state: CoachState, session: AsyncSession) -> dict:
    """Detect safety-sensitive messages before routing to specialist agents."""
    text = state.get("incoming_message", "")
    concerns = detect_safety_concerns(text)
    instructions = get_safety_instructions(text)
    has_concern = any(concerns.values())

    if has_concern:
        await AgentRepository(session).create_safety_event(
            user_id=state["user_id"],
            run_id=state.get("run_id"),
            concerns=concerns,
            message_excerpt=text,
            severity="caution",
        )

    await record_event(
        session,
        state,
        "safety_sentinel",
        "safety_checked",
        {"concerns": concerns, "has_concern": has_concern},
    )
    return {
        "safety_flags": concerns,
        "safety_instructions": instructions,
    }

