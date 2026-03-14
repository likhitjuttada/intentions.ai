"""agent.py — ADK root agent that turns intent into sidebar cards."""

import os
import uuid
from typing import Any

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import google_search
from google.genai import types as genai_types

APP_NAME = "ui-navigator"
_session_service = InMemorySessionService()

def _build_agent() -> Agent:
    return Agent(
        name="ui_navigator_root",
        model="gemini-2.0-flash",
        description="Proactive browser assistant that surfaces relevant info based on what the user is doing.",
        instruction="""\
You are a proactive browser assistant. You will receive:
- intent: what the user is trying to accomplish
- page_state: current visible UI state
- url: current page URL
- geolocation (optional): user's approximate location
- recent browsing (optional): user's tab history from the last hour

Your job:
1. Based on the intent and page_state, decide what would be most useful to surface.
2. Call web_search with targeted queries to find relevant information.
3. Return a JSON array of up to 3 cards, each with:
   {
     "id": "<unique stable string based on content topic>",
     "title": "<short card title, max 60 chars>",
     "summary": "<2-3 sentence summary, max 200 chars>",
     "icon": "<single relevant emoji>",
     "link": "<optional source URL or null>"
   }

Return ONLY the JSON array, no other text. No markdown code fences.

You may also receive a "User's recent browsing" list. Use it to understand the user's research trail and tailor your searches accordingly — e.g. if they browsed Reddit threads about a topic before landing on the current page, surface community insights that match.

Focus on genuinely useful, contextually relevant information. For government/immigration pages, surface community tips and timeline info. For local selections (city/office chosen), surface nearby points of interest or practical logistics.
""",
        tools=[google_search],
    )


_agent = _build_agent()
_runner = Runner(
    agent=_agent,
    app_name=APP_NAME,
    session_service=_session_service,
)


async def get_cards(
    intent: str,
    page_state: str,
    url: str,
    geolocation: dict | None = None,
    recent_history: list[dict] | None = None,
) -> list[dict[str, Any]]:
    """Run ADK agent and return a list of card dicts."""

    session_id = str(uuid.uuid4())
    user_id = "anonymous"

    await _session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )

    location_ctx = ""
    if geolocation:
        location_ctx = f"\nUser location: lat={geolocation['lat']:.4f}, lng={geolocation['lng']:.4f}"

    history_ctx = ""
    if recent_history:
        history_lines = "\n".join(
            f"- {h.get('title') or h['url']} ({h['url']})"
            for h in recent_history
        )
        history_ctx = f"\n\nUser's recent browsing (last 1hr):\n{history_lines}"
        print(f"[agent] recent_history received ({len(recent_history)} items):\n{history_lines}")
    else:
        print("[agent] recent_history: empty or not provided")
        
    message = (
        f"intent: {intent}\n"
        f"page_state: {page_state}\n"
        f"url: {url}"
        f"{location_ctx}"
        f"{history_ctx}"
    )

    content = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=message)],
    )

    final_text = ""
    async for event in _runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=content,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text.strip()

    if not final_text:
        return []

    import json, re
    # Try to pull a JSON array out of wherever it appears in the response
    match = re.search(r"\[.*\]", final_text, re.DOTALL)
    if not match:
        return []
    try:
        cards = json.loads(match.group())
    except json.JSONDecodeError:
        return []
    return cards if isinstance(cards, list) else []
