from fastapi import FastAPI, HTTPException, BackgroundTasks
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
from typing import List, Dict, Optional
import asyncio
import httpx

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

# Model fallback chain: lite → 2.0-flash → 2.5-flash-lite
# All three confirmed available via genai.list_models().
# Ordered cheapest/highest-quota first so free tier lasts as long as possible.
_MODEL_CHAIN = ["gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-2.5-flash-lite"]

# ── Persistent cache directory ───────────────────────────────────────
CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
SUMMARY_CACHE_FILE = CACHE_DIR / "summaries.json"
GO_DEEPER_CACHE_FILE = CACHE_DIR / "go_deeper.json"


def _load_json_cache(path: Path) -> Dict:
    """Load a JSON cache file from disk; return empty dict if missing/corrupt."""
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Cache load warning ({path.name}): {e}")
    return {}


def _save_json_cache(path: Path, data: Dict):
    """Atomically write a JSON cache file to disk."""
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception as e:
        print(f"Cache save warning ({path.name}): {e}")


# ── RAG Storage ──────────────────────────────────────────────────────
# In-memory only (chunks are cheap to rebuild from snippets)
rag_store: Dict[str, Dict] = {}

# ── Go Deeper Storage (disk-backed) ──────────────────────────────────
go_deeper_store: Dict[str, Dict] = _load_json_cache(GO_DEEPER_CACHE_FILE)

# ── Summary Cache (disk-backed) ───────────────────────────────────────
# Survives server restarts — each video_id is only ever summarised ONCE.
summary_store: Dict[str, Dict] = _load_json_cache(SUMMARY_CACHE_FILE)
print(f"Loaded {len(summary_store)} cached summaries and {len(go_deeper_store)} go-deeper entries from disk.")

# ── Request/Response Models ───────────────────────────────────────────
class SummariseRequest(BaseModel):
    url: str
    transcript_snippets: Optional[List[Dict]] = None

class ChatRequest(BaseModel):
    video_id: str
    question: str
    chat_history: Optional[List[Dict[str, str]]] = []


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




def snippets_to_text(snippets: List[Dict]) -> str:
    """Join snippet dicts into a single plain-text string (used for Gemini prompt)."""
    return " ".join(s["text"] for s in snippets)


def format_timestamp(seconds: float) -> str:
    """Convert float seconds to human-readable M:SS string e.g. 4:32."""
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


