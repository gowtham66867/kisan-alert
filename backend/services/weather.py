"""Open-Meteo weather integration — no API key required."""
import logging
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# AP district → coordinates
DISTRICT_COORDS = {
    "Guntur":       (16.3067, 80.4365),
    "Narasaraopet": (16.2340, 80.0573),
    "Krishna":      (16.5167, 80.6167),
    "Prakasam":     (15.5057, 80.0499),
    "Nellore":      (14.4426, 79.9865),
    "Kurnool":      (15.8281, 78.0373),
    "Anantapur":    (14.6819, 77.6006),
    "Vijayawada":   (16.5062, 80.6480),
}

WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Icy fog", 51: "Light drizzle", 53: "Drizzle",
    55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 80: "Rain showers",
    81: "Heavy showers", 82: "Violent showers", 95: "Thunderstorm",
    96: "Thunderstorm with hail", 99: "Heavy thunderstorm with hail",
}


def get_district_weather(district: str = "Guntur") -> dict:
    """Fetch 7-day forecast for an AP district — free, no API key."""
    lat, lng = DISTRICT_COORDS.get(district, DISTRICT_COORDS["Guntur"])
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lng}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
        f"precipitation_probability_max,windspeed_10m_max,weathercode"
        f"&current_weather=true"
        f"&timezone=Asia%2FKolkata"
        f"&forecast_days=7"
    )
    try:
        with httpx.Client(timeout=8) as http:
            resp = http.get(url)
            resp.raise_for_status()
            raw = resp.json()

        current = raw.get("current_weather", {})
        daily = raw.get("daily", {})
        dates = daily.get("time", [])

        forecast = []
        for i, date in enumerate(dates):
            code = daily.get("weathercode", [])[i] if i < len(daily.get("weathercode", [])) else 0
            forecast.append({
                "date": date,
                "max_temp": daily["temperature_2m_max"][i] if daily.get("temperature_2m_max") else None,
                "min_temp": daily["temperature_2m_min"][i] if daily.get("temperature_2m_min") else None,
                "rain_mm": daily["precipitation_sum"][i] if daily.get("precipitation_sum") else 0,
                "rain_prob": daily["precipitation_probability_max"][i] if daily.get("precipitation_probability_max") else 0,
                "wind_kmh": daily["windspeed_10m_max"][i] if daily.get("windspeed_10m_max") else 0,
                "condition": WMO_CODES.get(code, "Unknown"),
                "code": code,
            })

        # Farm advisories based on weather
        advisories = _farm_advisory(forecast[:3])

        return {
            "district": district,
            "lat": lat,
            "lng": lng,
            "current": {
                "temp": current.get("temperature"),
                "wind_kmh": current.get("windspeed"),
                "condition": WMO_CODES.get(current.get("weathercode", 0), "Unknown"),
            },
            "forecast": forecast,
            "farm_advisory": advisories,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        logger.warning(f"Weather fetch failed: {e}")
        return _fallback_weather(district, lat, lng)


def _farm_advisory(forecast: list) -> list[str]:
    """Generate weather-based farm advisories."""
    advisories = []
    for day in forecast:
        rain = day.get("rain_mm", 0) or 0
        prob = day.get("rain_prob", 0) or 0
        wind = day.get("wind_kmh", 0) or 0
        temp = day.get("max_temp", 30) or 30
        date = day.get("date", "")

        if rain > 30:
            advisories.append(f"{date}: Heavy rain ({rain}mm) expected — delay pesticide spray. Ensure field drainage.")
        elif rain > 5 and prob > 60:
            advisories.append(f"{date}: Rain likely — good for transplanting. Avoid fertilizer application.")
        elif rain == 0 and prob < 20:
            advisories.append(f"{date}: Dry day — good for pesticide/fungicide spray. Check irrigation schedule.")
        if wind > 40:
            advisories.append(f"{date}: High winds ({wind} km/h) — avoid spray operations, support tall crops.")
        if temp > 38:
            advisories.append(f"{date}: Heat stress risk ({temp}°C) — irrigate early morning, apply mulch.")

    return advisories[:4] if advisories else ["Good farming conditions expected this week."]


def _fallback_weather(district: str, lat: float, lng: float) -> dict:
    return {
        "district": district, "lat": lat, "lng": lng,
        "current": {"temp": 32, "wind_kmh": 12, "condition": "Partly cloudy"},
        "forecast": [],
        "farm_advisory": ["Weather data unavailable. Check IMD website for forecasts."],
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
