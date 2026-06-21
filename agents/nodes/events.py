"""Agent trace helpers."""

from sqlalchemy.ext.asyncio import AsyncSession

from agents.state import CoachState
from database.repositories import AgentRepository


async def record_event(
    session: AsyncSession,
    state: CoachState,
    node: str,
    event_type: str,
    payload: dict | None = None,
):
    """Persist a trace event when the graph already has a run id."""
    run_id = state.get("run_id")
    user_id = state.get("user_id")
    if not run_id or not user_id:
        return
    await AgentRepository(session).add_event(
        run_id=run_id,
        user_id=user_id,
        node=node,
        event_type=event_type,
        payload=payload,
    )

