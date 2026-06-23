"""FastAPI application for companion app integrations."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.apple_health import router as apple_health_router
from database.database import close_db, init_db


def create_app(manage_db: bool = True) -> FastAPI:
    """Create the HTTP API app.

    `manage_db=False` is used when the API runs in the same process as Telegram,
    because the main process already owns database startup and shutdown.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if manage_db:
            await init_db()
        try:
            yield
        finally:
            if manage_db:
                await close_db()

    app = FastAPI(
        title="Fitness Coach Companion API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(apple_health_router)

    @app.get("/health")
    async def health_check() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
