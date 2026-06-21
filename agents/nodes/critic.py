"""Final response verifier."""

from sqlalchemy.ext.asyncio import AsyncSession

from agents.nodes.events import record_event
from agents.state import CoachState


async def coach_critic(state: CoachState, session: AsyncSession) -> dict:
    """Run deterministic quality and safety checks before composing the final answer."""
    response = state.get("candidate_response", "")
    response_lower = response.lower()
    intent = state.get("intent", "general")
    findings: list[str] = []

    if any(state.get("safety_flags", {}).values()) and "professionnel" not in response_lower:
        findings.append("safety_professional_referral_missing")

    if intent in {"workout", "morning_plan"}:
        exercise_markers = ["squat", "pompe", "gainage", "fente", "développé", "deadlift", "rowing"]
        mentions_exercises = any(marker in response_lower for marker in exercise_markers)
        if mentions_exercises and "youtube.com/results?search_query=" not in response_lower:
            findings.append("exercise_demo_links_missing")

    if intent in {"nutrition", "meal_photo", "morning_plan"}:
        if "kcal" not in response_lower and "calorie" not in response_lower:
            findings.append("nutrition_calorie_estimate_missing")

    await record_event(
        session,
        state,
        "coach_critic",
        "checked",
        {"findings": findings, "intent": intent},
    )
    return {"critic_findings": findings}

