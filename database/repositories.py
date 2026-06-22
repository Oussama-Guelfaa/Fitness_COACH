"""Data access layer for all entities."""

import datetime
from typing import Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import (
    User, UserProfile, Conversation, Message,
    WorkoutLog, NutritionLog, CheckIn,
    AgentRun, AgentEvent, CoachMemory, PlanVersion,
    PendingAction, SafetyEvent, OutboxMessage,
    UserLocation, GeneratedDocument,
)


class UserRepository:
    """Handle user CRUD operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, external_id: str, platform: str = "telegram", username: str = None) -> User:
        """Get existing user or create a new one."""
        stmt = select(User).where(User.external_id == external_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            user = User(external_id=external_id, platform=platform, username=username)
            self.session.add(user)
            await self.session.flush()
            # Create empty profile
            profile = UserProfile(user_id=user.id)
            self.session.add(profile)
            await self.session.flush()
        return user

    async def get_by_external_id(self, external_id: str) -> Optional[User]:
        stmt = select(User).where(User.external_id == external_id).options(selectinload(User.profile))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> Optional[User]:
        stmt = select(User).where(User.id == user_id).options(selectinload(User.profile))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_active(self) -> list[User]:
        stmt = select(User).where(User.is_active == True)  # noqa: E712
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_last_message(self, user_id: int):
        """Update the last_message_at timestamp for a user."""
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            user.last_message_at = datetime.datetime.utcnow()
            await self.session.flush()

    async def get_inactive_users(self, hours: int = 24) -> list[User]:
        """Get active users who haven't sent a message in the given number of hours."""
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
        stmt = select(User).where(
            User.is_active == True,  # noqa: E712
            (User.last_message_at < cutoff) | (User.last_message_at == None),  # noqa: E711
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ProfileRepository:
    """Handle user profile operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: int) -> Optional[UserProfile]:
        stmt = select(UserProfile).where(UserProfile.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, user_id: int, **fields) -> UserProfile:
        """Update profile fields dynamically."""
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id)
            self.session.add(profile)
        for key, value in fields.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        profile.updated_at = datetime.datetime.utcnow()
        await self.session.flush()
        return profile


class ConversationRepository:
    """Handle conversation and message operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_active(self, user_id: int, context_type: str = "general") -> Conversation:
        """Get the most recent conversation or create one."""
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id, Conversation.context_type == context_type)
            .order_by(desc(Conversation.started_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        conv = result.scalar_one_or_none()
        if conv is None:
            conv = Conversation(user_id=user_id, context_type=context_type)
            self.session.add(conv)
            await self.session.flush()
        return conv

    async def add_message(self, conversation_id: int, role: str, content: str, metadata: dict = None) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata_json=metadata,
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def get_recent_messages(self, conversation_id: int, limit: int = 20) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(desc(Message.created_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        messages = list(result.scalars().all())
        messages.reverse()  # chronological order
        return messages


class TrackingRepository:
    """Handle workout logs, nutrition logs, and check-ins."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_workout_log(self, user_id: int, **fields) -> WorkoutLog:
        log = WorkoutLog(user_id=user_id, **fields)
        self.session.add(log)
        await self.session.flush()
        return log

    async def add_nutrition_log(self, user_id: int, **fields) -> NutritionLog:
        log = NutritionLog(user_id=user_id, **fields)
        self.session.add(log)
        await self.session.flush()
        return log

    async def add_checkin(self, user_id: int, **fields) -> CheckIn:
        checkin = CheckIn(user_id=user_id, **fields)
        self.session.add(checkin)
        await self.session.flush()
        return checkin

    async def get_recent_checkins(self, user_id: int, limit: int = 7) -> list[CheckIn]:
        stmt = (
            select(CheckIn)
            .where(CheckIn.user_id == user_id)
            .order_by(desc(CheckIn.date))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())
        items.reverse()
        return items

    async def get_recent_workouts(self, user_id: int, limit: int = 7) -> list[WorkoutLog]:
        stmt = (
            select(WorkoutLog)
            .where(WorkoutLog.user_id == user_id)
            .order_by(desc(WorkoutLog.date))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())
        items.reverse()
        return items

    async def get_recent_nutrition(self, user_id: int, limit: int = 7) -> list[NutritionLog]:
        stmt = (
            select(NutritionLog)
            .where(NutritionLog.user_id == user_id)
            .order_by(desc(NutritionLog.date))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())
        items.reverse()
        return items


class AgentRepository:
    """Persistence for agent graph traces, durable memory, and outbound messages."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_run(
        self,
        user_id: int,
        run_type: str,
        workflow: str,
        thread_id: str,
        input_preview: str = "",
        metadata: dict | None = None,
    ) -> AgentRun:
        run = AgentRun(
            user_id=user_id,
            run_type=run_type,
            workflow=workflow,
            thread_id=thread_id,
            input_preview=input_preview[:1000] if input_preview else None,
            metadata_json=metadata,
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def add_event(
        self,
        run_id: int,
        user_id: int,
        node: str,
        event_type: str,
        payload: dict | None = None,
    ) -> AgentEvent:
        event = AgentEvent(
            run_id=run_id,
            user_id=user_id,
            node=node,
            event_type=event_type,
            payload_json=payload,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def complete_run(
        self,
        run_id: int,
        intent: str | None,
        output_preview: str,
        status: str = "completed",
        error: str | None = None,
    ):
        stmt = select(AgentRun).where(AgentRun.id == run_id)
        result = await self.session.execute(stmt)
        run = result.scalar_one_or_none()
        if run:
            run.intent = intent
            run.output_preview = output_preview[:1000] if output_preview else None
            run.status = status
            run.error = error
            run.completed_at = datetime.datetime.utcnow()
            await self.session.flush()

    async def fail_run(self, run_id: int, error: str):
        await self.complete_run(
            run_id=run_id,
            intent=None,
            output_preview="",
            status="failed",
            error=error[:2000],
        )

    async def get_recent_memories(
        self,
        user_id: int,
        memory_type: str = "fitness_twin",
        limit: int = 20,
    ) -> list[CoachMemory]:
        stmt = (
            select(CoachMemory)
            .where(
                CoachMemory.user_id == user_id,
                CoachMemory.memory_type == memory_type,
                CoachMemory.is_active == True,  # noqa: E712
            )
            .order_by(desc(CoachMemory.updated_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_memory(
        self,
        user_id: int,
        memory_key: str,
        content: str,
        memory_type: str = "fitness_twin",
        confidence: float = 1.0,
        source_run_id: int | None = None,
    ) -> CoachMemory:
        stmt = select(CoachMemory).where(
            CoachMemory.user_id == user_id,
            CoachMemory.memory_type == memory_type,
            CoachMemory.memory_key == memory_key,
        )
        result = await self.session.execute(stmt)
        memory = result.scalar_one_or_none()
        if memory is None:
            memory = CoachMemory(
                user_id=user_id,
                memory_type=memory_type,
                memory_key=memory_key,
                content=content,
                confidence=confidence,
                source_run_id=source_run_id,
            )
            self.session.add(memory)
        else:
            memory.content = content
            memory.confidence = confidence
            memory.source_run_id = source_run_id
            memory.is_active = True
            memory.updated_at = datetime.datetime.utcnow()
        await self.session.flush()
        return memory

    async def create_plan_version(
        self,
        user_id: int,
        plan_type: str,
        content: str,
        title: str | None = None,
        source_run_id: int | None = None,
    ) -> PlanVersion:
        stmt = (
            select(PlanVersion)
            .where(PlanVersion.user_id == user_id, PlanVersion.plan_type == plan_type)
            .order_by(desc(PlanVersion.version))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        latest = result.scalar_one_or_none()
        version = (latest.version + 1) if latest else 1
        plan = PlanVersion(
            user_id=user_id,
            plan_type=plan_type,
            title=title,
            content=content,
            version=version,
            source_run_id=source_run_id,
        )
        self.session.add(plan)
        await self.session.flush()
        return plan

    async def create_pending_action(
        self,
        user_id: int,
        action_type: str,
        payload: dict | None = None,
        requires_confirmation: bool = True,
        due_at: datetime.datetime | None = None,
    ) -> PendingAction:
        action = PendingAction(
            user_id=user_id,
            action_type=action_type,
            payload_json=payload,
            requires_confirmation=requires_confirmation,
            due_at=due_at,
        )
        self.session.add(action)
        await self.session.flush()
        return action

    async def create_safety_event(
        self,
        user_id: int,
        run_id: int | None,
        concerns: dict,
        message_excerpt: str,
        severity: str = "caution",
    ) -> SafetyEvent:
        event = SafetyEvent(
            user_id=user_id,
            run_id=run_id,
            severity=severity,
            concerns_json=concerns,
            message_excerpt=message_excerpt[:1000] if message_excerpt else None,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def create_outbox_message(
        self,
        user_id: int,
        external_id: str,
        platform: str,
        body: str,
        source_run_id: int | None = None,
        status: str = "returned",
        channel: str = "chat",
    ) -> OutboxMessage:
        message = OutboxMessage(
            user_id=user_id,
            external_id=external_id,
            platform=platform,
            channel=channel,
            body=body,
            status=status,
            source_run_id=source_run_id,
        )
        self.session.add(message)
        await self.session.flush()
        return message


class LocationRepository:
    """Store and retrieve user-consented location data."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def set_active_location(
        self,
        user_id: int,
        latitude: float,
        longitude: float,
        label: str | None = None,
        timezone: str | None = None,
        country: str | None = None,
        admin_area: str | None = None,
        consent_source: str = "user_shared",
    ) -> UserLocation:
        current = await self.get_active_location(user_id)
        if current:
            current.is_active = False
        location = UserLocation(
            user_id=user_id,
            latitude=latitude,
            longitude=longitude,
            label=label,
            timezone=timezone,
            country=country,
            admin_area=admin_area,
            consent_source=consent_source,
        )
        self.session.add(location)
        await self.session.flush()
        return location

    async def get_active_location(self, user_id: int) -> UserLocation | None:
        stmt = (
            select(UserLocation)
            .where(
                UserLocation.user_id == user_id,
                UserLocation.is_active == True,  # noqa: E712
            )
            .order_by(desc(UserLocation.updated_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class DocumentRepository:
    """Store generated document metadata."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_document(
        self,
        user_id: int,
        document_type: str,
        title: str,
        file_path: str,
        source_run_id: int | None = None,
        metadata: dict | None = None,
    ) -> GeneratedDocument:
        document = GeneratedDocument(
            user_id=user_id,
            document_type=document_type,
            title=title,
            file_path=file_path,
            source_run_id=source_run_id,
            metadata_json=metadata,
        )
        self.session.add(document)
        await self.session.flush()
        return document
