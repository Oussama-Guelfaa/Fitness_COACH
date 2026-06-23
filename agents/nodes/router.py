"""Intent router node."""

import re

from sqlalchemy.ext.asyncio import AsyncSession

from agents.nodes.events import record_event
from agents.state import CoachIntent, CoachState, SPECIALIST_INTENTS


def _contains(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


FITNESS_DOMAIN_WORDS = [
    "fitness", "coach", "sport", "muscu", "musculation", "gym", "séance", "seance",
    "entrainement", "entraînement", "workout", "exercice", "cardio", "course",
    "running", "marche", "pas", "nutrition", "repas", "aliment", "calorie",
    "kcal", "macro", "protéine", "proteine", "diète", "diete", "régime", "regime",
    "menu", "poids", "kg", "cm", "taille", "sommeil", "récup", "recup",
    "récupération", "recuperation", "douleur", "blessure", "fatigue",
    "hydratation", "météo", "meteo", "apple health", "healthkit", "health",
    "pdf coach", "plan nutritionnel", "plan alimentaire", "plan d'entraînement",
    "plan d'entrainement",
]


OUT_OF_SCOPE_WORDS = [
    "python", "javascript", "typescript", "react", "html", "css", "sql",
    "docker", "kubernetes", "github", "git ", "algorithme", "programmation",
    "coder", "code ", "script", "fonction", "debug", "bug", "api rest",
    "trading", "crypto", "bourse", "investissement", "politique", "élection",
    "election", "histoire", "géographie", "geographie", "physique quantique",
    "devoir", "dissertation", "rédige un email", "redige un email", "cv",
    "lettre de motivation", "film", "musique", "voyage", "restaurant",
]


TASK_REQUEST_WORDS = [
    "écris", "ecris", "rédige", "redige", "traduis", "résume", "resume",
    "explique", "fais", "crée", "cree", "génère", "genere", "donne moi",
    "donne-moi", "aide moi à", "aide moi a", "peux-tu", "peux tu",
]


SHORT_ALLOWED_MESSAGES = [
    "salut", "bonjour", "bonsoir", "merci", "ok", "d'accord", "daccord",
    "oui", "non", "ça va", "ca va",
]


def _is_out_of_scope(text: str) -> bool:
    """Detect requests outside the coach domain before calling a specialist."""
    if not text or _contains(text, SHORT_ALLOWED_MESSAGES):
        return False
    if _contains(text, FITNESS_DOMAIN_WORDS):
        return False

    explicit_unrelated = _contains(text, OUT_OF_SCOPE_WORDS)
    if explicit_unrelated:
        return True

    asks_for_work = _contains(text, TASK_REQUEST_WORDS)
    has_question_mark = "?" in text
    enough_words = len(text.split()) >= 5
    return enough_words and (asks_for_work or has_question_mark)


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

    if _contains(
        text,
        [
            "nutrition", "repas", "aliment", "calorie", "macro", "protéine",
            "proteine", "diète", "diete", "régime", "regime", "menu",
        ],
    ):
        return {
            "subject": "nutrition",
            "document_type": "nutrition_plan",
            "title": "Plan nutritionnel personnalisé",
            "subtitle": "Repas, calories, quantités, budget et ajustements coach",
            "filename_prefix": "plan-nutritionnel",
        }
    if _contains(
        text,
        [
            "séance", "seance", "entrainement", "entraînement", "muscu",
            "cardio", "exercice", "programme", "full body", "push pull",
            "jambes", "pectoraux", "dos",
        ],
    ):
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

    if _is_out_of_scope(text):
        return "out_of_scope", None

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
