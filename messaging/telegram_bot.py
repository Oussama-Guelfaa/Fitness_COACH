"""Telegram bot interface for the fitness coach."""

import structlog
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from coaching.engine import CoachingEngine
from database.database import get_session, init_db
from database.repositories import UserRepository
from config.settings import get_settings

logger = structlog.get_logger()

# Global engine reference — set during startup
_engine: CoachingEngine | None = None


def set_engine(engine: CoachingEngine):
    global _engine
    _engine = engine


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    if not update.message:
        return
    user = update.effective_user
    welcome = (
        f"Salut {user.first_name} ! 👋\n\n"
        "Je suis ton **Coach Fitness IA** 🏋️\n\n"
        "Je vais t'aider à atteindre tes objectifs en te proposant "
        "des programmes d'entraînement et des plans nutritionnels personnalisés.\n\n"
        "Pour commencer, parle-moi un peu de toi ! "
        "Quel est ton objectif principal ?"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")
    # Trigger onboarding via engine
    await _handle_text(update, context, is_start=True)


async def cmd_morning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /morning command — get today's plan."""
    if not update.message or not _engine:
        return
    ext_id = str(update.effective_user.id)
    session = await get_session()
    try:
        user_repo = UserRepository(session)
        user = await user_repo.get_or_create(ext_id, "telegram", update.effective_user.first_name)
        reply = await _engine.generate_morning_message(session, user.id)
        await session.commit()
    finally:
        await session.close()
    await _send_long_message(update.message, reply)


async def cmd_evening(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /evening command — evening check-in."""
    if not update.message or not _engine:
        return
    ext_id = str(update.effective_user.id)
    session = await get_session()
    try:
        user_repo = UserRepository(session)
        user = await user_repo.get_or_create(ext_id, "telegram", update.effective_user.first_name)
        reply = await _engine.generate_evening_checkin(session, user.id)
        await session.commit()
    finally:
        await session.close()
    await _send_long_message(update.message, reply)


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /profile command — show current profile."""
    if not update.message:
        return
    ext_id = str(update.effective_user.id)
    session = await get_session()
    try:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_external_id(ext_id)
        if not user or not user.profile:
            await update.message.reply_text("Aucun profil trouvé. Envoie /start pour commencer !")
            return
        p = user.profile
        lines = ["📋 **Ton profil** :"]
        field_map = {
            "age": "Âge", "height_cm": "Taille (cm)", "weight_kg": "Poids (kg)",
            "sex": "Sexe", "fitness_level": "Niveau", "goal": "Objectif",
            "available_equipment": "Matériel", "training_frequency": "Fréquence",
            "injuries_constraints": "Contraintes", "dietary_preferences": "Alimentation",
            "allergies": "Allergies", "food_budget": "Budget",
            "lifestyle_rhythm": "Rythme de vie",
        }
        for field, label in field_map.items():
            val = getattr(p, field, None)
            if val is not None:
                lines.append(f"• **{label}** : {val}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    finally:
        await session.close()


MAX_TELEGRAM_LENGTH = 4096


async def _send_long_message(message_obj, text: str):
    """Send a message, splitting into chunks if it exceeds Telegram's limit."""
    if len(text) <= MAX_TELEGRAM_LENGTH:
        await message_obj.reply_text(text)
        return
    # Split on double newlines first, then single newlines, then hard cut
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= MAX_TELEGRAM_LENGTH:
            chunks.append(remaining)
            break
        # Try to split at a double newline
        cut = remaining[:MAX_TELEGRAM_LENGTH].rfind("\n\n")
        if cut < 200:
            cut = remaining[:MAX_TELEGRAM_LENGTH].rfind("\n")
        if cut < 200:
            cut = MAX_TELEGRAM_LENGTH
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    for chunk in chunks:
        if chunk.strip():
            await message_obj.reply_text(chunk)


async def _handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE, is_start: bool = False):
    """Handle any text message."""
    if not update.message or not _engine:
        return

    user = update.effective_user
    ext_id = str(user.id)
    text = update.message.text or ""

    if is_start and not text:
        return

    session = await get_session()
    try:
        reply = await _engine.handle_message(
            session, ext_id, text,
            platform="telegram",
            username=user.first_name,
        )
    finally:
        await session.close()
    await _send_long_message(update.message, reply)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for non-command text messages."""
    await _handle_text(update, context)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages — analyze meal from photo."""
    if not update.message or not _engine:
        return

    user = update.effective_user
    ext_id = str(user.id)

    # Get the highest resolution photo
    photo = update.message.photo[-1]  # last element = highest resolution
    file = await context.bot.get_file(photo.file_id)

    # Download photo bytes
    photo_bytes = await file.download_as_bytearray()

    await update.message.reply_text("📸 Photo reçue ! Analyse en cours... 🔍")

    session = await get_session()
    try:
        reply = await _engine.analyze_meal_photo(
            session, ext_id, bytes(photo_bytes),
            mime_type="image/jpeg",
            platform="telegram",
            username=user.first_name,
        )
    finally:
        await session.close()

    await _send_long_message(update.message, reply)


def _configure_app(app: Application):
    """Add handlers to a Telegram Application."""
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("morning", cmd_morning))
    app.add_handler(CommandHandler("evening", cmd_evening))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


def create_telegram_app(engine: CoachingEngine) -> Application:
    """Create and configure a single Telegram bot application (backward compat)."""
    settings = get_settings()
    set_engine(engine)
    tokens = settings.telegram.get_tokens()
    if not tokens:
        raise ValueError("No TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKENS configured")
    app = Application.builder().token(tokens[0]).build()
    _configure_app(app)
    logger.info("Telegram bot configured", token_suffix=tokens[0][-6:])
    return app


def create_telegram_apps(engine: CoachingEngine) -> list[Application]:
    """Create multiple Telegram bot applications, one per token."""
    settings = get_settings()
    set_engine(engine)
    tokens = settings.telegram.get_tokens()
    if not tokens:
        raise ValueError("No TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKENS configured")

    apps = []
    for token in tokens:
        app = Application.builder().token(token).build()
        _configure_app(app)
        logger.info("Telegram bot configured", token_suffix=token[-6:])
        apps.append(app)
    return apps

