"""Core coaching engine — orchestrates profile, LLM, and tracking."""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from llm.base import BaseLLMProvider, LLMMessage
from llm.prompt_builder import build_system_prompt
from llm.vision_provider import analyze_image_gemini
from agents.runtime import CoachAgentRuntime
from database.repositories import (
    UserRepository, ProfileRepository, ConversationRepository, TrackingRepository,
)
from coaching.profile_manager import ProfileManager
from coaching.safety import get_safety_instructions, has_safety_concern, SAFETY_WARNING

logger = structlog.get_logger()


class CoachingEngine:
    """Main engine that handles user interactions and coordinates all components."""

    def __init__(self, llm: BaseLLMProvider):
        self.llm = llm
        self.profile_manager = ProfileManager(llm)
        self.agent_runtime = CoachAgentRuntime(llm, self.profile_manager)

    async def handle_message(
        self, session: AsyncSession, external_id: str, user_message: str,
        platform: str = "telegram", username: str = None,
    ) -> str:
        """Process a user message through the agent graph and return the coach's response."""
        try:
            reply = await self.agent_runtime.handle_user_message(
                session=session,
                external_id=external_id,
                user_message=user_message,
                platform=platform,
                username=username,
            )
            await session.commit()
            return reply
        except Exception as e:
            await session.rollback()
            logger.exception("Agent runtime failed; falling back to legacy engine", error=str(e))
            return await self._handle_message_legacy(
                session=session,
                external_id=external_id,
                user_message=user_message,
                platform=platform,
                username=username,
            )

    async def _handle_message_legacy(
        self, session: AsyncSession, external_id: str, user_message: str,
        platform: str = "telegram", username: str = None,
    ) -> str:
        """Process a user message and return the coach's response."""
        user_repo = UserRepository(session)
        profile_repo = ProfileRepository(session)
        conv_repo = ConversationRepository(session)
        tracking_repo = TrackingRepository(session)

        # 1. Get or create user
        user = await user_repo.get_or_create(external_id, platform, username)
        profile = await profile_repo.get_by_user_id(user.id)

        # 2. Check profile completeness
        is_complete, missing = self.profile_manager.check_profile_completeness(profile)
        is_onboarding = not is_complete

        # 3. Try to extract profile data from the message
        updates = await self.profile_manager.extract_profile_updates(user_message)
        if updates:
            profile = await profile_repo.update(user.id, **updates)
            is_complete, missing = self.profile_manager.check_profile_completeness(profile)
            logger.info("Profile updated", user_id=user.id, fields=list(updates.keys()))

        # 4. Get conversation history
        conv = await conv_repo.get_or_create_active(user.id)
        recent_messages = await conv_repo.get_recent_messages(conv.id, limit=15)

        # 5. Get tracking data for context
        checkins = await tracking_repo.get_recent_checkins(user.id)
        workouts = await tracking_repo.get_recent_workouts(user.id)

        # 6. Check safety concerns
        safety_instructions = get_safety_instructions(user_message)
        extra = ""
        if safety_instructions:
            extra = safety_instructions
        elif is_onboarding and missing:
            extra = (
                f"Il manque encore ces informations au profil : {', '.join(missing)}. "
                "Essaie de les obtenir de manière naturelle dans la conversation."
            )

        # 7. Build system prompt
        system_msg = build_system_prompt(
            profile=profile,
            checkins=checkins,
            workouts=workouts,
            is_onboarding=is_onboarding,
            extra_instructions=extra,
        )

        # 8. Build message list for LLM
        llm_messages = [system_msg]
        for msg in recent_messages:
            llm_messages.append(LLMMessage(role=msg.role, content=msg.content))
        llm_messages.append(LLMMessage(role="user", content=user_message))

        # 9. Call LLM
        response = await self.llm.chat(llm_messages)
        assistant_reply = response.content

        # 10. Prepend safety warning if needed
        if has_safety_concern(user_message):
            assistant_reply = f"{SAFETY_WARNING}\n\n{assistant_reply}"

        # 11. Save messages
        await conv_repo.add_message(conv.id, "user", user_message)
        await conv_repo.add_message(conv.id, "assistant", assistant_reply)

        # 12. Update profile completeness flag
        if is_complete and profile and not profile.profile_complete:
            await profile_repo.update(user.id, profile_complete=True)

        # 13. Track user activity for follow-up
        await user_repo.update_last_message(user.id)

        await session.commit()
        return assistant_reply

    async def generate_morning_message(self, session: AsyncSession, user_id: int) -> str:
        """Generate the morning motivation/plan message."""
        try:
            return await self.agent_runtime.generate_scheduled_message(
                session=session,
                user_id=user_id,
                workflow="morning_plan",
            )
        except Exception as e:
            await session.rollback()
            logger.exception("Morning agent workflow failed; falling back to legacy prompt", error=str(e))

        profile_repo = ProfileRepository(session)
        tracking_repo = TrackingRepository(session)

        profile = await profile_repo.get_by_user_id(user_id)
        checkins = await tracking_repo.get_recent_checkins(user_id)
        workouts = await tracking_repo.get_recent_workouts(user_id)

        system_msg = build_system_prompt(
            profile=profile, checkins=checkins, workouts=workouts,
            extra_instructions=(
                "C'est le matin. Génère un message motivant avec :\n"
                "1. Un message d'encouragement personnalisé\n"
                "2. Le plan d'entraînement du jour (si prévu) avec des liens YouTube pour chaque exercice\n"
                "3. Des suggestions de repas pour la journée avec calories, quantités précises et prix estimé\n"
                "4. Le total calorique et le budget estimé de la journée\n"
                "5. Un conseil du jour\n"
                "Sois concis mais chaleureux."
            ),
        )
        user_msg = LLMMessage(role="user", content="Bonjour coach ! Quel est le programme aujourd'hui ?")
        response = await self.llm.chat([system_msg, user_msg])
        return response.content

    async def generate_evening_checkin(self, session: AsyncSession, user_id: int) -> str:
        """Generate the evening check-in message."""
        try:
            return await self.agent_runtime.generate_scheduled_message(
                session=session,
                user_id=user_id,
                workflow="evening_checkin",
            )
        except Exception as e:
            await session.rollback()
            logger.exception("Evening agent workflow failed; falling back to legacy prompt", error=str(e))

        profile_repo = ProfileRepository(session)
        tracking_repo = TrackingRepository(session)

        profile = await profile_repo.get_by_user_id(user_id)
        workouts = await tracking_repo.get_recent_workouts(user_id)

        system_msg = build_system_prompt(
            profile=profile, workouts=workouts,
            extra_instructions=(
                "C'est le soir. Génère un message de check-in bienveillant pour demander :\n"
                "1. Comment s'est passée la journée\n"
                "2. Si la séance a été faite (et comment ça s'est passé)\n"
                "3. Si le plan alimentaire a été suivi\n"
                "4. Le niveau d'énergie et de motivation\n"
                "5. D'éventuelles douleurs ou difficultés\n"
                "Termine par un mot encourageant."
            ),
        )
        user_msg = LLMMessage(role="user", content="Check-in du soir")
        response = await self.llm.chat([system_msg, user_msg])
        return response.content

    async def generate_followup_message(self, session: AsyncSession, user_id: int) -> str:
        """Generate a follow-up/relance message for an inactive user."""
        try:
            return await self.agent_runtime.generate_scheduled_message(
                session=session,
                user_id=user_id,
                workflow="inactive_followup",
            )
        except Exception as e:
            await session.rollback()
            logger.exception("Follow-up agent workflow failed; falling back to legacy prompt", error=str(e))

        profile_repo = ProfileRepository(session)
        tracking_repo = TrackingRepository(session)

        profile = await profile_repo.get_by_user_id(user_id)
        workouts = await tracking_repo.get_recent_workouts(user_id)

        system_msg = build_system_prompt(
            profile=profile, workouts=workouts,
            extra_instructions=(
                "L'utilisateur n'a pas donné de nouvelles depuis un moment.\n"
                "Génère un message de relance bienveillant et motivant pour :\n"
                "1. Prendre de ses nouvelles\n"
                "2. Lui rappeler ses objectifs\n"
                "3. Lui proposer une petite action simple à faire aujourd'hui\n"
                "4. L'encourager sans culpabiliser\n"
                "Sois chaleureux et compréhensif. Pas de jugement."
            ),
        )
        user_msg = LLMMessage(role="user", content="Relance utilisateur inactif")
        response = await self.llm.chat([system_msg, user_msg])
        return response.content

    async def analyze_meal_photo(
        self, session: AsyncSession, external_id: str,
        image_bytes: bytes, mime_type: str = "image/jpeg",
        platform: str = "telegram", username: str = None,
    ) -> str:
        """Analyze a meal photo and return nutritional information.

        1. Gemini Vision analyses the photo (raw nutritional data).
        2. The analysis is injected into the conversation history.
        3. DeepSeek generates a personalised coaching response using
           the vision analysis + user profile as context.
        """
        user_repo = UserRepository(session)
        profile_repo = ProfileRepository(session)
        conv_repo = ConversationRepository(session)
        tracking_repo = TrackingRepository(session)

        # Track user activity
        user = await user_repo.get_or_create(external_id, platform, username)
        await user_repo.update_last_message(user.id)

        # 1. Call vision API for raw analysis
        vision_analysis = await analyze_image_gemini(image_bytes, mime_type)

        # If vision failed (error message), return it directly
        if vision_analysis.startswith("⚠️") or vision_analysis.startswith("❌"):
            return vision_analysis

        try:
            coaching_reply = await self.agent_runtime.handle_meal_analysis(
                session=session,
                external_id=external_id,
                vision_analysis=vision_analysis,
                mime_type=mime_type,
                platform=platform,
                username=username,
            )
            await session.commit()
            logger.info("Meal photo analyzed through agent runtime", user_id=user.id)
            return coaching_reply
        except Exception as e:
            await session.rollback()
            logger.exception("Meal-photo agent workflow failed; falling back to legacy flow", error=str(e))
            user_repo = UserRepository(session)
            profile_repo = ProfileRepository(session)
            conv_repo = ConversationRepository(session)
            tracking_repo = TrackingRepository(session)
            user = await user_repo.get_or_create(external_id, platform, username)
            await user_repo.update_last_message(user.id)

        # 2. Save vision analysis in conversation history so DeepSeek sees it
        conv = await conv_repo.get_or_create_active(user.id)
        await conv_repo.add_message(
            conv.id, "user",
            "[📷 L'utilisateur a envoyé une photo de son repas]"
        )
        await conv_repo.add_message(
            conv.id, "assistant",
            f"[Analyse nutritionnelle du repas par vision IA]\n\n{vision_analysis}"
        )

        # 3. Build context for DeepSeek to give personalised coaching feedback
        profile = await profile_repo.get_by_user_id(user.id)
        checkins = await tracking_repo.get_recent_checkins(user.id)
        workouts = await tracking_repo.get_recent_workouts(user.id)

        system_msg = build_system_prompt(
            profile=profile,
            checkins=checkins,
            workouts=workouts,
            extra_instructions=(
                "L'utilisateur vient d'envoyer une photo de son repas. "
                "Voici l'analyse nutritionnelle faite par l'IA vision :\n\n"
                f"{vision_analysis}\n\n"
                "En te basant sur cette analyse ET le profil de l'utilisateur "
                "(objectifs, poids, niveau, contraintes alimentaires, budget…), "
                "donne un retour personnalisé :\n"
                "1. Résume l'analyse (calories, macros, note)\n"
                "2. Dis si ce repas est adapté à ses objectifs\n"
                "3. Propose des ajustements concrets si nécessaire\n"
                "4. Encourage-le\n"
                "Sois concis, bienveillant et utilise des emojis."
            ),
        )

        user_msg = LLMMessage(
            role="user",
            content="J'ai envoyé une photo de mon repas, qu'est-ce que tu en penses coach ?"
        )
        response = await self.llm.chat([system_msg, user_msg])
        coaching_reply = response.content

        # Save the coaching reply too
        await conv_repo.add_message(conv.id, "assistant", coaching_reply)

        await session.commit()
        logger.info("Meal photo analyzed and coaching feedback generated", user_id=user.id)
        return coaching_reply
