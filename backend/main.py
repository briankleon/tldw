from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
import json
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi

load_dotenv()

# ── App setup ────────────────────────────────────────────────────────
app = FastAPI(title="TL;DW")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

static_path = Path(__file__).parent.parent / "frontend" / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set. Copy .env.example to .env and add your key.")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# ── Models ───────────────────────────────────────────────────────────
class SummariseRequest(BaseModel):
    url: str


# ── Helpers ──────────────────────────────────────────────────────────
def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from any YouTube URL format."""
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11})(?:\?|&|\/|$)",
        r"youtu\.be\/([0-9A-Za-z_-]{11})",
        r"shorts\/([0-9A-Za-z_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError("Could not extract video ID from URL")


def get_transcript(video_id: str) -> str:
    """Fetch transcript using youtube-transcript-api."""
    try:
        ytt = YouTubeTranscriptApi()
        fetched = ytt.fetch(video_id)
        return " ".join(chunk.text for chunk in fetched)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"No transcript available for this video. It may be private, a music video, or have captions disabled. ({str(e)})"
        )


def clean_json(text: str) -> str:
    """Strip markdown fences from Gemini response."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


# ── Routes ───────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return FileResponse(str(Path(__file__).parent.parent / "frontend" / "index.html"))

@app.post("/api/summarise")
async def summarise(request: SummariseRequest):
    # 1. Extract video ID
    try:
        video_id = extract_video_id(request.url)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL. Please paste a valid YouTube or YouTube Shorts link.")

    # 2. Get transcript
    transcript = get_transcript(video_id)

    # Truncate if very long (Gemini flash has large context but let's be safe)
    if len(transcript) > 12000:
        transcript = transcript[:12000] + "... [truncated]"

    # 3. Ask Gemini to analyse content and choose the best visual type
    prompt = f"""
You are an expert at distilling YouTube video content into clear, beautiful visual summaries.

Here is the transcript of a YouTube video:
---
{transcript}
---

Your job:
1. Understand what this video is really about
2. Choose the BEST visual type to represent its core message from these options:
   - "hierarchy"    → for levels, tiers, rankings, pyramids (e.g. "5 levels of data scientist")
   - "timeline"     → for steps, processes, how-tos, chronological sequences
   - "graph"        → for connected concepts, frameworks, relationship maps
   - "comparison"   → for X vs Y, pros/cons, side-by-side analysis
   - "stat_cards"   → for key facts, numbers, tips, takeaways, listicles

3. Extract the key content and return it structured for that visual type

Return ONLY valid JSON (no markdown fences, no explanation) matching this structure:

{{
  "video_title": "inferred title or topic of the video",
  "tldr": "2-3 sentence summary of what this video is about and its key insight",
  "visual_type": "hierarchy|timeline|graph|comparison|stat_cards",
  "visual_reason": "one sentence explaining why you chose this visual type",
  "content": {{ ... }}
}}

The "content" field structure depends on visual_type:

For "hierarchy":
{{
  "title": "The X Levels of ...",
  "levels": [
    {{"level": 1, "name": "Level name", "description": "what defines this level", "traits": ["trait1", "trait2"]}}
  ]
}}

For "timeline":
{{
  "title": "How to ...",
  "steps": [
    {{"step": 1, "title": "Step title", "description": "what happens here", "tip": "optional pro tip"}}
  ]
}}

For "graph":
{{
  "title": "The ... Framework",
  "nodes": [
    {{"id": "snake_case_id", "label": "Concept", "description": "brief description", "group": "category"}}
  ],
  "edges": [
    {{"source": "id1", "target": "id2", "label": "relationship"}}
  ]
}}

For "comparison":
{{
  "title": "X vs Y",
  "items": ["Option A", "Option B"],
  "dimensions": [
    {{"dimension": "Dimension name", "values": ["value for A", "value for B"], "winner": 0}}
  ],
  "verdict": "overall recommendation or conclusion"
}}

For "stat_cards":
{{
  "title": "Key Takeaways",
  "cards": [
    {{"icon": "emoji", "stat": "bold headline fact or number", "detail": "1-2 sentence context"}}
  ]
}}

Be accurate to the video content. Extract real insights, not generic summaries.
"""

    try:
        response = model.generate_content(prompt)
        text = clean_json(response.text)
        data = json.loads(text)
        data["video_id"] = video_id
        return data
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"AI response parse error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    # Load .env if present
    from dotenv import load_dotenv
    load_dotenv()
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
