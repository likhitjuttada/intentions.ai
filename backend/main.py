"""main.py — FastAPI backend for UI Navigator."""

import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from vision import analyze_screenshot
from agent import get_cards

app = FastAPI(title="UI Navigator Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Chrome extensions use null origin
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    screenshot: str          # base64 PNG
    url: str
    title: str | None = None
    geolocation: dict | None = None  # { lat: float, lng: float }


class AnalyzeResponse(BaseModel):
    intent: str
    page_state: str
    confidence: float
    cards: list[dict[str, Any]]


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    if not req.screenshot:
        raise HTTPException(status_code=400, detail="screenshot is required")

    # Step 1: Vision — screenshot → intent + page_state
    try:
        vision_result = analyze_screenshot(
            screenshot_b64=req.screenshot,
            url=req.url,
            title=req.title,
            geolocation=req.geolocation,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Vision error: {e}")

    intent = vision_result.get("intent", "")
    page_state = vision_result.get("page_state", "")
    confidence = float(vision_result.get("confidence", 0.0))

    # Skip agent if confidence is too low (likely blank/internal page)
    if confidence < 0.3 or not intent:
        return AnalyzeResponse(
            intent=intent,
            page_state=page_state,
            confidence=confidence,
            cards=[],
        )

    # Step 2: ADK agent — intent + page_state → cards
    try:
        cards = await get_cards(
            intent=intent,
            page_state=page_state,
            url=req.url,
            geolocation=req.geolocation,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Agent error: {e}")

    return AnalyzeResponse(
        intent=intent,
        page_state=page_state,
        confidence=confidence,
        cards=cards[:3],  # enforce max 3
    )
