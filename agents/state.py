"""Typed state shared by the coach agent graph."""

from typing import Any, Literal, TypedDict


CoachIntent = Literal[
    "general",
    "onboarding",
    "safety",
    "workout",
    "nutrition",
    "meal_photo",
    "recovery",
    "checkin",
    "accountability",
    "document_request",
    "morning_plan",
    "evening_checkin",
    "inactive_followup",
]


class CoachState(TypedDict, total=False):
    """Serializable state passed through the agent graph."""

    run_id: int
    run_type: str
    workflow: str
    thread_id: str

    user_id: int
    external_id: str
    platform: str
    username: str | None
    conversation_id: int

    incoming_message: str
    image_mime_type: str
    vision_analysis: str

    intent: CoachIntent
    safety_flags: dict[str, bool]
    safety_instructions: str
    is_onboarding: bool
    missing_profile_fields: list[str]

    profile: dict[str, Any]
    recent_messages: list[dict[str, Any]]
    recent_checkins: list[dict[str, Any]]
    recent_workouts: list[dict[str, Any]]
    recent_nutrition: list[dict[str, Any]]
    coach_memories: list[dict[str, Any]]
    location: dict[str, Any]
    weather: dict[str, Any]

    extracted_profile_updates: dict[str, Any]
    mcp_tool_context: dict[str, Any]
    document_request: dict[str, Any]

    candidate_response: str
    critic_findings: list[str]
    final_response: str
    generated_document_path: str
    generated_document_id: int
    generated_document_title: str
    memory_updates: list[dict[str, Any]]
    pending_actions: list[dict[str, Any]]
    plan_type: str | None


SPECIALIST_INTENTS: set[str] = {
    "general",
    "onboarding",
    "safety",
    "workout",
    "nutrition",
    "meal_photo",
    "recovery",
    "checkin",
    "accountability",
    "document_request",
    "morning_plan",
    "evening_checkin",
    "inactive_followup",
}
