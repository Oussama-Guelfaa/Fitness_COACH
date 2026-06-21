"""Profile scout node."""

from sqlalchemy.ext.asyncio import AsyncSession

from agents.nodes.events import record_event
from agents.serialization import profile_to_dict
from agents.state import CoachState
from coaching.profile_manager import ProfileManager
from database.repositories import ProfileRepository


async def profile_scout(
    state: CoachState,
    session: AsyncSession,
    profile_manager: ProfileManager,
) -> dict:
    """Extract and persist structured profile updates from user text."""
    workflow = state.get("workflow", "user_message")
    if workflow not in {"user_message"}:
        await record_event(session, state, "profile_scout", "skipped", {"workflow": workflow})
        return {"extracted_profile_updates": {}}

    text = state.get("incoming_message", "")
    updates = await profile_manager.extract_profile_updates(text)
    if not updates:
        await record_event(session, state, "profile_scout", "no_updates", {})
        return {"extracted_profile_updates": {}}

    profile = await ProfileRepository(session).update(state["user_id"], **updates)
    is_complete, missing = profile_manager.check_profile_completeness(profile)
    await record_event(
        session,
        state,
        "profile_scout",
        "profile_updated",
        {"fields": list(updates.keys()), "profile_complete": is_complete},
    )
    return {
        "profile": profile_to_dict(profile),
        "is_onboarding": not is_complete,
        "missing_profile_fields": missing,
        "extracted_profile_updates": updates,
    }