def clean_json(text: str) -> str:
    """Strip markdown fences from Gemini response."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def chunk_transcript(snippets: List[Dict], chunk_size: int = 500, overlap: int = 100) -> List[Dict]:
    """Split transcript snippets into overlapping word-count chunks.

    Each returned chunk is: {"text": str, "start_seconds": float}

    start_seconds comes from the first snippet that contributed words to the
    chunk — accurate to within one caption line (~2-5 seconds).

    Previously this accepted a plain string and returned List[str], discarding
    all timestamp data. Now timestamps travel with every chunk all the way to
    the chat response, enabling "when is X mentioned?" answers.
    """
    # Flatten snippets to a word-level list, each word tagged with its snippet's
    # start time so we can recover the timestamp for any chunk boundary.
    word_data: List[Dict] = []
    for snippet in snippets:
        for word in snippet["text"].split():
            word_data.append({"word": word, "start": snippet["start"]})

    chunks: List[Dict] = []
    i = 0
    while i < len(word_data):
        window = word_data[i: i + chunk_size]
        chunks.append({
            "text": " ".join(w["word"] for w in window),
            "start_seconds": window[0]["start"],
        })
        i += chunk_size - overlap

    return chunks


def simple_text_similarity(text1: str, text2: str) -> float:
    """Jaccard similarity between two strings — used for keyword-based chunk retrieval."""
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    if not words1 or not words2:
        return 0.0
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return len(intersection) / len(union) if union else 0.0


def retrieve_relevant_chunks(video_id: str, question: str, top_k: int = 3) -> List[Dict]:
    """Return the top-k most relevant chunks for a question."""
    if video_id not in rag_store:
        raise HTTPException(status_code=404, detail="Video not found in RAG store.")
    chunks: List[Dict] = rag_store[video_id]["chunks"]
    scored = [(i, simple_text_similarity(question, c["text"])) for i, c in enumerate(chunks)]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [chunks[i] for i, _ in scored[:top_k]]


def build_rag_index(video_id: str, snippets: List[Dict]):
    """Build in-memory RAG index from timestamped transcript snippets.

    Previously accepted a plain transcript string. Now accepts the raw snippet
    list so chunk_transcript can assign accurate start times to every chunk.
    """
    chunks = chunk_transcript(snippets)
    rag_store[video_id] = {"chunks": chunks}
    print(f"RAG index built for {video_id}: {len(chunks)} timestamped chunks.")


def _parse_retry_delay(err: str) -> float:
    """Extract retry_delay seconds from a Gemini 429 error string, default 20s."""
    m = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+(?:\.\d+)?)', err)
    return float(m.group(1)) + 1 if m else 20.0


async def call_gemini_async(prompt: str, max_retries: int = 3) -> str:
    """Call Gemini with per-error retry delay and model fallback on quota exhaustion.

    - Parses the actual retry_delay from 429 responses instead of guessing.
    - Falls back through _MODEL_CHAIN when a model's daily quota is fully used.
    - Never blocks the event loop (runs in a thread pool).
    """
    for model_name in _MODEL_CHAIN:
        current_model = genai.GenerativeModel(model_name)
        for attempt in range(max_retries):
            try:
                response = await asyncio.to_thread(current_model.generate_content, prompt)
                return response.text
            except Exception as e:
                err = str(e)
                is_rate_limit = '429' in err or 'quota' in err.lower() or 'exhausted' in err.lower()
                if not is_rate_limit:
                    raise  # non-quota error — bubble up immediately

                # Broadened daily quota detection to catch RESOURCE_EXHAUSTED and
                # other Gemini error variants the original narrow check would miss.
                is_daily_exhausted = (
                    'limit: 0' in err
                    or 'PerDay' in err
                    or 'RESOURCE_EXHAUSTED' in err
                    or 'daily' in err.lower()
                )
                if is_daily_exhausted:
                    print(f"Gemini daily quota exhausted for {model_name} — trying next model…")
                    break  # break inner loop → advance to next model

                if attempt < max_retries - 1:
                    wait = _parse_retry_delay(err)
                    print(f"Gemini rate limited ({model_name}) — waiting {wait:.0f}s before retry {attempt + 1}/{max_retries}…")
                    await asyncio.sleep(wait)
                else:
                    break  # exhausted retries for this model → try next

    raise HTTPException(status_code=429, detail="AI service rate-limited. Please wait and try again.")


# ── Shared prompt pieces ──────────────────────────────────────────────
_VISUAL_INSTRUCTIONS = """Your job:
1. Understand what this video is really about
2. Choose the BEST visual type to represent its core message from these options:
   - "hierarchy"    → for levels, tiers, rankings, pyramids
   - "timeline"     → for steps, processes, how-tos, chronological sequences
   - "graph"        → for connected concepts, frameworks, relationship maps
   - "comparison"   → for X vs Y, pros/cons, side-by-side analysis
   - "stat_cards"   → for key facts, numbers, tips, takeaways, listicles
3. Extract the key content and return it structured for that visual type
"""

_VISUAL_SCHEMA = """Return ONLY valid JSON (no markdown fences, no explanation) matching this structure:

{{
  "video_title": "inferred title or topic of the video",
  "tldr": "2-3 sentence summary of what this video is about and its key insight",
  "visual_type": "hierarchy|timeline|graph|comparison|stat_cards",
  "visual_reason": "one sentence explaining why you chose this visual type",
  "content": {{ ... }}
}}

The "content" field depends on visual_type:

For "hierarchy":
{{ "title": "...", "levels": [ {{"level": 1, "name": "Level name", "description": "what defines this level", "traits": ["trait1", "trait2"]}} ] }}

For "timeline":
{{ "title": "...", "steps": [ {{"step": 1, "title": "Step title", "description": "what happens here", "tip": "optional pro tip"}} ] }}

