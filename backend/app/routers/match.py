import json
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query

from backend.app.config import settings
from backend.app.models.match import (
    BallEvent,
    SquadsResponse,
    MatchSummary,
)

router = APIRouter(prefix="/api/match", tags=["match"])


def get_data_paths(match_id: str):
    raw_file = settings.DATA_DIR / "raw" / f"{match_id}.json"
    events_file = settings.DATA_DIR / "normalized" / f"{match_id}_events.json"
    squads_file = settings.DATA_DIR / "normalized" / f"{match_id}_squads.json"
    return raw_file, events_file, squads_file


@router.get("/summary", response_model=MatchSummary)
def get_match_summary(match_id: Optional[str] = None):
    mid = match_id or settings.MATCH_ID
    raw_file, events_file, _ = get_data_paths(mid)

    if not raw_file.exists():
        raise HTTPException(status_code=404, detail=f"Match raw data not found for ID {mid}")

    with open(raw_file, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    events = []
    if events_file.exists():
        with open(events_file, "r", encoding="utf-8") as f:
            events = json.load(f)

    info = raw_data.get("info", {})

    # Calculate summaries
    innings_summaries = []
    for inn_idx in [1, 2]:
        inn_events = [e for e in events if e["innings"] == inn_idx]
        if inn_events:
            last = inn_events[-1]
            innings_summaries.append({
                "innings": inn_idx,
                "team": inn_events[0]["batting_team"],
                "total_events": len(inn_events),
                "score": last["situation"]["score"],
                "wickets": last["situation"]["wickets"],
                "overs": last["situation"]["overs_completed"],
            })

    return MatchSummary(
        match_id=mid,
        season=str(info.get("season", "2023")),
        dates=info.get("dates", []),
        venue=info.get("venue", ""),
        city=info.get("city", ""),
        teams=info.get("teams", []),
        toss=info.get("toss", {}),
        outcome=info.get("outcome", {}),
        player_of_match=info.get("player_of_match", []),
        total_events=len(events),
        innings_summaries=innings_summaries,
    )


@router.get("/squads", response_model=SquadsResponse)
def get_match_squads(match_id: Optional[str] = None):
    mid = match_id or settings.MATCH_ID
    _, _, squads_file = get_data_paths(mid)

    if not squads_file.exists():
        raise HTTPException(status_code=404, detail=f"Squads data not found for ID {mid}")

    with open(squads_file, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/events", response_model=List[BallEvent])
def get_match_events(
    match_id: Optional[str] = None,
    innings: Optional[int] = None,
    limit: Optional[int] = None,
):
    mid = match_id or settings.MATCH_ID
    _, events_file, _ = get_data_paths(mid)

    if not events_file.exists():
        raise HTTPException(status_code=404, detail=f"Events data not found for ID {mid}")

    with open(events_file, "r", encoding="utf-8") as f:
        events = json.load(f)

    if innings is not None and isinstance(innings, int):
        events = [e for e in events if e["innings"] == innings]

    if limit is not None and isinstance(limit, int):
        events = events[:limit]

    return events


@router.get("/events/{event_id}", response_model=BallEvent)
def get_event_by_id(event_id: str, match_id: Optional[str] = None):
    mid = match_id or settings.MATCH_ID
    _, events_file, _ = get_data_paths(mid)

    if not events_file.exists():
        raise HTTPException(status_code=404, detail=f"Events data not found for ID {mid}")

    with open(events_file, "r", encoding="utf-8") as f:
        events = json.load(f)

    for event in events:
        if event["event_id"] == event_id:
            return event

    raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
