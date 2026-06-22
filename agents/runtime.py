"""Agentic coach runtime.

This module is the compatibility seam between the existing application and the
new LangGraph-style agent architecture.
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agents.nodes.composer import response_composer
from agents.nodes.critic import coach_critic
from agents.nodes.document import document_generator
from agents.nodes.hydrator import hydrate_state
from agents.nodes.mcp_context import load_mcp_context
from agents.nodes.memory import memory_curator
from agents.nodes.profile import profile_scout
from agents.nodes.router import intent_router, route_to_specialist
from agents.nodes.safety import safety_sentinel
from agents.nodes.specialists import (
    accountability_agent,
    checkin_agent,
    evening_checkin_agent,
    general_coach,
    inactive_followup_agent,
    meal_vision_agent,
    morning_plan_agent,
    nutrition_chef,
    onboarding_agent,
    document_agent,
    recovery_advisor,
    safety_agent,
    workout_architect,
)
from agents.state import CoachState
from agents.tools.mcp_gateway import MCPGateway
from coaching.profile_manager import ProfileManager
from database.repositories import AgentRepository, UserRepository
from llm.base import BaseLLMProvider

logger = structlog.get_logger()


class CoachAgentRuntime:
    """Runs the bounded specialist-agent graph for coach interactions."""

    def __init__(
        self,
        llm: BaseLLMProvider,
        profile_manager: ProfileManager,
        mcp_gateway: MCPGateway | None = None,
    ):
        self.llm = llm
        self.profile_manager = profile_manager
        self.mcp_gateway = mcp_gateway or MCPGateway()
        self._langgraph_available = self._check_langgraph_available()
        self.last_result: CoachState | None = None
        self.last_generated_document_path: str | None = None

    @staticmethod
    def _check_langgraph_available() -> bool:
        try:
            import langgraph  # noqa: F401
            return True
        except ImportError:
            logger.warning("LangGraph is not installed; using linear fallback runner")
            return False

    async def _start_run(
        self,
        session: AsyncSession,
        workflow: str,
        run_type: str,
        incoming_message: str = "",
        external_id: str | None = None,
        platform: str = "telegram",
        username: str | None = None,
        user_id: int | None = None,
        metadata: dict | None = None,
    ) -> CoachState:
        user_repo = UserRepository(session)
        if user_id is not None:
            user = await user_repo.get_by_id(user_id)
            if user is None:
                raise ValueError(f"Unknown user_id for agent run: {user_id}")
        else:
            if external_id is None:
                raise ValueError("external_id is required when user_id is not provided")
            user = await user_repo.get_or_create(external_id, platform, username)

        thread_id = f"{user.platform}:{user.external_id}:{workflow}"
        run = await AgentRepository(session).create_run(
            user_id=user.id,
            run_type=run_type,
            workflow=workflow,
            thread_id=thread_id,
            input_preview=incoming_message,
            metadata=metadata,
        )
        return {
            "run_id": run.id,
            "run_type": run_type,
            "workflow": workflow,
            "thread_id": thread_id,
            "user_id": user.id,
            "external_id": user.external_id,
            "platform": user.platform,
            "username": user.username,
            "incoming_message": incoming_message,
            "critic_findings": [],
            "pending_actions": [],
            "memory_updates": [],
            "plan_type": None,
        }

    def _compile_graph(self, session: AsyncSession):
        from langgraph.graph import END, START, StateGraph

        builder = StateGraph(CoachState)

        async def _hydrate(state: CoachState):
            return await hydrate_state(state, session, self.profile_manager)

        async def _safety(state: CoachState):
            return await safety_sentinel(state, session)

        async def _profile(state: CoachState):
            return await profile_scout(state, session, self.profile_manager)

        async def _router(state: CoachState):
            return await intent_router(state, session)

        async def _mcp(state: CoachState):
            return await load_mcp_context(state, session, self.mcp_gateway)

        async def _onboarding(state: CoachState):
            return await onboarding_agent(state, session, self.llm)

        async def _safety_agent(state: CoachState):
            return await safety_agent(state, session, self.llm)

        async def _workout(state: CoachState):
            return await workout_architect(state, session, self.llm)

        async def _nutrition(state: CoachState):
            return await nutrition_chef(state, session, self.llm)

        async def _meal_photo(state: CoachState):
            return await meal_vision_agent(state, session, self.llm)

        async def _recovery(state: CoachState):
            return await recovery_advisor(state, session, self.llm)

        async def _checkin(state: CoachState):
            return await checkin_agent(state, session, self.llm)

        async def _accountability(state: CoachState):
            return await accountability_agent(state, session, self.llm)

        async def _document_agent(state: CoachState):
            return await document_agent(state, session, self.llm)

        async def _morning(state: CoachState):
            return await morning_plan_agent(state, session, self.llm)

        async def _evening(state: CoachState):
            return await evening_checkin_agent(state, session, self.llm)

        async def _inactive(state: CoachState):
            return await inactive_followup_agent(state, session, self.llm)

        async def _general(state: CoachState):
            return await general_coach(state, session, self.llm)

        async def _critic(state: CoachState):
            return await coach_critic(state, session)

        async def _composer(state: CoachState):
            return await response_composer(state, session)

        async def _document(state: CoachState):
            return await document_generator(state, session)

        async def _memory(state: CoachState):
            return await memory_curator(state, session)

        builder.add_node("memory_hydrator", _hydrate)
        builder.add_node("safety_sentinel", _safety)
        builder.add_node("profile_scout", _profile)
        builder.add_node("intent_router", _router)
        builder.add_node("mcp_gateway", _mcp)

        specialist_nodes = {
            "onboarding": _onboarding,
            "safety": _safety_agent,
            "workout": _workout,
            "nutrition": _nutrition,
            "meal_photo": _meal_photo,
            "recovery": _recovery,
            "checkin": _checkin,
            "accountability": _accountability,
            "document_request": _document_agent,
            "morning_plan": _morning,
            "evening_checkin": _evening,
            "inactive_followup": _inactive,
            "general": _general,
        }
        for name, node in specialist_nodes.items():
            builder.add_node(name, node)
            builder.add_edge(name, "coach_critic")

        builder.add_node("coach_critic", _critic)
        builder.add_node("response_composer", _composer)
        builder.add_node("document_generator", _document)
        builder.add_node("memory_curator", _memory)

        builder.add_edge(START, "memory_hydrator")
        builder.add_edge("memory_hydrator", "safety_sentinel")
        builder.add_edge("safety_sentinel", "profile_scout")
        builder.add_edge("profile_scout", "intent_router")
        builder.add_edge("intent_router", "mcp_gateway")
        builder.add_conditional_edges(
            "mcp_gateway",
            route_to_specialist,
            {name: name for name in specialist_nodes},
        )
        builder.add_edge("coach_critic", "response_composer")
        builder.add_edge("response_composer", "document_generator")
        builder.add_edge("document_generator", "memory_curator")
        builder.add_edge("memory_curator", END)
        return builder.compile()

    async def _run_linear(self, state: CoachState, session: AsyncSession) -> CoachState:
        """Manual runner used only when LangGraph is not importable."""
        for step in (
            lambda s: hydrate_state(s, session, self.profile_manager),
            lambda s: safety_sentinel(s, session),
            lambda s: profile_scout(s, session, self.profile_manager),
            lambda s: intent_router(s, session),
            lambda s: load_mcp_context(s, session, self.mcp_gateway),
        ):
            state.update(await step(state))

        specialists = {
            "onboarding": onboarding_agent,
            "safety": safety_agent,
            "workout": workout_architect,
            "nutrition": nutrition_chef,
            "meal_photo": meal_vision_agent,
            "recovery": recovery_advisor,
            "checkin": checkin_agent,
            "accountability": accountability_agent,
            "document_request": document_agent,
            "morning_plan": morning_plan_agent,
            "evening_checkin": evening_checkin_agent,
            "inactive_followup": inactive_followup_agent,
            "general": general_coach,
        }
        specialist = specialists.get(state.get("intent", "general"), general_coach)
        state.update(await specialist(state, session, self.llm))
        state.update(await coach_critic(state, session))
        state.update(await response_composer(state, session))
        state.update(await document_generator(state, session))
        state.update(await memory_curator(state, session))
        return state

    async def _invoke(self, session: AsyncSession, state: CoachState) -> CoachState:
        try:
            if self._langgraph_available:
                graph = self._compile_graph(session)
                result = await graph.ainvoke(
                    state,
                    {"configurable": {"thread_id": state["thread_id"]}},
                )
            else:
                result = await self._run_linear(state, session)
            self.last_result = result
            self.last_generated_document_path = result.get("generated_document_path")
            return result
        except Exception as exc:
            logger.exception("Agent graph failed", run_id=state.get("run_id"))
            if state.get("run_id"):
                await AgentRepository(session).fail_run(state["run_id"], str(exc))
            raise

    async def handle_user_message(
        self,
        session: AsyncSession,
        external_id: str,
        user_message: str,
        platform: str = "telegram",
        username: str | None = None,
    ) -> str:
        state = await self._start_run(
            session=session,
            workflow="user_message",
            run_type="message",
            incoming_message=user_message,
            external_id=external_id,
            platform=platform,
            username=username,
        )
        result = await self._invoke(session, state)
        return result["final_response"]

    async def handle_meal_analysis(
        self,
        session: AsyncSession,
        external_id: str,
        vision_analysis: str,
        mime_type: str,
        platform: str = "telegram",
        username: str | None = None,
    ) -> str:
        state = await self._start_run(
            session=session,
            workflow="meal_photo",
            run_type="meal_photo",
            incoming_message="[L'utilisateur a envoyé une photo de son repas]",
            external_id=external_id,
            platform=platform,
            username=username,
            metadata={"mime_type": mime_type},
        )
        state["vision_analysis"] = vision_analysis
        state["image_mime_type"] = mime_type
        result = await self._invoke(session, state)
        return result["final_response"]

    async def generate_scheduled_message(
        self,
        session: AsyncSession,
        user_id: int,
        workflow: str,
    ) -> str:
        if workflow not in {"morning_plan", "evening_checkin", "inactive_followup"}:
            raise ValueError(f"Unsupported scheduled workflow: {workflow}")
        state = await self._start_run(
            session=session,
            workflow=workflow,
            run_type="scheduled",
            incoming_message=workflow,
            user_id=user_id,
        )
        result = await self._invoke(session, state)
        return result["final_response"]
