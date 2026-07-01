"""Gemini AI service for crop advisory, disease detection, and alerts."""
import base64
import json
import logging
import os

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)
MODEL = "gemini-2.0-flash"

_client = None


def _get_client():
    global _client
    if _client is None:
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set")
        _client = genai.Client(api_key=key)
    return _client


def _call(prompt: str, image_bytes: bytes = None, max_tokens: int = 1500) -> str:
    client = _get_client()
    parts = []
    if image_bytes:
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))
    parts.append(prompt)
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=parts,
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=0.3,
            ),
        )
        return response.text or ""
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            logger.warning("Gemini quota exhausted — using fallback")
            return ""
        raise


def analyze_crop_query(
    text: str,
    language: str = "en",
    crop: str = "",
    image_bytes: bytes = None,
) -> dict:
    """Analyze a farmer's query and return structured advisory."""
    lang_note = f"The farmer wrote in language code '{language}'." if language != "en" else ""
    crop_note = f"The crop mentioned is: {crop}." if crop else ""
    image_note = "An image of the crop/field has been provided — analyze it for disease, pest, or deficiency symptoms." if image_bytes else ""

    prompt = f"""You are an expert agricultural advisor for Indian farmers. {lang_note} {crop_note} {image_note}

Farmer's query: "{text}"

Analyze and return ONLY valid JSON with these fields:
{{
  "translated_text": "English translation of the query (same as input if already English)",
  "crop": "crop name mentioned or inferred (e.g. rice, tomato, groundnut)",
  "issue_type": one of ["Crop Disease", "Pest Attack", "Water Stress", "Soil Deficiency", "Weather Damage", "Market/Price", "Irrigation", "Fertilizer", "Seeds/Varieties", "General Advisory"],
  "severity": one of ["Critical", "High", "Medium", "Low"],
  "symptoms": "brief description of symptoms observed",
  "advisory": "practical 3-5 step advisory in simple language (in English)",
  "advisory_local": "same advisory translated to the farmer's language ({language})",
  "immediate_action": "single most urgent action the farmer should take today",
  "products_recommended": ["list of recommended inputs, max 3"],
  "follow_up_days": number of days after which farmer should check back
}}"""

    text_out = _call(prompt, image_bytes, 1500)

    # Parse JSON
    if text_out:
        start = text_out.find("{")
        end = text_out.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text_out[start:end])
            except Exception:
                pass

    # Rule-based fallback
    return {
        "translated_text": text,
        "crop": crop or "unspecified crop",
        "issue_type": "General Advisory",
        "severity": "Medium",
        "symptoms": "Unable to analyze — please provide more details",
        "advisory": "1. Inspect the crop closely for visible symptoms.\n2. Check soil moisture.\n3. Contact your local Krishi Vigyan Kendra (KVK) for in-person advice.\n4. Document symptoms with photos for better diagnosis.",
        "advisory_local": "स्थानीय कृषि विज्ञान केंद्र से संपर्क करें।",
        "immediate_action": "Visit your nearest Krishi Vigyan Kendra today.",
        "products_recommended": [],
        "follow_up_days": 7,
    }


def generate_daily_alert(district: str, season: str, crops: list[str]) -> dict:
    """Generate a daily weather and crop advisory alert."""
    prompt = f"""You are an agricultural advisory system for {district}, India.
Season: {season}. Main crops grown: {', '.join(crops) or 'rice, groundnut, chilli'}.

Generate a practical daily farm advisory. Return ONLY valid JSON:
{{
  "alert_type": one of ["Weather Advisory", "Pest Alert", "Irrigation Schedule", "Market Update", "Crop Stage Advisory"],
  "severity": one of ["Critical", "High", "Medium", "Low"],
  "message": "Clear 2-3 sentence advisory in English for farmers",
  "message_telugu": "Same advisory in Telugu",
  "message_hindi": "Same advisory in Hindi",
  "action_items": ["up to 3 specific actions farmers should take today"],
  "crops_affected": ["list of affected crops"]
}}"""

    out = _call(prompt, max_tokens=800)
    if out:
        start, end = out.find("{"), out.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(out[start:end])
            except Exception:
                pass

    return {
        "alert_type": "Crop Stage Advisory",
        "severity": "Low",
        "message": f"Daily advisory for {district}: Monitor your crops for pest activity. Ensure adequate irrigation. Check weather forecasts before applying fertilizers.",
        "message_telugu": "మీ పంటలను పర్యవేక్షించండి. తగిన నీటిపారుదల నిర్ధారించండి.",
        "message_hindi": "अपनी फसलों की निगरानी करें। उचित सिंचाई सुनिश्चित करें।",
        "action_items": ["Monitor crop for pests", "Check soil moisture", "Review weather forecast"],
        "crops_affected": crops[:3],
    }


def translate_text(text: str, target_language: str) -> str:
    """Translate text to target language."""
    if not text or target_language == "en":
        return text
    prompt = f"Translate the following text to {target_language}. Return only the translation, nothing else:\n\n{text}"
    out = _call(prompt, max_tokens=500)
    return out.strip() if out else text
