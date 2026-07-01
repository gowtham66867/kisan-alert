"""Farmer query endpoints — text, voice, photo."""
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from services import db, gemini_service

router = APIRouter(prefix="/query", tags=["queries"])
logger = logging.getLogger(__name__)


class TextQuery(BaseModel):
    text: str
    language: str = "en"
    crop: str = ""
    phone: str = ""
    village: str = ""
    lat: float = 0.0
    lng: float = 0.0


@router.post("/text")
def submit_text_query(body: TextQuery):
    """Submit a crop query as text."""
    result = gemini_service.analyze_crop_query(
        text=body.text,
        language=body.language,
        crop=body.crop,
    )
    record = {
        "id": str(uuid.uuid4())[:8],
        "input_type": "text",
        "original_text": body.text,
        "phone": body.phone,
        "village": body.village,
        "lat": body.lat,
        "lng": body.lng,
        **result,
    }
    qid = db.save_query(record)
    return {"id": qid, "status": "analyzed", **result}


@router.post("/photo")
async def submit_photo_query(
    image: UploadFile = File(...),
    text: str = Form(""),
    language: str = Form("en"),
    crop: str = Form(""),
    phone: str = Form(""),
    village: str = Form(""),
    lat: float = Form(0.0),
    lng: float = Form(0.0),
):
    """Submit a crop photo for disease/pest detection."""
    image_bytes = await image.read()
    result = gemini_service.analyze_crop_query(
        text=text or "Please analyze this crop photo and provide advisory.",
        language=language,
        crop=crop,
        image_bytes=image_bytes,
    )
    record = {
        "id": str(uuid.uuid4())[:8],
        "input_type": "photo",
        "original_text": text,
        "phone": phone,
        "village": village,
        "lat": lat,
        "lng": lng,
        **result,
    }
    qid = db.save_query(record)
    return {"id": qid, "status": "analyzed", **result}


@router.get("/history")
def get_query_history(district: str = "", limit: int = 100):
    """Get recent farmer queries."""
    return db.get_queries(district, limit)


@router.get("/stats")
def get_stats():
    """Get aggregated statistics."""
    return db.get_stats()
