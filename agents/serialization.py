"""Serialization helpers for graph-safe agent state."""

from typing import Any


def _iso(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def profile_to_dict(profile) -> dict[str, Any]:
    if profile is None:
        return {}
    fields = [
        "id", "user_id", "age", "height_cm", "weight_kg", "sex",
        "fitness_level", "goal", "available_equipment", "training_frequency",
        "injuries_constraints", "dietary_preferences", "allergies",
        "food_budget", "lifestyle_rhythm", "wake_up_time", "sleep_time",
        "extra_info", "profile_complete",
    ]
    return {field: getattr(profile, field, None) for field in fields}


def message_to_dict(message) -> dict[str, Any]:
    return {
        "role": getattr(message, "role", None),
        "content": getattr(message, "content", ""),
        "created_at": _iso(getattr(message, "created_at", None)),
        "metadata": getattr(message, "metadata_json", None),
    }


def checkin_to_dict(checkin) -> dict[str, Any]:
    fields = [
        "id", "user_id", "check_in_type", "energy_level", "motivation_level",
        "mood", "pain_reported", "workout_done", "nutrition_followed",
        "sleep_quality", "notes", "raw_response",
    ]
    data = {field: getattr(checkin, field, None) for field in fields}
    data["date"] = _iso(getattr(checkin, "date", None))
    return data


def workout_to_dict(workout) -> dict[str, Any]:
    fields = [
        "id", "user_id", "planned_workout", "completed", "actual_workout",
        "duration_minutes", "difficulty_rating", "notes",
    ]
    data = {field: getattr(workout, field, None) for field in fields}
    data["date"] = _iso(getattr(workout, "date", None))
    return data


def nutrition_to_dict(nutrition) -> dict[str, Any]:
    fields = ["id", "user_id", "meal_type", "description", "plan_followed", "notes"]
    data = {field: getattr(nutrition, field, None) for field in fields}
    data["date"] = _iso(getattr(nutrition, "date", None))
    return data


def memory_to_dict(memory) -> dict[str, Any]:
    return {
        "memory_type": getattr(memory, "memory_type", None),
        "memory_key": getattr(memory, "memory_key", None),
        "content": getattr(memory, "content", ""),
        "confidence": getattr(memory, "confidence", None),
        "updated_at": _iso(getattr(memory, "updated_at", None)),
    }


def location_to_dict(location) -> dict[str, Any]:
    if location is None:
        return {}
    return {
        "latitude": getattr(location, "latitude", None),
        "longitude": getattr(location, "longitude", None),
        "label": getattr(location, "label", None),
        "timezone": getattr(location, "timezone", None),
        "country": getattr(location, "country", None),
        "admin_area": getattr(location, "admin_area", None),
        "consent_source": getattr(location, "consent_source", None),
        "updated_at": _iso(getattr(location, "updated_at", None)),
    }


def health_connection_to_dict(connection) -> dict[str, Any]:
    if connection is None:
        return {}
    return {
        "provider": getattr(connection, "provider", None),
        "status": getattr(connection, "status", None),
        "device_name": getattr(connection, "device_name", None),
        "permissions": getattr(connection, "permissions_json", None) or [],
        "consent_source": getattr(connection, "consent_source", None),
        "last_synced_at": _iso(getattr(connection, "last_synced_at", None)),
        "updated_at": _iso(getattr(connection, "updated_at", None)),
    }


def health_daily_summary_to_dict(summary) -> dict[str, Any]:
    if summary is None:
        return {}
    fields = [
        "id", "user_id", "source", "steps", "active_energy_kcal",
        "resting_heart_rate_bpm", "hrv_ms", "sleep_minutes",
        "workout_minutes", "walking_running_distance_km", "vo2_max",
        "body_mass_kg",
    ]
    data = {field: getattr(summary, field, None) for field in fields}
    data["summary_date"] = _iso(getattr(summary, "summary_date", None))
    data["updated_at"] = _iso(getattr(summary, "updated_at", None))
    return data


def health_workout_to_dict(workout) -> dict[str, Any]:
    if workout is None:
        return {}
    fields = [
        "id", "user_id", "external_uuid", "source", "workout_type",
        "duration_minutes", "active_energy_kcal", "distance_km",
    ]
    data = {field: getattr(workout, field, None) for field in fields}
    data["started_at"] = _iso(getattr(workout, "started_at", None))
    data["ended_at"] = _iso(getattr(workout, "ended_at", None))
    data["updated_at"] = _iso(getattr(workout, "updated_at", None))
    return data
