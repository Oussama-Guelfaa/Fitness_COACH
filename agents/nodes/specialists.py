"""Specialist coach agents used by the graph."""

from sqlalchemy.ext.asyncio import AsyncSession

from agents.nodes.events import record_event
from agents.state import CoachState
from llm.base import BaseLLMProvider, LLMMessage
from llm.prompt_builder import build_system_prompt


def _format_memories(state: CoachState) -> str:
    memories = state.get("coach_memories", [])
    if not memories:
        return ""
    lines = ["=== FITNESS TWIN MEMORY ==="]
    for memory in memories[:12]:
        key = memory.get("memory_key", "memoire")
        content = memory.get("content", "")
        if content:
            lines.append(f"- {key}: {content}")
    return "\n".join(lines)


def _format_mcp_context(state: CoachState) -> str:
    context = state.get("mcp_tool_context", {})
    tools = context.get("tools", [])
    if not context.get("enabled") or not tools:
        return ""
    lines = ["=== OUTILS MCP DISPONIBLES POUR CETTE INTENTION ==="]
    for tool in tools[:12]:
        name = tool.get("name", "outil")
        description = tool.get("description", "")
        lines.append(f"- {name}: {description}")
    lines.append(
        "Utilise ces outils seulement si l'information existante ne suffit pas. "
        "Ne prétends jamais avoir appelé un outil si ce n'est pas le cas."
    )
    return "\n".join(lines)


def _format_environment_context(state: CoachState) -> str:
    location = state.get("location") or {}
    weather = state.get("weather") or {}
    if not location and not weather:
        return ""

    lines = ["=== CONTEXTE LOCAL CONSENTI ==="]
    if location:
        label = location.get("label") or "Position partagée"
        details = [label]
        if location.get("admin_area"):
            details.append(location["admin_area"])
        if location.get("country"):
            details.append(location["country"])
        lines.append(f"- Localisation: {', '.join(details)}")
    if weather.get("summary"):
        lines.append(f"- Météo actuelle: {weather['summary']}")
        lines.append(
            "- Adapte les recommandations outdoor, hydratation, échauffement et intensité "
            "selon cette météo, sans dramatiser."
        )
    elif weather.get("error"):
        lines.append("- Météo actuelle indisponible malgré une localisation consentie.")
    return "\n".join(lines)


def _format_health_context(state: CoachState) -> str:
    connection = state.get("health_connection") or {}
    latest = state.get("latest_health_summary") or {}
    summaries = state.get("recent_health_summaries") or []
    workouts = state.get("recent_health_workouts") or []
    if not connection and not latest and not workouts:
        return ""

    lines = ["=== CONTEXTE APPLE HEALTH CONSENTI ==="]
    if connection:
        synced_at = connection.get("last_synced_at") or "jamais"
        device = connection.get("device_name") or "iPhone / Apple Watch"
        lines.append(f"- Source: Apple Health via {device}, dernière sync: {synced_at}")
    if latest:
        details = []
        if latest.get("summary_date"):
            details.append(f"date {latest['summary_date']}")
        if latest.get("steps") is not None:
            details.append(f"{latest['steps']} pas")
        if latest.get("active_energy_kcal") is not None:
            details.append(f"{latest['active_energy_kcal']} kcal actives")
        if latest.get("sleep_minutes") is not None:
            details.append(f"{round(latest['sleep_minutes'] / 60, 1)} h sommeil")
        if latest.get("resting_heart_rate_bpm") is not None:
            details.append(f"FC repos {latest['resting_heart_rate_bpm']} bpm")
        if latest.get("hrv_ms") is not None:
            details.append(f"HRV {latest['hrv_ms']} ms")
        if details:
            lines.append("- Dernier résumé: " + ", ".join(details))
    if summaries:
        avg_steps = _average([item.get("steps") for item in summaries])
        avg_sleep = _average([item.get("sleep_minutes") for item in summaries])
        if avg_steps is not None:
            lines.append(f"- Moyenne récente: {int(avg_steps)} pas/jour")
        if avg_sleep is not None:
            lines.append(f"- Sommeil récent moyen: {round(avg_sleep / 60, 1)} h/nuit")
    if workouts:
        last_workout = workouts[-1]
        workout_bits = [
            last_workout.get("workout_type") or "workout",
            str(last_workout.get("started_at") or ""),
        ]
        if last_workout.get("duration_minutes") is not None:
            workout_bits.append(f"{round(last_workout['duration_minutes'])} min")
        lines.append("- Dernier entraînement Apple Health: " + ", ".join(bit for bit in workout_bits if bit))
    lines.append(
        "- Utilise ces données comme signaux de contexte, pas comme diagnostic médical. "
        "Adapte charge, récupération, hydratation et calories avec prudence."
    )
    return "\n".join(lines)


