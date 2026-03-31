# TL;DW — See the video without watching it

Paste any YouTube URL and get an instant visual summary. AI reads the transcript and picks the best visual format — hierarchy, timeline, concept graph, comparison table, or stat cards.

---

## Quick Start

### 1. Create a Python 3.11 virtual environment in PyCharm

> ⚠️ Use Python 3.11 — not 3.14 — to avoid dependency issues.

In PyCharm: Settings → Python Interpreter → Add → Virtualenv → Base: Python 3.11

Or via terminal:
```bash
python3.11 -m venv venv
source venv/bin/activate      # Mac/Linux
venv\Scripts\activate         # Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set your Gemini API key

```bash
cp .env.example .env
```

Edit `.env`:
```
GEMINI_API_KEY=your_actual_key_here
```

Free key at: https://aistudio.google.com/app/apikey

### 4. Run

```bash
cd backend
python main.py
```

Or set PyCharm run config:
- Script: `backend/main.py`
- Working directory: project root

### 5. Open browser

```
http://localhost:8000
```

---

## How It Works

1. You paste a YouTube or YouTube Shorts URL
2. `youtube-transcript-api` fetches the auto-generated transcript (no download, no API key needed)
3. Gemini reads the full transcript and decides the best visual type for the content
4. The frontend renders the visual — hierarchy, timeline, graph, comparison, or stat cards

---

## Project Structure

```
tldw/
├── backend/
│   └── main.py               # FastAPI + transcript extraction + Gemini
├── frontend/
│   ├── index.html
│   └── static/
│       ├── css/style.css
│       └── js/
│           ├── app.js         # Routing, loading, API calls
│           └── visuals.js     # All 5 visual renderers
├── requirements.txt
├── .env.example
└── README.md
```

---

## Visual Types

| Type | When AI picks it |
|------|-----------------|
| Hierarchy | Levels, tiers, rankings, pyramids |
| Timeline | Steps, processes, how-tos |
| Concept Graph | Frameworks, connected ideas |
| Comparison | X vs Y, pros/cons |
| Stat Cards | Tips, facts, listicles, numbers |

---

## Notes

- Videos need auto-generated captions enabled (most English videos do)
- Music videos, private videos, and some foreign language videos may not work
- Shorts work the same as regular videos
