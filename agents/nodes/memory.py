"""Memory curator and outbox persistence node."""

from sqlalchemy.ext.asyncio import AsyncSession

from agents.nodes.events import record_event
from agents.state import CoachState
from database.repositories import (
    AgentRepository,
    ConversationRepository,
    ProfileRepository,
    UserRepository,
)


async def memory_curator(state: CoachState, session: AsyncSession) -> dict:
    """Persist conversation messages, fitness-twin memories, plans, pending actions, and outbox."""
    agent_repo = AgentRepository(session)
    conv_repo = ConversationRepository(session)
    profile_repo = ProfileRepository(session)
    user_repo = UserRepository(session)

    final_response = state.get("final_response", "")
    workflow = state.get("workflow", "user_message")
    intent = state.get("intent", "general")

    if workflow in {"user_message", "meal_photo"}:
        conversation_id = state["conversation_id"]
        user_content = state.get("incoming_message") or "[L'utilisateur a envoyé une photo de repas]"
        await conv_repo.add_message(conversation_id, "user", user_content)
        if state.get("vision_analysis"):
            await conv_repo.add_message(
                conversation_id,
                "assistant",
                f"[Analyse nutritionnelle du repas par vision IA]\n\n{state['vision_analysis']}",
                metadata={"source": "vision"},
            )
        await conv_repo.add_message(
            conversation_id,
            "assistant",
            final_response,
            metadata={"agent_run_id": state.get("run_id"), "intent": intent},
        )
        await user_repo.update_last_message(state["user_id"])

    updates = state.get("extracted_profile_updates", {})
    memory_updates = []
    for key, value in updates.items():
        memory_key = f"profile.{key}"
        await agent_repo.upsert_memory(
            user_id=state["user_id"],
            memory_key=memory_key,
            content=str(value),
            source_run_id=state.get("run_id"),
        )
        memory_updates.append({"memory_key": memory_key, "content": str(value)})

    if not state.get("is_onboarding"):
        profile = state.get("profile") or {}
        if profile and not profile.get("profile_complete"):
            await profile_repo.update(state["user_id"], profile_complete=True)

    if state.get("plan_type") and final_response:
        await agent_repo.create_plan_version(
            user_id=state["user_id"],
            plan_type=state["plan_type"] or "mixed",
            content=final_response,
            title=f"{intent.replace('_', ' ').title()}",
            source_run_id=state.get("run_id"),
        )

    for action in state.get("pending_actions", []):
        await agent_repo.create_pending_action(
            user_id=state["user_id"],
            action_type=action.get("action_type", "unknown"),
            payload=action.get("payload"),
            requires_confirmation=action.get("requires_confirmation", True),
        )

    await agent_repo.create_outbox_message(
        user_id=state["user_id"],
        external_id=state["external_id"],
        platform=state.get("platform", "telegram"),
        body=final_response,
        source_run_id=state.get("run_id"),
        status="returned" if workflow in {"user_message", "meal_photo"} else "generated",
    )

    await agent_repo.complete_run(
        run_id=state["run_id"],
        intent=intent,
        output_preview=final_response,
        status="completed",
    )
    await record_event(
        session,
        state,
        "memory_curator",
        "persisted",
        {
            "workflow": workflow,
            "memory_updates": len(memory_updates),
            "pending_actions": len(state.get("pending_actions", [])),
        },
    )
    return {"memory_updates": memory_updates}