def _average(values) -> float | None:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _shared_extra(state: CoachState) -> str:
    parts = []
    if state.get("safety_instructions"):
        parts.append(state["safety_instructions"])
    elif state.get("is_onboarding") and state.get("missing_profile_fields"):
        parts.append(
            "Il manque encore ces informations au profil : "
            f"{', '.join(state['missing_profile_fields'])}. "
            "Obtiens-les naturellement sans transformer la réponse en questionnaire."
        )

    memories = _format_memories(state)
    if memories:
        parts.append(memories)

    mcp_context = _format_mcp_context(state)
    if mcp_context:
        parts.append(mcp_context)

    environment = _format_environment_context(state)
    if environment:
        parts.append(environment)

    health_context = _format_health_context(state)
    if health_context:
        parts.append(health_context)

    return "\n\n".join(parts)


def _intent_extra(state: CoachState) -> tuple[str, str, str | None]:
    intent = state.get("intent", "general")
    shared = _shared_extra(state)
    plan_type: str | None = None
    document_request = state.get("document_request") or {}
    incoming_message = state.get("incoming_message", "")

    extras = {
        "onboarding": (
            "L'utilisateur est encore en onboarding. Accueille-le, réponds utilement, "
            "puis demande les prochaines informations manquantes de façon naturelle."
        ),
        "safety": (
            "Priorité absolue à la sécurité. Ne donne pas de diagnostic, ne minimise pas "
            "la douleur, et recommande un professionnel de santé adapté."
        ),
        "workout": (
            "Agis comme l'architecte d'entraînement. Propose une séance adaptée au niveau, "
            "au matériel, aux contraintes, au temps disponible et à la fatigue. Pour chaque "
            "exercice, fournis un lien YouTube de démonstration au format demandé."
        ),
        "nutrition": (
            "Agis comme le chef nutrition. Donne des repas concrets avec calories, macros "
            "si utile, quantités exactes et coût estimé. Respecte allergies, préférences "
            "alimentaires et budget."
        ),
        "meal_photo": (
            "L'utilisateur a envoyé une photo de repas. Voici l'analyse vision brute :\n\n"
            f"{state.get('vision_analysis', '')}\n\n"
            "Transforme-la en retour personnalisé selon son objectif, ses contraintes et "
            "son historique. Résume calories/macros, dis si le repas est adapté, puis donne "
            "des ajustements concrets."
        ),
        "recovery": (
            "Agis comme conseiller récupération. Priorise sommeil, douleur, fatigue, "
            "gestion de charge et adaptations prudentes. Si la douleur est médicale ou "
            "inhabituelle, reste sur une recommandation de consultation."
        ),
        "checkin": (
            "Agis comme coach de check-in. Fais un bilan court, aide l'utilisateur à tirer "
            "une leçon de la journée, puis propose une prochaine action simple."
        ),
        "accountability": (
            "Agis comme agent d'accountability. Transforme l'objectif en engagement simple, "
            "mesurable et réaliste. Si un rappel ou calendrier est demandé, propose l'action "
            "mais indique qu'elle doit être confirmée avant exécution."
        ),
        "document_request": (
            "L'utilisateur demande un PDF. Tu dois générer le contenu final du PDF, "
            "pas une réponse conversationnelle et pas une explication de ce que tu vas faire.\n\n"
            f"Demande exacte de l'utilisateur : {incoming_message}\n"
            f"Type de document détecté : {document_request.get('document_type', 'coach_report')}\n"
            f"Sujet détecté : {document_request.get('subject', 'coach_summary')}\n\n"
            "Le document doit répondre directement à cette demande précise. Commence par "
            "un titre spécifique à la demande, puis crée des sections nettes avec du contenu "
            "actionnable. Évite les paragraphes génériques du type 'voici un plan'. "
            "Si le sujet est nutritionnel, inclus repas, calories, quantités, macros si utile, "
            "budget estimé, alternatives et ajustements. Si le sujet est entraînement, inclus "
            "séances, exercices, séries, répétitions, repos, progression et liens YouTube de "
            "démonstration. Si le sujet est mixte, couvre entraînement, nutrition, récupération "
            "et priorités. Le contenu sera transformé automatiquement en PDF."
        ),
        "out_of_scope": (
            "L'utilisateur demande quelque chose hors du domaine du coach fitness. "
            "Refuse brièvement et réoriente vers fitness, entraînement, nutrition, "
            "récupération, habitudes, météo sportive, Apple Health ou PDF coach."
        ),
        "morning_plan": (
            "C'est le matin. Génère un message motivant avec :\n"
            "1. Un encouragement personnalisé\n"
            "2. Le plan d'entraînement du jour avec liens YouTube pour chaque exercice\n"
            "3. Des suggestions de repas avec calories, quantités précises et prix estimé\n"
            "4. Le total calorique et le budget estimé de la journée\n"
            "5. Un conseil du jour\n"
            "Sois concis mais chaleureux."
        ),
        "evening_checkin": (
            "C'est le soir. Génère un message de check-in bienveillant pour demander :\n"
            "1. Comment s'est passée la journée\n"
            "2. Si la séance a été faite et comment ça s'est passé\n"
            "3. Si le plan alimentaire a été suivi\n"
            "4. Le niveau d'énergie et de motivation\n"
            "5. D'éventuelles douleurs ou difficultés\n"
            "Termine par un mot encourageant."
        ),
        "inactive_followup": (
            "L'utilisateur n'a pas donné de nouvelles depuis un moment. Génère une relance "
            "bienveillante pour prendre de ses nouvelles, rappeler ses objectifs, proposer "
            "une petite action simple aujourd'hui, et encourager sans culpabiliser."
        ),
        "general": (
            "Réponds comme coach généraliste. Sois concret, personnalisé, prudent et "
            "orienté action."
        ),
    }

    if intent in {"workout"}:
        plan_type = "workout"
    elif intent in {"nutrition", "meal_photo"}:
        plan_type = "nutrition"
    elif intent == "document_request":
        subject = document_request.get("subject")
        if subject == "nutrition":
            plan_type = "nutrition"
        elif subject == "workout":
            plan_type = "workout"
        else:
            plan_type = "mixed"
    elif intent == "morning_plan":
        plan_type = "mixed"

    extra = extras.get(intent, extras["general"])
    if shared:
        extra = f"{extra}\n\n{shared}"

    user_prompts = {
        "morning_plan": "Bonjour coach ! Quel est le programme aujourd'hui ?",
        "evening_checkin": "Check-in du soir",
        "inactive_followup": "Relance utilisateur inactif",
        "meal_photo": "J'ai envoyé une photo de mon repas, qu'est-ce que tu en penses coach ?",
    }
    user_prompt = user_prompts.get(intent, state.get("incoming_message", ""))
    return extra, user_prompt, plan_type


