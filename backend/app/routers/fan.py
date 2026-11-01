"""
Fan Router — fan-facing API endpoints.
Exposes player pool, team validation, fan sessions with points/rank/key-moments,
and a SSE stream that carries per-delivery explanations.
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.models.fantasy import FantasyTeam, ValidationResult
from backend.app.models.key_moment import AIExplanation, KeyMomentResult, MatchReplaySummary
from backend.app.services.ai_explainer import get_explanation
from backend.app.services.fan_session import FanSession, fan_session_manager
from backend.app.services.points_engine import PointsEngine
from backend.app.services.preset_teams import PRESET_TEAMS
from backend.app.services.replay_engine import load_match_stream_items

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["fan"])

# Shared points engine for validation (read-only usage)
_engine = PointsEngine()


# ─── Models ────────────────────────────────────────────────────────────────────

class PlayerInfo(BaseModel):
    name: str
    team: str
    role: str
    is_impact_player: bool


class FanSessionRequest(BaseModel):
    team: Optional[FantasyTeam] = None       # custom team
    preset: Optional[str] = None             # "safe_pick" | "differential" | "finisher_fan"
    match_id: str = "1359487"


class FanSessionResponse(BaseModel):
    session_id: str
    team_name: str
    captain: str
    vice_captain: str
    players: List[str]
    is_valid: bool
    validation_errors: List[str] = []


class FanStreamItem(BaseModel):
    stream_index: int
    item_type: str                          # "delivery" | "marker" | "key_moment"
    delivery: Optional[Dict[str, Any]] = None
    marker: Optional[Dict[str, Any]] = None
    # Fan-specific additions
    team_points: Optional[float] = None
    points_delta: Optional[float] = None
    simulated_rank: Optional[int] = None
    rank_movement: Optional[int] = None
    rank_label: str = "simulated rank among 10,000 sample teams"
    key_moment: Optional[Dict[str, Any]] = None


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/players", response_model=List[PlayerInfo])
def list_players():
    """List all 24 pickable players with role, team and impact-player flag."""
    result = []
    for name in _engine.pickable_players:
        status = _engine.player_status[name]
        result.append(PlayerInfo(
            name=name,
            team=_engine.player_teams[name],
            role=_engine.player_roles[name],
            is_impact_player=status["is_impact_player"],
        ))
    return sorted(result, key=lambda p: (p.team, p.role, p.name))


@router.post("/teams/validate", response_model=ValidationResult)
def validate_team(team: FantasyTeam):
    """Validate a fantasy team against all rules."""
    return _engine.validate_team(team)


@router.get("/teams/presets")
def list_presets():
    """List available preset team names."""
    return {
        "presets": [
            {"key": k, "name": v.name, "captain": v.captain, "vice_captain": v.vice_captain}
            for k, v in PRESET_TEAMS.items()
        ]
    }


@router.post("/fan/sessions", response_model=FanSessionResponse)
def create_fan_session(request: FanSessionRequest):
    """
    Create a fan session tied to a fantasy team.
    Accepts either a preset name or a custom FantasyTeam.
    """
    if request.preset:
        team = PRESET_TEAMS.get(request.preset)
        if team is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown preset '{request.preset}'. Valid: {list(PRESET_TEAMS.keys())}"
            )
    elif request.team:
        team = request.team
    else:
        raise HTTPException(status_code=400, detail="Provide either 'preset' or 'team'")

    validation = _engine.validate_team(team)
    if not validation.is_valid:
        raise HTTPException(
            status_code=422,
            detail={"message": "Team validation failed", "errors": validation.errors}
        )

    api_key = settings.GEMINI_API_KEY or ""
    session = fan_session_manager.create(
        fan_team=team,
        match_id=request.match_id,
        ai_api_key=api_key,
    )

    return FanSessionResponse(
        session_id=session.session_id,
        team_name=team.name or "My Fantasy XI",
        captain=team.captain,
        vice_captain=team.vice_captain,
        players=team.players,
        is_valid=True,
    )


@router.get("/fan/sessions/{session_id}")
def get_fan_session(session_id: str):
    """Get current state of a fan session."""
    session = fan_session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Fan session not found")
    return {
        "session_id": session_id,
        "delivery_count": session.delivery_count,
        "team_total": session.team_total_history[-1] if session.team_total_history else 0.0,
        "current_rank": session.rank_history[-1] if session.rank_history else 10000,
        "key_moment_count": len(session.key_moments),
        "is_finished": session.is_finished,
    }


@router.get("/fan/sessions/{session_id}/summary", response_model=MatchReplaySummary)
def get_fan_summary(session_id: str):
    """Get the final match summary for a fan session."""
    session = fan_session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Fan session not found")
    return session.get_final_summary()


@router.get("/fan/sessions/{session_id}/stream")
async def fan_stream(
    session_id: str,
    speed: str = Query("1x", description="1x | 2x | 5x | instant"),
):
    """
    SSE stream that delivers match events with fantasy points, rank, and AI explanations.
    Each message is a JSON-encoded FanStreamItem.
    Markers: REPLAY_STARTED, INNINGS_BREAK, MATCH_FINISHED (with final summary).
    """
    session = fan_session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Fan session not found")

    # Speed → interval in seconds
    speed_map = {"1x": 2.0, "2x": 1.0, "5x": 0.4, "instant": 0.0}
    interval = speed_map.get(speed, 2.0)

    all_items = load_match_stream_items(session.match_id)

    # Normalise: load_match_stream_items returns StreamItem objects
    async def event_generator():
        idx = 0
        for stream_item in all_items:
            # Determine type (StreamItem pydantic model)
            item_type = stream_item.item_type

            if item_type == "marker":
                marker_data = stream_item.marker.model_dump() if stream_item.marker else {}
                payload = {
                    "stream_index": idx,
                    "item_type": "marker",
                    "marker": marker_data,
                    "team_points": session.team_total_history[-1] if session.team_total_history else 0.0,
                    "simulated_rank": session.rank_history[-1] if session.rank_history else 10000,
                    "rank_label": "simulated rank among 10,000 sample teams",
                }
                # If this is MATCH_FINISHED, attach summary
                marker_type = marker_data.get("marker_type", "")
                if marker_type == "match_finished":
                    session.is_finished = True
                    summary = session.get_final_summary()
                    payload["final_summary"] = summary.model_dump()
                yield f"data: {json.dumps(payload)}\n\n"

            elif item_type == "delivery":
                delivery_data = stream_item.delivery
                if delivery_data is None:
                    continue
                ev_dict = delivery_data.model_dump()

                # Process through fan session
                total_after, delta, rank_after, km_result = session.process_one_delivery(ev_dict)
                rank_before = session.rank_history[-2] if len(session.rank_history) >= 2 else rank_after

                # AI explanation for key moments
                km_payload = None
                if km_result and km_result.facts_packet:
                    # Fetch AI explanation (from cache or generate)
                    try:
                        explanation = await get_explanation(
                            km_result.facts_packet,
                            session.ai_api_key,
                        )
                        km_result.explanation = explanation
                    except Exception as e:
                        logger.warning(f"AI explanation failed: {e}")
                        km_result.explanation = None

                    km_payload = {
                        "is_key_moment": True,
                        "reasons": km_result.reasons,
                        "facts": km_result.facts_packet.model_dump(),
                        "explanation": km_result.explanation.model_dump() if km_result.explanation else None,
                    }

                payload = {
                    "stream_index": idx,
                    "item_type": "delivery",
                    "delivery": ev_dict,
                    "team_points": total_after,
                    "points_delta": delta,
                    "simulated_rank": rank_after,
                    "rank_movement": rank_before - rank_after,
                    "rank_label": "simulated rank among 10,000 sample teams",
                    "key_moment": km_payload,
                }
                yield f"data: {json.dumps(payload)}\n\n"

                if interval > 0:
                    await asyncio.sleep(interval)

            idx += 1

        # Final signal
        yield "data: {\"stream_index\": -1, \"item_type\": \"stream_end\"}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

