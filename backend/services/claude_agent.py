"""
Claude multi-agent pipeline for expert validation.

Flow: Gemini (diagnosis) → Claude (expert validation + treatment) → Gemini (translation)

Claude acts as a second-opinion specialist — it reviews the Gemini diagnosis,
checks for red flags, adds research-backed treatments, and flags if the
severity should be escalated.
"""
import json
import logging
import os
from typing import AsyncGenerator

import anthropic

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> anthropic.Anthropic | None:
    global _client
    if _client is None:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            return None
        _client = anthropic.Anthropic(api_key=key)
    return _client


TOOLS = [
    {
        "name": "validate_diagnosis",
        "description": "Validate a crop disease diagnosis and provide expert treatment protocol",
        "input_schema": {
            "type": "object",
            "properties": {
                "confirmed_diagnosis": {"type": "string", "description": "Confirmed disease/pest name"},
                "severity_assessment": {"type": "string", "enum": ["Critical", "High", "Medium", "Low"]},
                "treatment_protocol": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered list of treatment steps"
                },
                "chemical_recommendations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific chemical/organic inputs with dosage"
                },
                "preventive_measures": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "escalate_to_expert": {"type": "boolean"},
                "confidence": {"type": "number", "description": "0-1 confidence score"}
            },
            "required": ["confirmed_diagnosis", "severity_assessment", "treatment_protocol", "confidence"]
        }
    }
]


def validate_with_claude(gemini_result: dict, original_query: str, crop: str) -> dict:
    """
    Use Claude as expert validator for Gemini's diagnosis.
    Returns enhanced advisory with Claude's second opinion.
    Falls back gracefully if ANTHROPIC_API_KEY not set.
    """
    client = _get_client()
    if not client:
        return {"claude_validated": False, "source": "gemini_only", **gemini_result}

    prompt = f"""You are an expert agricultural pathologist and crop consultant for India.

A farmer has reported: "{original_query}"
Crop: {crop}

Gemini AI's initial diagnosis:
- Issue Type: {gemini_result.get('issue_type', 'Unknown')}
- Severity: {gemini_result.get('severity', 'Medium')}
- Symptoms: {gemini_result.get('symptoms', 'Not specified')}
- Initial Advisory: {gemini_result.get('advisory', 'None')}

Please validate this diagnosis using your expert knowledge. Use the validate_diagnosis tool to provide:
1. Confirmed or corrected diagnosis
2. Evidence-based severity assessment
3. Detailed treatment protocol specific to Indian farming conditions
4. Chemical recommendations with correct dosages
5. Whether this needs in-person expert consultation"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            tools=TOOLS,
            messages=[{"role": "user", "content": prompt}]
        )

        # Extract tool use result
        for block in response.content:
            if block.type == "tool_use" and block.name == "validate_diagnosis":
                inp = block.input
                # Merge Claude's expert opinion with Gemini's output
                return {
                    **gemini_result,
                    "claude_validated": True,
                    "source": "gemini+claude",
                    "confirmed_diagnosis": inp.get("confirmed_diagnosis"),
                    "severity": inp.get("severity_assessment", gemini_result.get("severity")),
                    "treatment_protocol": inp.get("treatment_protocol", []),
                    "chemical_recommendations": inp.get("chemical_recommendations", []),
                    "preventive_measures": inp.get("preventive_measures", []),
                    "escalate_to_expert": inp.get("escalate_to_expert", False),
                    "claude_confidence": inp.get("confidence", 0.8),
                    "products_recommended": inp.get("chemical_recommendations", gemini_result.get("products_recommended", [])),
                    "advisory": "\n".join(
                        f"{i+1}. {step}" for i, step in enumerate(inp.get("treatment_protocol", []))
                    ) or gemini_result.get("advisory", ""),
                }

        # Claude responded without tool use (text only)
        return {"claude_validated": True, "source": "gemini+claude", **gemini_result}

    except anthropic.APIConnectionError:
        logger.warning("Claude API unreachable — using Gemini-only result")
    except anthropic.RateLimitError:
        logger.warning("Claude rate limited — using Gemini-only result")
    except Exception as e:
        logger.warning(f"Claude validation failed: {e}")

    return {"claude_validated": False, "source": "gemini_only", **gemini_result}


async def stream_advisory(text: str, language: str, crop: str, image_bytes: bytes = None) -> AsyncGenerator[str, None]:
    """
    Stream a crop advisory using Claude's streaming API.
    Yields SSE-formatted strings.
    """
    client = _get_client()
    if not client:
        yield f"data: {json.dumps({'step': 'advisory', 'chunk': 'Advisory generation requires Claude API key.'})}\n\n"
        return

    lang_map = {"te": "Telugu", "hi": "Hindi", "ta": "Tamil", "kn": "Kannada", "mr": "Marathi", "en": "English"}
    lang_name = lang_map.get(language, "English")

    system = """You are KisanGPT — an expert agricultural advisor for Indian farmers.
Provide clear, practical, step-by-step advice. Use simple language.
Structure your response as:
🔍 DIAGNOSIS: (1 line)
⚠️ SEVERITY: (Critical/High/Medium/Low + reason)
📋 TREATMENT STEPS:
1. ...
2. ...
3. ...
💊 INPUTS NEEDED: (specific products + dosage)
⏰ FOLLOW-UP: (when to check back)"""

    user_msg = f"Crop: {crop or 'not specified'}\nLanguage preference: {lang_name}\nFarmer's query: {text}"

    try:
        yield f"data: {json.dumps({'step': 'start', 'message': 'Consulting KisanGPT...'})}\n\n"

        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=800,
            system=system,
            messages=[{"role": "user", "content": user_msg}]
        ) as stream:
            for chunk in stream.text_stream:
                yield f"data: {json.dumps({'step': 'chunk', 'chunk': chunk})}\n\n"

        yield f"data: {json.dumps({'step': 'done'})}\n\n"

    except Exception as e:
        logger.error(f"Claude stream error: {e}")
        yield f"data: {json.dumps({'step': 'error', 'message': str(e)})}\n\n"