For "graph":
{{ "title": "...", "nodes": [ {{"id": "snake_case_id", "label": "Concept", "description": "brief description", "group": "category"}} ], "edges": [ {{"source": "id1", "target": "id2", "label": "relationship"}} ] }}

For "comparison":
{{ "title": "...", "items": ["Option A", "Option B"], "dimensions": [ {{"dimension": "Dimension name", "values": ["value for A", "value for B"], "winner": 0}} ], "verdict": "overall recommendation" }}

For "stat_cards":
{{ "title": "...", "cards": [ {{"icon": "emoji", "stat": "bold headline fact", "detail": "1-2 sentence context"}} ] }}

Be accurate to the video content. Extract real insights, not generic summaries.
"""


# ── Go Deeper helpers ─────────────────────────────────────────────────
def extract_key_concepts(visual_data: Dict) -> List[str]:
    """Extract 3-5 key concepts from visual summary content."""
    concepts = []
    visual_type = visual_data.get('visual_type', '')
    content = visual_data.get('content', {})

    if visual_type == 'hierarchy':
        concepts = [l.get('name', '') for l in content.get('levels', [])[:5] if l.get('name')]
    elif visual_type == 'timeline':
        concepts = [s.get('title', '') for s in content.get('steps', [])[:5] if s.get('title')]
    elif visual_type == 'graph':
        concepts = [n.get('label', '') for n in content.get('nodes', [])[:5] if n.get('label')]
    elif visual_type == 'comparison':
        items = content.get('items', [])
        dimensions = content.get('dimensions', [])
        concepts = items[:2] + [d.get('dimension', '') for d in dimensions[:3] if d.get('dimension')]
    elif visual_type == 'stat_cards':
        concepts = [c.get('stat', '') for c in content.get('cards', [])[:5] if c.get('stat')]

    if len(concepts) < 3 and visual_data.get('video_title'):
        concepts.append(visual_data.get('video_title'))

    return concepts[:5]


async def gather_resources(concepts: List[str], video_title: str) -> List[Dict]:
    """Use Tavily REST API directly via httpx to search for related resources."""
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        print("TAVILY_API_KEY not set — will use YouTube search link fallback for Go Deeper")
        return []

    queries = [f"{concept} tutorial guide course" for concept in concepts]
    all_results: List[Dict] = []

    print(f"Searching Tavily for {len(queries)} queries...")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            responses = await asyncio.gather(
                *[
                    client.post(
                        "https://api.tavily.com/search",
                        json={
                            "api_key": tavily_key,
                            "query": q,
                            "search_depth": "basic",
                            "max_results": 3,
                        },
                    )
                    for q in queries
                ],
                return_exceptions=True,
            )

        for i, resp in enumerate(responses):
            if isinstance(resp, Exception):
                print(f"  ✗ Tavily query '{queries[i]}': {resp}")
                continue
            try:
                data = resp.json()
                results = data.get("results", [])
                all_results.extend(results)
                print(f"  ✓ '{queries[i]}': {len(results)} results")
            except Exception as e:
                print(f"  ✗ Parse error for '{queries[i]}': {e}")

    except Exception as e:
        print(f"Tavily HTTP error: {e}")

    print(f"Tavily gathered {len(all_results)} total results")
    return all_results


def generate_search_link_fallback(concepts: List[str], video_title: str) -> List[Dict]:
    """Generate YouTube search links from key concepts — zero API calls."""
    from urllib.parse import quote_plus
    resources = []
    terms = concepts[:5] if concepts else [video_title]
    for i, term in enumerate(terms):
        query = quote_plus(f"{term} tutorial")
        resources.append({
            'title': f'{term} — Video Tutorials',
            'url': f'https://www.youtube.com/results?search_query={query}',
            'type': 'video',
            'source': 'youtube.com',
            'reason': f'Watch tutorials and explanations about {term}',
            'relevance_score': 8 - i,
        })
    return resources


def process_tavily_results(raw_results: List[Dict], concepts: List[str]) -> List[Dict]:
    """Deduplicate, classify and rank Tavily results — zero API calls."""
    from urllib.parse import urlparse
    seen_domains: set = set()
    processed = []

    for r in raw_results:
        url = r.get('url', '')
        title = r.get('title', 'Resource')
        snippet = r.get('content', '')
        if not url:
            continue
        try:
            domain = urlparse(url).netloc.replace('www.', '')
        except Exception:
            domain = 'Unknown'

        if domain in seen_domains:
            continue
        seen_domains.add(domain)

        url_l, title_l = url.lower(), title.lower()
        if 'youtube.com' in url_l or 'youtu.be' in url_l:
            rtype = 'video'
        elif any(x in url_l for x in ('udemy', 'coursera', 'course', '/learn', 'tutorial')):
            rtype = 'course'
        elif 'github.com' in url_l:
            rtype = 'tool'
        elif 'book' in title_l:
            rtype = 'book'
        else:
            rtype = 'article'

        score = 6
        for concept in concepts[:3]:
            if concept.lower() in title_l or concept.lower() in url_l:
                score = min(score + 1, 10)
                break

        reason = snippet[:120].rstrip() + '…' if len(snippet) > 120 else (
            snippet or f'Related to {concepts[0] if concepts else "the video topic"}')

        processed.append({
            'title': title,
            'url': url,
            'type': rtype,
            'source': domain,
            'reason': reason,
            'relevance_score': score,
        })

    processed.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
    return processed[:5]


async def build_go_deeper(video_id: str, visual_data: Dict):
    """Build Go Deeper resources (runs as async background task)."""
    try:
        print(f"\n=== Starting Go Deeper for video {video_id} ===")
        go_deeper_store[video_id] = {'status': 'processing', 'resources': []}

        concepts = extract_key_concepts(visual_data)
        print(f"Extracted concepts: {concepts}")

        if not concepts:
            print("No concepts extracted, marking as completed with empty results")
            go_deeper_store[video_id] = {'status': 'completed', 'resources': []}
            return

        video_title = visual_data.get('video_title', '')

        print(f"Gathering resources for {len(concepts)} concepts...")
        raw_results = await gather_resources(concepts, video_title)
        print(f"Got {len(raw_results)} raw results from Tavily")

        if raw_results:
            resources = process_tavily_results(raw_results, concepts)
            print(f"Processed {len(resources)} resources from Tavily")
        else:
            print("No Tavily results — generating YouTube search links...")
            resources = generate_search_link_fallback(concepts, video_title)

        go_deeper_store[video_id] = {'status': 'completed', 'resources': resources}
        _save_json_cache(GO_DEEPER_CACHE_FILE, go_deeper_store)
        print(f"=== Go Deeper completed for video {video_id} with {len(resources)} resources ===\n")

    except Exception as e:
        print(f"Go Deeper error for {video_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        go_deeper_store[video_id] = {'status': 'error', 'resources': []}
        _save_json_cache(GO_DEEPER_CACHE_FILE, go_deeper_store)


# ── Routes ───────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return FileResponse(str(Path(__file__).parent.parent / "frontend" / "index.html"))


@app.post("/api/summarise")
async def summarise(request: SummariseRequest, background_tasks: BackgroundTasks):
    # 1. Extract video ID
    try:
        video_id = extract_video_id(request.url)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid YouTube URL. Please paste a valid YouTube or YouTube Shorts link."
        )

    # 1a. Cache hit — skip Gemini and rebuild RAG from stored snippets.
    if video_id in summary_store:
        print(f"Cache hit for video {video_id} — skipping Gemini call")
        cached = summary_store[video_id]
        if video_id not in rag_store:
            if cached.get("_snippets"):
                # Preferred path: timestamps intact from original fetch.
                background_tasks.add_task(build_rag_index, video_id, cached["_snippets"])
            elif cached.get("_transcript"):
                # Legacy cache (pre-timestamp): synthesise a single snippet with
                # start=0 so the index builds, but timestamps won't be accurate.
                legacy_snippets = [{"text": cached["_transcript"], "start": 0.0, "duration": 0.0}]
                background_tasks.add_task(build_rag_index, video_id, legacy_snippets)
        return {k: v for k, v in cached.items() if not k.startswith("_")}

    # 2. Use client-provided transcript or fall back to Gemini direct video analysis.
    snippets = None
    if request.transcript_snippets and len(request.transcript_snippets) > 0:
        snippets = request.transcript_snippets

    if snippets:
        background_tasks.add_task(build_rag_index, video_id, snippets)
        full_text = snippets_to_text(snippets)
        transcript_for_prompt = full_text[:6000] + ("... [truncated]" if len(full_text) > 6000 else "")
        prompt = f"""You are an expert at distilling YouTube video content into clear, beautiful visual summaries.

