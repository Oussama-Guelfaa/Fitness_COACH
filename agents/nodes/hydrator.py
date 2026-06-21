"""Load durable context into graph state."""

from sqlalchemy.ext.asyncio import AsyncSession

from agents.nodes.events import record_event
from agents.serialization import (
    checkin_to_dict,
    memory_to_dict,
    message_to_dict,
    nutrition_to_dict,
    profile_to_dict,
    workout_to_dict,
)
from agents.state import CoachState
from coaching.profile_manager import ProfileManager
from database.repositories import (
    AgentRepository,
    ConversationRepository,
    ProfileRepository,
    TrackingRepository,
    UserRepository,
)


async def hydrate_state(
    state: CoachState,
    session: AsyncSession,
    profile_manager: ProfileManager,
) -> dict:
    """Hydrate user, conversation, profile, recent history, and fitness-twin memory."""
    user_repo = UserRepository(session)
    profile_repo = ProfileRepository(session)
    conv_repo = ConversationRepository(session)
    tracking_repo = TrackingRepository(session)
    agent_repo = AgentRepository(session)

    user = None
    if state.get("user_id"):
        user = await user_repo.get_by_id(state["user_id"])
    if user is None:
        user = await user_repo.get_or_create(
            state["external_id"],
            state.get("platform", "telegram"),
            state.get("username"),
        )

    profile = await profile_repo.get_by_user_id(user.id)
    is_complete, missing = profile_manager.check_profile_completeness(profile)

    conv = await conv_repo.get_or_create_active(user.id)
    recent_messages = await conv_repo.get_recent_messages(conv.id, limit=15)
    checkins = await tracking_repo.get_recent_checkins(user.id)
    workouts = await tracking_repo.get_recent_workouts(user.id)
    nutrition = await tracking_repo.get_recent_nutrition(user.id)
    memories = await agent_repo.get_recent_memories(user.id)

    updates = {
        "user_id": user.id,
        "external_id": user.external_id,
        "platform": user.platform,
        "username": user.username,
        "conversation_id": conv.id,
        "profile": profile_to_dict(profile),
        "is_onboarding": not is_complete,
        "missing_profile_fields": missing,
        "recent_messages": [message_to_dict(msg) for msg in recent_messages],
        "recent_checkins": [checkin_to_dict(item) for item in checkins],
        "recent_workouts": [workout_to_dict(item) for item in workouts],
        "recent_nutrition": [nutrition_to_dict(item) for item in nutrition],
        "coach_memories": [memory_to_dict(item) for item in memories],
    }
    await record_event(
        session,
        {**state, **updates},
        "memory_hydrator",
        "hydrated",
        {
            "profile_complete": is_complete,
            "missing_profile_fields": missing,
            "recent_messages": len(recent_messages),
            "fitness_twin_memories": len(memories),
        },
    )
    return updates