async def _run_specialist(
    state: CoachState,
    session: AsyncSession,
    llm: BaseLLMProvider,
    node_name: str,
) -> dict:
    extra, user_prompt, plan_type = _intent_extra(state)
    system_msg = build_system_prompt(
        profile=state.get("profile"),
        checkins=state.get("recent_checkins"),
        workouts=state.get("recent_workouts"),
        is_onboarding=state.get("intent") == "onboarding",
        extra_instructions=extra,
    )
    messages = [system_msg]
    for message in state.get("recent_messages", []):
        role = message.get("role")
        content = message.get("content")
        if role in {"user", "assistant", "system"} and content:
            messages.append(LLMMessage(role=role, content=content))
    messages.append(LLMMessage(role="user", content=user_prompt))

    response = await llm.chat(messages)
    pending_actions = []
    if state.get("intent") == "accountability":
        text = state.get("incoming_message", "").lower()
        if any(word in text for word in ["rappel", "rappelle", "calendrier", "remind"]):
            pending_actions.append(
                {
                    "action_type": "proposed_reminder",
                    "payload": {"request": state.get("incoming_message", "")},
                    "requires_confirmation": True,
                }
            )

    await record_event(
        session,
        state,
        node_name,
        "candidate_generated",
        {
            "intent": state.get("intent"),
            "response_length": len(response.content),
            "pending_actions": len(pending_actions),
        },
    )
    return {
        "candidate_response": response.content,
        "plan_type": plan_type,
        "pending_actions": pending_actions,
    }


