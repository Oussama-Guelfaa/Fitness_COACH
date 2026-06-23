"""Main entry point for the Fitness Coach AI.

Usage:
    python main.py cli        — Run in CLI mode (for testing)
    python main.py telegram   — Run with Telegram bot
    python main.py api        — Run the companion HTTP API
    python main.py telegram-api — Run Telegram bot and companion HTTP API
    python main.py mcp        — Run internal Fitness MCP server over stdio
    python main.py            — Default: CLI mode
"""

import sys
import asyncio
import structlog
from dotenv import load_dotenv

# Load .env before anything else
load_dotenv()

from config.settings import get_settings
from database.database import init_db, close_db
from llm.ollama_provider import create_llm_provider
from coaching.engine import CoachingEngine


def configure_logging():
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


async def run_telegram(with_api: bool = False):
    """Run one or more Telegram bots with scheduler."""
    from messaging.telegram_bot import create_telegram_apps
    from scheduler.scheduler import create_scheduler, start_scheduler, stop_scheduler, set_send_callback

    settings = get_settings()
    tokens = settings.telegram.get_tokens()
    if not tokens:
        print("❌ Aucun token Telegram configuré. Ajoute TELEGRAM_BOT_TOKEN ou TELEGRAM_BOT_TOKENS dans .env")
        sys.exit(1)

    llm = create_llm_provider(settings.llm)
    engine = CoachingEngine(llm)
    await init_db()

    apps = create_telegram_apps(engine)

    # Configure scheduler — send via the first bot (primary)
    primary_bot = apps[0]

    async def _send_chunks(bot, chat_id: int, text: str):
        """Send a message, splitting into chunks if too long for Telegram."""
        max_len = 4096
        if len(text) <= max_len:
            await bot.send_message(chat_id=chat_id, text=text)
            return
        remaining = text
        while remaining:
            if len(remaining) <= max_len:
                await bot.send_message(chat_id=chat_id, text=remaining)
                break
            cut = remaining[:max_len].rfind("\n\n")
            if cut < 200:
                cut = remaining[:max_len].rfind("\n")
            if cut < 200:
                cut = max_len
            await bot.send_message(chat_id=chat_id, text=remaining[:cut])
            remaining = remaining[cut:].lstrip("\n")

    async def send_telegram_message(external_id: str, platform: str, message: str):
        """Try sending via each bot until one succeeds."""
        for app in apps:
            try:
                await _send_chunks(app.bot, int(external_id), message)
                return
            except Exception:
                continue
        structlog.get_logger().error("All bots failed to send", user=external_id)

    scheduler = create_scheduler(engine)
    set_send_callback(send_telegram_message)
    start_scheduler()

    api_server = None
    api_task = None
    if with_api:
        import uvicorn
        from api.server import create_app

        api_settings = settings.api
        api_server = uvicorn.Server(
            uvicorn.Config(
                create_app(manage_db=False),
                host=api_settings.host,
                port=api_settings.port,
                log_level=settings.log_level.lower(),
            )
        )
        api_task = asyncio.create_task(api_server.serve())

    mode_label = "Telegram + API" if with_api else "Telegram"
    print(f"🏋️ Coach Fitness IA — Mode {mode_label} ({len(apps)} bot(s))")
    print("Bot(s) démarré(s). Ctrl+C pour arrêter.")

    try:
        # Initialize and start all bots
        for app in apps:
            await app.initialize()
            await app.start()
            await app.updater.start_polling()

        # Keep running
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except (KeyboardInterrupt, SystemExit):
            pass
    finally:
        stop_scheduler()
        if api_server:
            api_server.should_exit = True
        if api_task:
            try:
                await api_task
            except Exception:
                pass
        for app in apps:
            try:
                await app.updater.stop()
                await app.stop()
                await app.shutdown()
            except Exception:
                pass
        await llm.close()
        await close_db()


async def run_cli():
    """Run in CLI mode."""
    from messaging.cli_interface import run_cli as cli_main
    await cli_main()


async def run_api():
    """Run the companion HTTP API."""
    import uvicorn
    from api.server import create_app

    settings = get_settings()
    api_settings = settings.api
    config = uvicorn.Config(
        create_app(manage_db=True),
        host=api_settings.host,
        port=api_settings.port,
        log_level=settings.log_level.lower(),
    )
    server = uvicorn.Server(config)
    await server.serve()


def run_mcp():
    """Run the internal MCP server."""
    from agents.mcp.internal_server import run_internal_mcp_server
    run_internal_mcp_server()


def main():
    """Parse mode and run."""
    configure_logging()
    mode = sys.argv[1] if len(sys.argv) > 1 else "cli"

    if mode == "telegram":
        asyncio.run(run_telegram())
    elif mode in {"telegram-api", "telegram_api"}:
        asyncio.run(run_telegram(with_api=True))
    elif mode == "api":
        asyncio.run(run_api())
    elif mode == "cli":
        asyncio.run(run_cli())
    elif mode == "mcp":
        run_mcp()
    else:
        print(f"Mode inconnu : {mode}")
        print("Usage : python main.py [cli|telegram|telegram-api|api|mcp]")
        sys.exit(1)


if __name__ == "__main__":
    main()
