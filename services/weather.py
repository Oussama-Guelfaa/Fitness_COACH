"""Location geocoding and weather retrieval using Open-Meteo."""

from dataclasses import dataclass
from typing import Any

import httpx


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


WEATHER_CODES = {
    0: "Ciel clair",
    1: "Principalement clair",
    2: "Partiellement nuageux",
    3: "Couvert",
    45: "Brouillard",
    48: "Brouillard givrant",
    51: "Bruine légère",
    53: "Bruine modérée",
    55: "Bruine dense",
    61: "Pluie légère",
    63: "Pluie modérée",
    65: "Pluie forte",
    71: "Neige légère",
    73: "Neige modérée",
    75: "Neige forte",
    80: "Averses légères",
    81: "Averses modérées",
    82: "Averses fortes",
    95: "Orage",
    96: "Orage avec grêle légère",
    99: "Orage avec grêle forte",
}


@dataclass
class GeocodedLocation:
    """Resolved location returned by Open-Meteo geocoding."""

    name: str
    latitude: float
    longitude: float
    timezone: str | None = None
    country: str | None = None
    admin_area: str | None = None


@dataclass
class CurrentWeather:
    """Current weather snapshot for coaching decisions."""

    temperature_c: float | None
    apparent_temperature_c: float | None
    humidity_percent: float | None
    precipitation_mm: float | None
    wind_speed_kmh: float | None
    weather_code: int | None
    description: str
    time: str | None

    def to_coaching_summary(self) -> str:
        """Return a compact French summary for prompts and user messages."""
        parts = []
        if self.temperature_c is not None:
            parts.append(f"{self.temperature_c:.1f}°C")
        if self.apparent_temperature_c is not None:
            parts.append(f"ressenti {self.apparent_temperature_c:.1f}°C")
        if self.humidity_percent is not None:
            parts.append(f"humidité {self.humidity_percent:.0f}%")
        if self.wind_speed_kmh is not None:
            parts.append(f"vent {self.wind_speed_kmh:.0f} km/h")
        if self.precipitation_mm is not None and self.precipitation_mm > 0:
            parts.append(f"pluie {self.precipitation_mm:.1f} mm")
        prefix = " - ".join(parts) if parts else "conditions indisponibles"
        return f"{prefix} - {self.description}"


async def geocode_location(query: str, language: str = "fr") -> GeocodedLocation | None:
    """Resolve a city/place name to coordinates."""
    params = {
        "name": query,
        "count": 1,
        "language": language,
        "format": "json",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(GEOCODING_URL, params=params)
        resp.raise_for_status()
    data = resp.json()
    results = data.get("results") or []
    if not results:
        return None
    item = results[0]
    return GeocodedLocation(
        name=item.get("name") or query,
        latitude=float(item["latitude"]),
        longitude=float(item["longitude"]),
        timezone=item.get("timezone"),
        country=item.get("country"),
        admin_area=item.get("admin1"),
    )


async def get_current_weather(latitude: float, longitude: float, timezone: str = "auto") -> CurrentWeather:
    """Fetch current weather for latitude/longitude."""
    params: dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation",
                "weather_code",
                "wind_speed_10m",
            ]
        ),
        "timezone": timezone or "auto",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(FORECAST_URL, params=params)
        resp.raise_for_status()
    current = resp.json().get("current") or {}
    code = current.get("weather_code")
    description = WEATHER_CODES.get(code, "Conditions météo non classées")
    return CurrentWeather(
        temperature_c=current.get("temperature_2m"),
        apparent_temperature_c=current.get("apparent_temperature"),
        humidity_percent=current.get("relative_humidity_2m"),
        precipitation_mm=current.get("precipitation"),
        wind_speed_kmh=current.get("wind_speed_10m"),
        weather_code=code,
        description=description,
        time=current.get("time"),
    )

