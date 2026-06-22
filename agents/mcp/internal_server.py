"""Internal Fitness Coach MCP server.

Run with:
    python -m agents.mcp.internal_server
"""

import asyncio

from database.database import close_db, get_session, init_db
from database.repositories import (
    DocumentRepository,
    LocationRepository,
    ProfileRepository,
    TrackingRepository,
    UserRepository,
)
from agents.serialization import (
    checkin_to_dict,
    location_to_dict,
    nutrition_to_dict,
    profile_to_dict,
    workout_to_dict,
)
from services.pdf_report import create_coach_pdf, sections_from_coach_text
from services.weather import geocode_location, get_current_weather

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

    @mcp.tool()
    async def set_user_location_by_city(external_id: str, city: str) -> dict:
        """Store a user-consented location resolved from a city/place name."""
        session = await get_session()
        try:
            user = await UserRepository(session).get_or_create(external_id, "mcp")
            resolved = await geocode_location(city)
            if not resolved:
                return {"stored": False, "error": "location_not_found"}
            location = await LocationRepository(session).set_active_location(
                user_id=user.id,
                latitude=resolved.latitude,
                longitude=resolved.longitude,
                label=resolved.name,
                timezone=resolved.timezone,
                country=resolved.country,
                admin_area=resolved.admin_area,
                consent_source="mcp_city",
            )
            await session.commit()
            return {"stored": True, "location": location_to_dict(location)}
        finally:
            await session.close()

    @mcp.tool()
    async def get_user_location(external_id: str) -> dict:
        """Return the active user-consented location."""
        session, user = await _get_user(external_id)
        try:
            if not user:
                return {"found": False, "location": {}}
            location = await LocationRepository(session).get_active_location(user.id)
            return {"found": bool(location), "location": location_to_dict(location)}
        finally:
            await session.close()

    @mcp.tool()
    async def get_current_weather_for_user(external_id: str) -> dict:
        """Return current weather for the user's consented location."""
        session, user = await _get_user(external_id)
        try:
            if not user:
                return {"found": False, "error": "user_not_found"}
            location = await LocationRepository(session).get_active_location(user.id)
            if not location:
                return {"found": False, "error": "location_missing"}
            weather = await get_current_weather(
                location.latitude,
                location.longitude,
                timezone=location.timezone or "auto",
            )
            return {
                "found": True,
                "location": location_to_dict(location),
                "weather": {
                    "temperature_c": weather.temperature_c,
                    "apparent_temperature_c": weather.apparent_temperature_c,
                    "humidity_percent": weather.humidity_percent,
                    "precipitation_mm": weather.precipitation_mm,
                    "wind_speed_kmh": weather.wind_speed_kmh,
                    "weather_code": weather.weather_code,
                    "description": weather.description,
                    "time": weather.time,
                    "summary": weather.to_coaching_summary(),
                },
            }
        finally:
            await session.close()

    @mcp.tool()
    async def generate_coach_pdf(
        external_id: str,
        title: str,
        subtitle: str,
        coach_text: str,
        document_type: str = "coach_report",
    ) -> dict:
        """Generate a styled PDF document from coach text and store its metadata."""
        session = await get_session()
        try:
            user = await UserRepository(session).get_or_create(external_id, "mcp")
            file_path = create_coach_pdf(
                title=title,
                subtitle=subtitle,
                sections=sections_from_coach_text(coach_text),
                filename_prefix=f"{external_id}-{document_type}",
            )
            document = await DocumentRepository(session).create_document(
                user_id=user.id,
                document_type=document_type,
                title=title,
                file_path=file_path,
                metadata={"source": "mcp"},
            )
            await session.commit()
            return {
                "generated": True,
                "document_id": document.id,
                "file_path": file_path,
                "document_type": document_type,
            }
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
