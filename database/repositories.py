"""Data access layer for all entities."""

import datetime
from typing import Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import (
    User, UserProfile, Conversation, Message,
    WorkoutLog, NutritionLog, CheckIn,
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

