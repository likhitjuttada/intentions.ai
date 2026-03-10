"""vision.py — Gemini multimodal screenshot analysis."""

import json
import os
import re

from google import genai
from google.genai import types

_client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

_SYSTEM_PROMPT = """\
You are a browser assistant that helps users by watching their screen.
Analyze the provided screenshot and answer:
1. What is the user trying to accomplish? (be specific, e.g. "scheduling a biometrics appointment with USCIS")
2. What is the current visible page state? (any forms, selections, errors, or notable UI elements)
3. How confident are you? (0.0 – 1.0)

Return ONLY valid JSON in this exact shape:
{
  "intent": "<short description of user goal>",
  "page_state": "<current UI state description>",
  "confidence": <float>
}
"""

def analyze_screenshot(
    screenshot_b64: str,
    url: str,
    title: str | None = None,
    geolocation: dict | None = None,
) -> dict:
    location_ctx = ""
    if geolocation:
        location_ctx = f"\nUser's approximate location: lat={geolocation['lat']:.4f}, lng={geolocation['lng']:.4f}"

    user_prompt = (
        f"Page URL: {url}\n"
        f"Page title: {title or 'unknown'}"
        f"{location_ctx}\n\n"
        "Now analyze the screenshot below."
    )

    response = _client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[
            types.Content(parts=[
                types.Part(text=_SYSTEM_PROMPT),
                types.Part(text=user_prompt),
                types.Part(inline_data=types.Blob(mime_type="image/png", data=screenshot_b64)),
            ])
        ],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )

    raw = response.text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)
