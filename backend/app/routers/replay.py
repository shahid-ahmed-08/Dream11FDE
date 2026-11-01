import asyncio
import json
from typing import List, Optional
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from backend.app.models.replay import (
    ControlAction,
    ControlRequest,
    ReplaySpeed,
    SessionState,
    SessionStatus,
    StreamItem,
)
from backend.app.services.replay_engine import replay_manager

router = APIRouter(prefix="/api/replay", tags=["replay"])


@router.post("/sessions", response_model=SessionState)
def create_replay_session(match_id: Optional[str] = Query("1359487")):
    session = replay_manager.create_session(match_id=match_id)
    return session.get_state()


@router.get("/sessions/{session_id}", response_model=SessionState)
def get_session_state(session_id: str):
    session = replay_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.get_state()


@router.post("/sessions/{session_id}/control", response_model=SessionState)
def control_session(session_id: str, request: ControlRequest):
    session = replay_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if request.action == ControlAction.START:
        session.start()
    elif request.action == ControlAction.PAUSE:
        session.pause()
    elif request.action == ControlAction.RESUME:
        session.resume()
    elif request.action == ControlAction.RESTART:
        session.restart()
    elif request.action == ControlAction.SET_SPEED:
        if not request.speed:
            raise HTTPException(status_code=400, detail="Speed parameter required for set_speed action")
        session.set_speed(request.speed)

    return session.get_state()


@router.post("/sessions/{session_id}/step", response_model=List[StreamItem])
def step_session(session_id: str, steps: int = Query(1, ge=1)):
    session = replay_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.step(steps=steps)


@router.post("/sessions/{session_id}/instant", response_model=List[StreamItem])
def run_session_instant(session_id: str):
    session = replay_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.run_instant()


@router.get("/sessions/{session_id}/events", response_model=List[StreamItem])
def get_session_events(
    session_id: str,
    from_index: int = Query(0, ge=0, description="Resume stream from this index (0-based)"),
):
    session = replay_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.get_items_from(from_index=from_index)


@router.get("/sessions/{session_id}/stream")
async def stream_replay(
    session_id: str,
    request: Request,
    from_index: Optional[int] = Query(None, description="Explicit resume index"),
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
):
    session = replay_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Determine starting index from Last-Event-ID header or from_index query
    start_index = 0
    if from_index is not None:
        start_index = max(0, from_index)
    elif last_event_id is not None:
        try:
            start_index = max(0, int(last_event_id) + 1)
        except ValueError:
            start_index = 0

    async def event_generator():
        # First deliver any past items that were missed up to session.current_index
        missed_items = session.get_items_from(from_index=start_index)
        for item in missed_items:
            data = item.model_dump_json()
            yield f"id: {item.stream_index}\nevent: replay_item\ndata: {data}\n\n"

        # Now live stream subsequent items
        while not session.is_finished:
            if await request.is_disconnected():
                break

            if session.status == SessionStatus.PAUSED:
                await asyncio.sleep(0.2)
                continue

            if session.status != SessionStatus.PLAYING:
                await asyncio.sleep(0.2)
                continue

            item = session.advance_one()
            if item is not None:
                data = item.model_dump_json()
                yield f"id: {item.stream_index}\nevent: replay_item\ndata: {data}\n\n"

            interval = session.interval_seconds
            if interval > 0:
                await asyncio.sleep(interval)
            else:
                # Instant mode or tight loop: yield control momentarily
                await asyncio.sleep(0)

        # Notify stream completion
        yield "event: complete\ndata: {\"finished\": true}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

