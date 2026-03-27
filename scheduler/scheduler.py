"""Scheduled tasks — morning messages and evening check-ins."""

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from coaching.engine import CoachingEngine
from database.database import get_session
from database.repositories import UserRepository
from config.settings import get_settings

logger = structlog.get_logger()

_scheduler: AsyncIOScheduler | None = None
_engine: CoachingEngine | None = None
_send_message_callback = None


def set_send_callback(callback):
    """Set the callback function to send messages to users.

    The callback should accept (external_id: str, platform: str, message: str).
    """
    global _send_message_callback
    _send_message_callback = callback


async def _send_to_all_users(message_generator):
    """Send a generated message to all active users."""
    if not _engine or not _send_message_callback:
        logger.warning("Engine or send callback not configured")
        return

    session = await get_session()
    try:
        user_repo = UserRepository(session)
        users = await user_repo.get_all_active()

        for user in users:
            try:
                message = await message_generator(session, user.id)
                await _send_message_callback(user.external_id, user.platform, message)
                logger.info("Scheduled message sent", user_id=user.id, type=message_generator.__name__)
            except Exception as e:
                logger.error("Failed to send scheduled message", user_id=user.id, error=str(e))

        await session.commit()
    finally:
        await session.close()


async def morning_job():
    """Morning message job."""
    logger.info("Running morning job")
    await _send_to_all_users(_engine.generate_morning_message)


async def evening_job():
    """Evening check-in job."""
    logger.info("Running evening job")
    await _send_to_all_users(_engine.generate_evening_checkin)


async def followup_job():
    """Follow-up job for users who haven't responded."""
    if not _engine or not _send_message_callback:
        logger.warning("Engine or send callback not configured for followup")
        return

    session = await get_session()
    try:
        user_repo = UserRepository(session)
        inactive_users = await user_repo.get_inactive_users(hours=24)

        for user in inactive_users:
            try:
                message = await _engine.generate_followup_message(session, user.id)
                await _send_message_callback(user.external_id, user.platform, message)
                logger.info("Follow-up message sent", user_id=user.id)
            except Exception as e:
                logger.error("Failed to send follow-up", user_id=user.id, error=str(e))

        await session.commit()
    finally:
        await session.close()


def create_scheduler(engine: CoachingEngine) -> AsyncIOScheduler:
    """Create and configure the scheduler."""
    global _scheduler, _engine
    _engine = engine
    settings = get_settings().scheduler

    _scheduler = AsyncIOScheduler()

    # Morning message
    _scheduler.add_job(
        morning_job,
        trigger=CronTrigger(
            hour=settings.morning_hour,
            minute=settings.morning_minute,
            timezone=settings.timezone,
        ),
        id="morning_message",
        name="Message du matin",
        replace_existing=True,
    )

    # Evening check-in
    _scheduler.add_job(
        evening_job,
        trigger=CronTrigger(
            hour=settings.evening_hour,
            minute=settings.evening_minute,
            timezone=settings.timezone,
        ),
        id="evening_checkin",
        name="Check-in du soir",
        replace_existing=True,
    )

    # Follow-up for inactive users — runs at 14h every day
    _scheduler.add_job(
        followup_job,
        trigger=CronTrigger(
            hour=14,
            minute=0,
            timezone=settings.timezone,
        ),
        id="followup_inactive",
        name="Relance utilisateurs inactifs",
        replace_existing=True,
    )

    logger.info(
        "Scheduler configured",
        morning=f"{settings.morning_hour}:{settings.morning_minute:02d}",
        evening=f"{settings.evening_hour}:{settings.evening_minute:02d}",
        timezone=settings.timezone,
    )
    return _scheduler


def start_scheduler():
    """Start the scheduler."""
    if _scheduler and not _scheduler.running:
        _scheduler.start()
        logger.info("Scheduler started")


def stop_scheduler():
    """Stop the scheduler."""
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        logger.info("Scheduler stopped")

