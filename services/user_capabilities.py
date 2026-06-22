"""User-facing location, weather, and PDF capabilities."""

import os

from sqlalchemy.ext.asyncio import AsyncSession

from agents.serialization import location_to_dict
from database.models import User
from database.repositories import (
    DocumentRepository,
    LocationRepository,
    ProfileRepository,
    TrackingRepository,
    UserRepository,
)
from services.pdf_report import PDFSection, create_coach_pdf
from services.weather import geocode_location, get_current_weather


async def set_location_from_city(
    session: AsyncSession,
    external_id: str,
    platform: str,
    city: str,
    username: str | None = None,
) -> tuple[User, str]:
    """Store a user-consented city location."""
    user = await UserRepository(session).get_or_create(external_id, platform, username)
    resolved = await geocode_location(city)
    if not resolved:
        return user, f"Je n'ai pas trouvé la ville `{city}`. Essaie avec une ville plus précise."

    location = await LocationRepository(session).set_active_location(
        user_id=user.id,
        latitude=resolved.latitude,
        longitude=resolved.longitude,
        label=resolved.name,
        timezone=resolved.timezone,
        country=resolved.country,
        admin_area=resolved.admin_area,
        consent_source="city_command",
    )
    await session.commit()
    details = [location.label or city]
    if location.admin_area:
        details.append(location.admin_area)
    if location.country:
        details.append(location.country)
    return user, (
        "Localisation enregistrée avec ton consentement : "
        f"{', '.join(details)}. Je peux maintenant adapter la météo, "
        "l'hydratation et les séances outdoor."
    )


async def set_location_from_coordinates(
    session: AsyncSession,
    external_id: str,
    platform: str,
    latitude: float,
    longitude: float,
    username: str | None = None,
    label: str = "Position partagée",
) -> tuple[User, str]:
    """Store precise coordinates explicitly shared by the user."""
    user = await UserRepository(session).get_or_create(external_id, platform, username)
    await LocationRepository(session).set_active_location(
        user_id=user.id,
        latitude=latitude,
        longitude=longitude,
        label=label,
        consent_source="telegram_location",
    )
    await session.commit()
    return user, (
        "Position enregistrée avec ton consentement. "
        "Je l'utiliserai uniquement pour adapter les conseils météo et contexte local."
    )


async def get_weather_text(session: AsyncSession, external_id: str) -> str:
    """Return current weather text for the active user location."""
    user = await UserRepository(session).get_by_external_id(external_id)
    if not user:
        return "Aucun profil trouvé. Envoie d'abord /start ou un message au coach."
    location = await LocationRepository(session).get_active_location(user.id)
    if not location:
        return (
            "Je n'ai pas encore ta localisation. Partage ta position Telegram ou utilise "
            "`/location Paris` pour enregistrer une ville."
        )

    weather = await get_current_weather(
        location.latitude,
        location.longitude,
        timezone=location.timezone or "auto",
    )
    label = location.label or "ta position"
    return (
        f"Météo actuelle pour {label} : {weather.to_coaching_summary()}.\n\n"
        "Impact coach : adapte l'intensité, l'hydratation et le choix indoor/outdoor "
        "selon ces conditions."
    )


def _profile_section(profile) -> PDFSection:
    if not profile:
        return PDFSection(
            "Profil",
            "Profil encore incomplet. Continue l'onboarding pour obtenir un plan plus précis.",
            "#0EA5A4",
        )
    fields = {
        "Age": profile.age,
        "Taille": f"{profile.height_cm} cm" if profile.height_cm else None,
        "Poids": f"{profile.weight_kg} kg" if profile.weight_kg else None,
        "Objectif": profile.goal,
        "Niveau": profile.fitness_level,
        "Materiel": profile.available_equipment,
        "Frequence": profile.training_frequency,
        "Contraintes": profile.injuries_constraints,
        "Preferences": profile.dietary_preferences,
        "Budget": profile.food_budget,
    }
    body = "\n".join(f"- {key}: {value}" for key, value in fields.items() if value)
    if not body:
        body = "Profil encore vide. Le coach a besoin de tes objectifs, ton niveau et tes contraintes."
    return PDFSection("Profil utilisateur", body, "#0EA5A4")


def _list_section(title: str, items: list, formatter, empty: str, accent: str) -> PDFSection:
    if not items:
        return PDFSection(title, empty, accent)
    return PDFSection(title, "\n".join(formatter(item) for item in items[-5:]), accent)


async def generate_user_summary_pdf(session: AsyncSession, external_id: str) -> tuple[str | None, str]:
    """Generate a polished PDF summary for a user and return path + message."""
    user = await UserRepository(session).get_by_external_id(external_id)
    if not user:
        return None, "Aucun profil trouvé. Envoie d'abord /start ou un message au coach."

    profile = await ProfileRepository(session).get_by_user_id(user.id)
    tracking = TrackingRepository(session)
    location = await LocationRepository(session).get_active_location(user.id)

    sections = [_profile_section(profile)]

    if location:
        loc = location_to_dict(location)
        loc_body = (
            f"- Lieu: {loc.get('label') or 'Position partagée'}\n"
            f"- Pays: {loc.get('country') or 'Non renseigné'}\n"
            f"- Source de consentement: {loc.get('consent_source') or 'user_shared'}"
        )
        try:
            weather = await get_current_weather(
                location.latitude,
                location.longitude,
                timezone=location.timezone or "auto",
            )
            loc_body += f"\n- Météo actuelle: {weather.to_coaching_summary()}"
        except Exception:
            loc_body += "\n- Météo actuelle: indisponible"
        sections.append(PDFSection("Contexte local", loc_body, "#2563EB"))

    checkins = await tracking.get_recent_checkins(user.id)
    workouts = await tracking.get_recent_workouts(user.id)
    nutrition = await tracking.get_recent_nutrition(user.id)

    sections.append(
        _list_section(
            "Check-ins récents",
            checkins,
            lambda item: f"- {item.check_in_type}: énergie {item.energy_level or '?'} / motivation {item.motivation_level or '?'} - {item.notes or 'pas de note'}",
            "Aucun check-in récent.",
            "#7C3AED",
        )
    )
    sections.append(
        _list_section(
            "Séances récentes",
            workouts,
            lambda item: f"- {'faite' if item.completed else 'non faite'} - {item.actual_workout or item.planned_workout or 'séance non détaillée'}",
            "Aucune séance récente.",
            "#F97316",
        )
    )
    sections.append(
        _list_section(
            "Nutrition récente",
            nutrition,
            lambda item: f"- {item.meal_type or 'repas'}: {item.description or item.notes or 'non détaillé'}",
            "Aucun log nutrition récent.",
            "#16A34A",
        )
    )

    file_path = create_coach_pdf(
        title="Bilan Coach Fitness",
        subtitle="Profil, contexte local, historique récent et prochaines priorités",
        sections=sections,
        filename_prefix=f"{external_id}-bilan-coach",
    )
    document = await DocumentRepository(session).create_document(
        user_id=user.id,
        document_type="coach_summary",
        title="Bilan Coach Fitness",
        file_path=file_path,
        metadata={"external_id": external_id},
    )
    await session.commit()
    return file_path, f"PDF généré : {os.path.basename(file_path)} (document #{document.id})"
