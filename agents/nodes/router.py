"""Intent router node."""

import re

from sqlalchemy.ext.asyncio import AsyncSession

from agents.nodes.events import record_event
from agents.state import CoachIntent, CoachState, SPECIALIST_INTENTS


def _contains(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def _detect_document_request(text: str) -> dict | None:
    wants_document = _contains(
        text,
        [
            "pdf",
            "document",
            "fichier",
            "rapport",
            "export",
            "imprimer",
            "envoie-moi",
            "envoie moi",
            "fournis-moi",
            "fournis moi",
        ],
    )
    if not wants_document:
        return None

    if _contains(text, ["nutrition", "repas", "aliment", "calorie", "macro", "protéine", "proteine"]):
        return {
            "subject": "nutrition",
            "document_type": "nutrition_plan",
            "title": "Plan nutritionnel personnalisé",
            "subtitle": "Repas, calories, quantités, budget et ajustements coach",
            "filename_prefix": "plan-nutritionnel",
        }
    if _contains(text, ["séance", "seance", "entrainement", "entraînement", "muscu", "cardio", "exercice"]):
        return {
            "subject": "workout",
            "document_type": "workout_plan",
            "title": "Plan d'entraînement personnalisé",
            "subtitle": "Séances, exercices, intensité, sécurité et progression",
            "filename_prefix": "plan-entrainement",
        }
    return {
        "subject": "coach_summary",
        "document_type": "coach_report",
        "title": "Document Coach Fitness",
        "subtitle": "Plan personnalisé généré par le coach",
        "filename_prefix": "document-coach",
    }


def _classify_message(state: CoachState) -> tuple[CoachIntent, dict | None]:
    workflow = state.get("workflow", "user_message")
    if workflow in {"morning_plan", "evening_checkin", "inactive_followup", "meal_photo"}:
        return workflow, None  # type: ignore[return-value]

    if any(state.get("safety_flags", {}).values()):
        return "safety", None

    text = re.sub(r"\s+", " ", state.get("incoming_message", "").lower())

    document_request = _detect_document_request(text)
    if document_request:
        return "document_request", document_request
    if _contains(text, ["photo", "assiette", "repas en photo", "scan repas"]):
        return "meal_photo", None
    if _contains(text, ["douleur", "bless", "récup", "recup", "sommeil", "fatigue", "courbature"]):
        return "recovery", None
    if _contains(text, ["manger", "repas", "nutrition", "calorie", "kcal", "macro", "protéine", "proteine"]):
        return "nutrition", None
    if _contains(text, ["séance", "seance", "entrainement", "entraînement", "muscu", "cardio", "exercice"]):
        return "workout", None
    if _contains(text, ["check-in", "bilan", "journée", "journee", "énergie", "energie", "motivation"]):
        return "checkin", None
    if _contains(text, ["rappelle", "rappel", "calendrier", "objectif", "habitude", "discipline"]):
        return "accountability", None
    if state.get("is_onboarding"):
        return "onboarding", None
    return "general", None


async def intent_router(state: CoachState, session: AsyncSession) -> dict:
    intent, document_request = _classify_message(state)
    if intent not in SPECIALIST_INTENTS:
        intent = "general"
    payload = {"intent": intent}
    if document_request:
        payload["document_request"] = document_request
    await record_event(session, state, "intent_router", "routed", payload)
    return payload


def route_to_specialist(state: CoachState) -> str:
    """LangGraph conditional edge target."""
    intent = state.get("intent", "general")
    return intent if intent in SPECIALIST_INTENTS else "general"
