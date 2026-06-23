"""High-level Apple Health connection helpers."""

from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import get_settings
from database.repositories import HealthRepository, UserRepository


DEFAULT_HEALTHKIT_PERMISSIONS = [
    "stepCount",
    "activeEnergyBurned",
    "restingHeartRate",
    "heartRateVariabilitySDNN",
    "sleepAnalysis",
    "workouts",
    "distanceWalkingRunning",
    "vo2Max",
    "bodyMass",
]


async def create_apple_health_link(
    session: AsyncSession,
    external_id: str,
    platform: str,
    username: str | None = None,
) -> tuple[str, str]:
    """Create a short-lived pairing code for the iOS companion app."""
    user = await UserRepository(session).get_or_create(external_id, platform, username)
    connection, code = await HealthRepository(session).create_link_code(
        user_id=user.id,
        ttl_minutes=get_settings().api.healthkit_link_ttl_minutes,
        permissions=DEFAULT_HEALTHKIT_PERMISSIONS,
        consent_source=f"{platform}_health_link",
    )
    await session.commit()

    public_url = get_settings().api.public_url.strip()
    api_hint = f"\nAPI : {public_url}" if public_url else ""
    message = (
        "Code Apple Health généré.\n\n"
        f"Code : {code}\n"
        f"Expiration : {connection.link_code_expires_at.isoformat()} UTC\n\n"
        "Dans l'app iOS companion, colle ce code pour autoriser la synchronisation "
        "Apple Health vers ton coach."
        f"{api_hint}"
    )
    return code, message


async def get_apple_health_status_text(session: AsyncSession, external_id: str) -> str:
    """Return a user-facing Apple Health sync status."""
    user = await UserRepository(session).get_by_external_id(external_id)
    if not user:
        return "Aucun utilisateur trouvé. Envoie d'abord un message au coach."

    health_repo = HealthRepository(session)
    connection = await health_repo.get_active_connection(user.id)
    latest = await health_repo.get_latest_daily_summary(user.id)
    workouts = await health_repo.get_recent_health_workouts(user.id, limit=3)

    if not connection:
        return "Apple Health n'est pas encore connecté. Utilise /health_link pour générer un code."

    lines = ["Apple Health est connecté."]
    if connection.device_name:
        lines.append(f"Appareil : {connection.device_name}")
    if connection.last_synced_at:
        lines.append(f"Dernière sync : {connection.last_synced_at.isoformat()} UTC")
    if latest:
        parts = [f"date {latest.summary_date.isoformat()}"]
        if latest.steps is not None:
            parts.append(f"{latest.steps} pas")
        if latest.active_energy_kcal is not None:
            parts.append(f"{latest.active_energy_kcal} kcal actives")
        if latest.sleep_minutes is not None:
            parts.append(f"{round(latest.sleep_minutes / 60, 1)} h sommeil")
        lines.append("Dernier résumé : " + ", ".join(parts))
    if workouts:
        lines.append(f"Workouts importés récemment : {len(workouts)}")
    return "\n".join(lines)
