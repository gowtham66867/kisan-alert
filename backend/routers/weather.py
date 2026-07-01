"""Weather endpoints — Open-Meteo free tier."""
from fastapi import APIRouter
from services.weather import get_district_weather

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/{district}")
def district_weather(district: str = "Guntur"):
    """Get 7-day forecast + farm advisories for a district."""
    return get_district_weather(district)


@router.get("/")
def default_weather():
    return get_district_weather("Guntur")
