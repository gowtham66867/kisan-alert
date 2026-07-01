"""Farmer query endpoints — text, photo, streaming advisory."""
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services import db, gemini_service
from services.claude_agent import validate_with_claude, stream_advisory

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
    use_claude: bool = True  # opt-in to Claude multi-agent validation


@router.post("/text")
def submit_text_query(body: TextQuery):
    """Submit a crop query — Gemini diagnosis + optional Claude expert validation."""
    # Stage 1: Gemini diagnosis
    result = gemini_service.analyze_crop_query(
        text=body.text,
        language=body.language,
        crop=body.crop,
    )

    # Stage 2: Claude expert validation (if API key is available)
    if body.use_claude:
        result = validate_with_claude(result, body.text, body.crop)

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
    use_claude: bool = Form(True),
):
    """Submit a crop photo for disease/pest detection."""
    image_bytes = await image.read()
    result = gemini_service.analyze_crop_query(
        text=text or "Please analyze this crop photo and provide advisory.",
        language=language,
        crop=crop,
        image_bytes=image_bytes,
    )

    if use_claude:
        result = validate_with_claude(result, text or "Photo analysis", crop)

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


@router.get("/stream")
async def stream_query(text: str, language: str = "en", crop: str = ""):
    """
    Stream a real-time advisory via Server-Sent Events.
    Claude streams tokens directly — farmer sees the advice as it's written.
    """
    async def event_generator():
        async for chunk in stream_advisory(text, language, crop):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/history")
def get_query_history(district: str = "", limit: int = 100):
    """Get recent farmer queries."""
    return db.get_queries(district, limit)


@router.get("/stats")
def get_stats():
    """Get aggregated statistics."""
    return db.get_stats()
