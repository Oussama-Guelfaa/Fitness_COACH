"""Load durable context into graph state."""

from sqlalchemy.ext.asyncio import AsyncSession

from agents.nodes.events import record_event
from agents.serialization import (
    checkin_to_dict,
    health_connection_to_dict,
    health_daily_summary_to_dict,
    health_workout_to_dict,
    location_to_dict,
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
    HealthRepository,
    LocationRepository,
    ProfileRepository,
    TrackingRepository,
    UserRepository,
)
from services.weather import get_current_weather


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
    location_repo = LocationRepository(session)
    health_repo = HealthRepository(session)

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
    location = await location_repo.get_active_location(user.id)
    health_connection = await health_repo.get_active_connection(user.id)
    latest_health_summary = await health_repo.get_latest_daily_summary(user.id)
    recent_health_summaries = await health_repo.get_recent_daily_summaries(user.id)
    recent_health_workouts = await health_repo.get_recent_health_workouts(user.id)

    weather = {}
    if location:
        try:
            current_weather = await get_current_weather(
                location.latitude,
                location.longitude,
                timezone=location.timezone or "auto",
            )
            weather = {
                "temperature_c": current_weather.temperature_c,
                "apparent_temperature_c": current_weather.apparent_temperature_c,
                "humidity_percent": current_weather.humidity_percent,
                "precipitation_mm": current_weather.precipitation_mm,
                "wind_speed_kmh": current_weather.wind_speed_kmh,
                "weather_code": current_weather.weather_code,
                "description": current_weather.description,
                "time": current_weather.time,
                "summary": current_weather.to_coaching_summary(),
            }
        except Exception as exc:
            weather = {"error": str(exc)}

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
        "location": location_to_dict(location),
        "weather": weather,
        "health_connection": health_connection_to_dict(health_connection),
        "latest_health_summary": health_daily_summary_to_dict(latest_health_summary),
        "recent_health_summaries": [health_daily_summary_to_dict(item) for item in recent_health_summaries],
        "recent_health_workouts": [health_workout_to_dict(item) for item in recent_health_workouts],
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
            "has_location": bool(location),
            "has_weather": bool(weather and not weather.get("error")),
            "has_apple_health": bool(health_connection),
            "health_summaries": len(recent_health_summaries),
            "health_workouts": len(recent_health_workouts),
        },
    )
    return updates
