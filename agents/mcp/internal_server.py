"""Internal Fitness Coach MCP server.

Run with:
    python -m agents.mcp.internal_server
"""

import asyncio

from database.database import close_db, get_session, init_db
from database.repositories import ProfileRepository, TrackingRepository, UserRepository
from agents.serialization import (
    checkin_to_dict,
    nutrition_to_dict,
    profile_to_dict,
    workout_to_dict,
)

try:
    from fastmcp import FastMCP
except ImportError:  # pragma: no cover - only relevant when running the server
    FastMCP = None


mcp = FastMCP("FitnessCoach") if FastMCP else None


async def _get_user(external_id: str):
    session = await get_session()
    try:
        return session, await UserRepository(session).get_by_external_id(external_id)
    except Exception:
        await session.close()
        raise


if mcp:

    @mcp.tool()
    async def get_user_profile(external_id: str) -> dict:
        """Return the stored fitness profile for one external user id."""
        session, user = await _get_user(external_id)
        try:
            if not user:
                return {"found": False, "profile": {}}
            profile = await ProfileRepository(session).get_by_user_id(user.id)
            return {"found": True, "profile": profile_to_dict(profile)}
        finally:
            await session.close()

    @mcp.tool()
    async def get_recent_workouts(external_id: str, limit: int = 7) -> dict:
        """Return recent workout logs for one external user id."""
        session, user = await _get_user(external_id)
        try:
            if not user:
                return {"found": False, "workouts": []}
            workouts = await TrackingRepository(session).get_recent_workouts(user.id, limit=limit)
            return {"found": True, "workouts": [workout_to_dict(item) for item in workouts]}
        finally:
            await session.close()

    @mcp.tool()
    async def get_recent_checkins(external_id: str, limit: int = 7) -> dict:
        """Return recent check-ins for one external user id."""
        session, user = await _get_user(external_id)
        try:
            if not user:
                return {"found": False, "checkins": []}
            checkins = await TrackingRepository(session).get_recent_checkins(user.id, limit=limit)
            return {"found": True, "checkins": [checkin_to_dict(item) for item in checkins]}
        finally:
            await session.close()

    @mcp.tool()
    async def get_recent_nutrition(external_id: str, limit: int = 7) -> dict:
        """Return recent nutrition logs for one external user id."""
        session, user = await _get_user(external_id)
        try:
            if not user:
                return {"found": False, "nutrition": []}
            nutrition = await TrackingRepository(session).get_recent_nutrition(user.id, limit=limit)
            return {"found": True, "nutrition": [nutrition_to_dict(item) for item in nutrition]}
        finally:
            await session.close()


def run_internal_mcp_server():
    """Run the internal MCP server over stdio."""
    if not mcp:
        raise RuntimeError("fastmcp is not installed. Install dependencies from requirements.txt.")
    asyncio.run(init_db())
    try:
        mcp.run(transport="stdio")
    finally:
        asyncio.run(close_db())


if __name__ == "__main__":
    run_internal_mcp_server()
