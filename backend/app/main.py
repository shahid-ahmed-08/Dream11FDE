from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.config import settings
from backend.app.routers import match, replay, fan

app = FastAPI(
    title="Why Did My Rank Drop - API",
    description="Backend API for cricket fantasy rank analysis and ball-by-ball replay.",
    version="1.0.0",
)

# CORS Middleware for Frontend Communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(match.router)
app.include_router(replay.router)
app.include_router(fan.router)


@app.get("/health")
def healthcheck():
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "match_id": settings.MATCH_ID,
        "gemini_api_configured": settings.has_gemini_key,
    }


# Serve built React frontend (must be AFTER all API routes)
_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=settings.HOST, port=settings.PORT, reload=True)

