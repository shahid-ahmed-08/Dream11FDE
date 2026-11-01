# Why Did My Rank Drop? 🏏

> **Dream11 FDE Assignment** — GT vs KKR, IPL 2023 Match 13.
> A mobile-first fantasy cricket replay app that explains, ball-by-ball, exactly why your rank moved.

## Live Demo

Pick a preset team → watch the match replay → get plain-English (or Hinglish) explanations of every rank swing.

---

## How to Run

```bash
# 1. Clone
git clone https://github.com/shahid-ahmed-08/Dream11FDE.git
cd Dream11FDE

# 2. Python environment
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r backend/requirements.txt

# 3. Add your Gemini key
cp backend/.env.example backend/.env
# Edit backend/.env and set GEMINI_API_KEY=your_key_here
# Get a free key at https://aistudio.google.com/

# 4. Build the frontend
cd frontend
npm install
npm run build
cd ..

# 5. Run (API + UI on one port)
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

# Open http://localhost:8000
```

> Works without a Gemini key — explanations fall back to a structured template automatically.

---

## Features

| Feature | Details |
|---------|---------|
| **3 preset teams** | Safe Pick (C: Shubman Gill), Differential (C: Rashid Khan), Finisher Fan (C: AD Russell) |
| **Ball-by-ball replay** | SSE stream at 1×, 5×, or instant speed |
| **AI explanations** | Gemini 2.5 Flash explains each rank swing in English and Hinglish |
| **Simulated rank** | Ranked against 10,000 sampled teams every ball |
| **Hat-trick highlight** | Balls 16.1–16.3 (Rashid's hat-trick) are gold-highlighted |
| **Final-over highlight** | Over 19 highlighted in cyan |
| **Watch-next lines** | Innings-aware — never mentions a dismissed or finished player |
| **Summary screen** | Final points, rank, percentile, best & worst moment |

---

## Architecture

```
Dream11FDE/
├── backend/
│   ├── app/
│   │   ├── main.py             # FastAPI app + static file serving
│   │   ├── config.py           # Settings (loads GEMINI_API_KEY from .env)
│   │   ├── models/             # Pydantic schemas
│   │   ├── routers/            # API endpoints (/api/...)
│   │   └── services/
│   │       ├── points_engine.py      # Ball-by-ball fantasy points
│   │       ├── pool_generator.py     # 10,000 simulated teams
│   │       ├── replay_engine.py      # SSE stream
│   │       ├── fan_session.py        # Session management
│   │       ├── key_moment_engine.py  # Moment detection + facts packet
│   │       └── ai_explainer.py       # Gemini 2.5 Flash integration
│   ├── tests/                  # 40 pytest tests
│   ├── requirements.txt
│   └── .env.example            # Copy to .env and add your key
├── frontend/
│   └── src/
│       ├── App.jsx             # Screen router
│       ├── components/
│       │   ├── StartScreen.jsx
│       │   ├── LiveScreen.jsx
│       │   └── FinishedScreen.jsx
│       └── index.css
└── data/                       # Cricsheet match JSON
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Backend health + Gemini key status |
| `GET` | `/api/teams/presets` | The 3 preset teams |
| `POST` | `/api/fan/sessions` | Start a replay session |
| `GET` | `/api/fan/sessions/{id}/stream?speed=1x` | SSE ball-by-ball stream |
| `GET` | `/api/fan/sessions/{id}/summary` | Final match summary |
| `GET` | `/api/match/1359487/summary` | Match metadata |

---

## Security

- The Gemini API key lives **only** in `backend/.env` (git-ignored via `*.env`).
- The built frontend is static JS — no secrets, no API calls with credentials.
- `backend/.env.example` contains a placeholder only — **no real key**.

---

## Tests

```bash
.venv\Scripts\pytest.exe backend/tests -q
# 40 passed
```

---

*Built with FastAPI · React · Vite · Gemini 2.5 Flash · Cricsheet data*