Here is the transcript of a YouTube video:
---
{transcript_for_prompt}
---

{_VISUAL_INSTRUCTIONS}
{_VISUAL_SCHEMA}"""
    else:
        full_text = ""
        prompt = f"""You are an expert at distilling YouTube video content into clear, beautiful visual summaries.

Watch this YouTube video and analyze its content:
https://www.youtube.com/watch?v={video_id}

{_VISUAL_INSTRUCTIONS}
{_VISUAL_SCHEMA}"""

    try:
        text = await call_gemini_async(prompt)
        text = clean_json(text)
        data = json.loads(text)
        data["video_id"] = video_id
        data["_snippets"] = (snippets or [])[:500]
        data["_transcript"] = full_text[:20000]

        summary_store[video_id] = data
        _save_json_cache(SUMMARY_CACHE_FILE, summary_store)

        # Pass only public (non-_) fields to build_go_deeper so internal data
        # can never accidentally end up serialised into a Gemini prompt.
        public_data = {k: v for k, v in data.items() if not k.startswith("_")}
        background_tasks.add_task(build_go_deeper, video_id, public_data)

        return public_data
    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"AI response parse error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")


@app.get("/api/go-deeper/{video_id}")
async def get_go_deeper(video_id: str):
    """Get Go Deeper resources for a video."""
    if video_id not in go_deeper_store:
        return {"status": "not_started", "resources": []}
    return go_deeper_store[video_id]


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Timestamp-aware RAG Q&A endpoint.

    Each retrieved chunk carries a start_seconds value from the original YouTube
    caption metadata. The prompt instructs Gemini to cite timestamps and the
    response includes deep-link URLs so users can jump straight to that moment.
    """
    # 1. Retrieve relevant timestamped chunks.
    try:
        relevant_chunks = retrieve_relevant_chunks(request.video_id, request.question, top_k=3)
    except HTTPException:
        return {
            "answer": "I'm still processing the video transcript. Please wait a moment and try again.",
            "status": "processing"
        }

    # 2. Build context — each excerpt is labelled with its timestamp and a
    #    clickable YouTube deep-link so Gemini can reference both in its answer.
    context_parts = []
    for i, chunk in enumerate(relevant_chunks):
        ts = format_timestamp(chunk["start_seconds"])
        deep_link = f"https://youtu.be/{request.video_id}?t={int(chunk['start_seconds'])}"
        context_parts.append(
            f"[Excerpt {i + 1} — {ts} | {deep_link}]:\n{chunk['text']}"
        )
    context = "\n\n".join(context_parts)

    # 3. Chat history (last 2 exchanges only to keep token count low).
    history_text = ""
    if request.chat_history:
        history_text = "\nPrevious conversation:\n" + "\n".join([
            f"User: {msg['role'] == 'user' and msg['content'] or ''}\n"
            f"Assistant: {msg['role'] == 'assistant' and msg['content'] or ''}"
            for msg in request.chat_history[-2:]
        ])

    # 4. Prompt — explicitly tells Gemini to cite timestamps and deep-links.
    prompt = f"""You are answering questions about a YouTube video based ONLY on the transcript excerpts below.
Each excerpt includes a timestamp (M:SS) and a YouTube link that jumps directly to that moment in the video.

{context}
{history_text}

Instructions:
- Answer based only on the excerpts provided.
- When relevant, cite the timestamp (e.g. "At 4:32, ...") and include the YouTube link so the user can jump to that moment.
- If the question asks when something is mentioned or discussed, always include the timestamp and link.
- Be concise.

Question: {request.question}
Answer:"""

    # 5. Generate response.
    try:
        answer = await call_gemini_async(prompt)
        return {"answer": answer.strip(), "status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)