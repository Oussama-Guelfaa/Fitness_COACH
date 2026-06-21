"""Response composer node."""

from sqlalchemy.ext.asyncio import AsyncSession

from agents.nodes.events import record_event
from agents.state import CoachState
from coaching.safety import SAFETY_WARNING


async def response_composer(state: CoachState, session: AsyncSession) -> dict:
    """Produce the final user-facing response."""
    response = state.get("candidate_response", "").strip()
    if not response:
        response = (
            "Je n'ai pas réussi à générer une réponse complète. "
            "Réessaie avec une demande un peu plus précise."
        )

    if any(state.get("safety_flags", {}).values()) and not response.startswith("⚠️"):
        response = f"{SAFETY_WARNING}\n\n{response}"

    findings = state.get("critic_findings", [])
    addenda = []
    if "exercise_demo_links_missing" in findings:
        addenda.append(
            "Pour chaque exercice, vérifie la forme avec une recherche YouTube du type "
            "`nom exercice tutoriel` avant de charger lourd."
        )
    if "nutrition_calorie_estimate_missing" in findings:
        addenda.append(
            "Les calories restent une estimation : ajuste les quantités selon ta faim, "
            "tes progrès et ton objectif."
        )
    if addenda:
        response = f"{response}\n\n" + "\n".join(addenda)

    await record_event(
        session,
        state,
        "response_composer",
        "composed",
        {"response_length": len(response), "addenda": len(addenda)},
    )
    return {"final_response": response}

