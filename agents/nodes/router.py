"""Intent router node."""

import re

from sqlalchemy.ext.asyncio import AsyncSession

from agents.nodes.events import record_event
from agents.state import CoachIntent, CoachState, SPECIALIST_INTENTS


def _contains(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def _classify_message(state: CoachState) -> CoachIntent:
    workflow = state.get("workflow", "user_message")
    if workflow in {"morning_plan", "evening_checkin", "inactive_followup", "meal_photo"}:
        return workflow  # type: ignore[return-value]

    if any(state.get("safety_flags", {}).values()):
        return "safety"

    text = re.sub(r"\s+", " ", state.get("incoming_message", "").lower())

    if _contains(text, ["photo", "assiette", "repas en photo", "scan repas"]):
        return "meal_photo"
    if _contains(text, ["douleur", "bless", "récup", "recup", "sommeil", "fatigue", "courbature"]):
        return "recovery"
    if _contains(text, ["manger", "repas", "nutrition", "calorie", "kcal", "macro", "protéine", "proteine"]):
        return "nutrition"
    if _contains(text, ["séance", "seance", "entrainement", "entraînement", "muscu", "cardio", "exercice"]):
        return "workout"
    if _contains(text, ["check-in", "bilan", "journée", "journee", "énergie", "energie", "motivation"]):
        return "checkin"
    if _contains(text, ["rappelle", "rappel", "calendrier", "objectif", "habitude", "discipline"]):
        return "accountability"
    if state.get("is_onboarding"):
        return "onboarding"
    return "general"


async def intent_router(state: CoachState, session: AsyncSession) -> dict:
    intent = _classify_message(state)
    if intent not in SPECIALIST_INTENTS:
        intent = "general"
    await record_event(session, state, "intent_router", "routed", {"intent": intent})
    return {"intent": intent}


def route_to_specialist(state: CoachState) -> str:
    """LangGraph conditional edge target."""
    intent = state.get("intent", "general")
    return intent if intent in SPECIALIST_INTENTS else "general"