async def onboarding_agent(state: CoachState, session: AsyncSession, llm: BaseLLMProvider) -> dict:
    return await _run_specialist(state, session, llm, "profile_scout_agent")


async def safety_agent(state: CoachState, session: AsyncSession, llm: BaseLLMProvider) -> dict:
    return await _run_specialist(state, session, llm, "safety_agent")


async def workout_architect(state: CoachState, session: AsyncSession, llm: BaseLLMProvider) -> dict:
    return await _run_specialist(state, session, llm, "workout_architect")


async def nutrition_chef(state: CoachState, session: AsyncSession, llm: BaseLLMProvider) -> dict:
    return await _run_specialist(state, session, llm, "nutrition_chef")


async def meal_vision_agent(state: CoachState, session: AsyncSession, llm: BaseLLMProvider) -> dict:
    return await _run_specialist(state, session, llm, "meal_vision_agent")


async def recovery_advisor(state: CoachState, session: AsyncSession, llm: BaseLLMProvider) -> dict:
    return await _run_specialist(state, session, llm, "recovery_advisor")


async def checkin_agent(state: CoachState, session: AsyncSession, llm: BaseLLMProvider) -> dict:
    return await _run_specialist(state, session, llm, "checkin_agent")


async def accountability_agent(state: CoachState, session: AsyncSession, llm: BaseLLMProvider) -> dict:
    return await _run_specialist(state, session, llm, "accountability_agent")


async def document_agent(state: CoachState, session: AsyncSession, llm: BaseLLMProvider) -> dict:
    return await _run_specialist(state, session, llm, "document_agent")


async def out_of_scope_agent(state: CoachState, session: AsyncSession, llm: BaseLLMProvider) -> dict:
    response = (
        "Je suis ton coach fitness IA, donc je ne peux pas traiter cette demande. "
        "Je peux t'aider sur l'entraînement, la nutrition, la récupération, le suivi "
        "d'habitudes, la météo pour tes séances, Apple Health ou la génération de PDF coach."
    )
    await record_event(
        session,
        state,
        "out_of_scope_agent",
        "refused",
        {"intent": state.get("intent"), "response_length": len(response)},
    )
    return {
        "candidate_response": response,
        "plan_type": None,
        "pending_actions": [],
    }


async def morning_plan_agent(state: CoachState, session: AsyncSession, llm: BaseLLMProvider) -> dict:
    return await _run_specialist(state, session, llm, "morning_plan_agent")


async def evening_checkin_agent(state: CoachState, session: AsyncSession, llm: BaseLLMProvider) -> dict:
    return await _run_specialist(state, session, llm, "evening_checkin_agent")


async def inactive_followup_agent(state: CoachState, session: AsyncSession, llm: BaseLLMProvider) -> dict:
    return await _run_specialist(state, session, llm, "inactive_followup_agent")


async def general_coach(state: CoachState, session: AsyncSession, llm: BaseLLMProvider) -> dict:
    return await _run_specialist(state, session, llm, "general_coach")
