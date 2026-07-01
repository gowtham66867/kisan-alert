"""Alert endpoints — daily advisories, weather alerts."""
import logging
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from services import db, gemini_service

router = APIRouter(prefix="/alerts", tags=["alerts"])
logger = logging.getLogger(__name__)

DISTRICTS = ["Narasaraopet", "Guntur", "Krishna", "Prakasam", "Nellore"]
SEASON_CROPS = {
    "kharif": ["rice", "groundnut", "cotton", "maize", "soybean"],
    "rabi": ["wheat", "chickpea", "mustard", "sunflower", "potato"],
    "zaid": ["watermelon", "cucumber", "bitter gourd", "tomato"],
}


def _current_season():
    month = datetime.now().month
    if 6 <= month <= 10:
        return "kharif"
    elif 11 <= month <= 3:
        return "rabi"
    return "zaid"


@router.post("/generate")
def generate_alert(district: str = "Narasaraopet"):
    """Generate and store a daily alert for a district."""
    season = _current_season()
    crops = SEASON_CROPS.get(season, ["rice", "groundnut"])
    alert_data = gemini_service.generate_daily_alert(district, season, crops)
    alert_data["district"] = district
    alert_data["village"] = district
    alert_data["message_local"] = alert_data.get("message_telugu", "")
    alert_data["language"] = "te"
    aid = db.save_alert(alert_data)
    return {"id": aid, "status": "generated", **alert_data}


@router.get("/recent")
def get_recent_alerts(limit: int = 20):
    """Get recent alerts."""
    return db.get_alerts(limit)


@router.post("/cron/daily")
def cron_daily(x_cron_secret: str = Header(default="")):
    """Cloud Scheduler daily alert generation for all districts."""
    import os
    if x_cron_secret != os.environ.get("CRON_SECRET", ""):
        raise HTTPException(status_code=403, detail="Invalid cron secret")
    results = []
    for district in DISTRICTS:
        try:
            season = _current_season()
            crops = SEASON_CROPS.get(season, ["rice", "groundnut"])
            alert_data = gemini_service.generate_daily_alert(district, season, crops)
            alert_data["district"] = district
            alert_data["village"] = district
            alert_data["message_local"] = alert_data.get("message_telugu", "")
            alert_data["language"] = "te"
            aid = db.save_alert(alert_data)
            results.append({"district": district, "id": aid, "status": "ok"})
        except Exception as e:
            results.append({"district": district, "status": "error", "error": str(e)})
    return {"generated": len(results), "results": results}
