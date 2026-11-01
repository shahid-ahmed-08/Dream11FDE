import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.config import settings
from backend.app.models.match import BallEvent
from backend.app.models.replay import (
    ControlAction,
    MarkerType,
    ReplayMarker,
    ReplaySpeed,
    SessionState,
    SessionStatus,
    SPEED_INTERVALS,
    StreamItem,
)


def load_match_stream_items(match_id: str = "1359487") -> List[StreamItem]:
    events_path = settings.DATA_DIR / "normalized" / f"{match_id}_events.json"
    raw_path = settings.DATA_DIR / "raw" / f"{match_id}.json"

    if not events_path.exists() or not raw_path.exists():
        raise FileNotFoundError(f"Match data files missing for ID {match_id}")

    with open(events_path, "r", encoding="utf-8") as f:
        events_data: List[Dict[str, Any]] = json.load(f)

    with open(raw_path, "r", encoding="utf-8") as f:
        raw_data: Dict[str, Any] = json.load(f)

    info = raw_data.get("info", {})

    inn1_events = [e for e in events_data if e["innings"] == 1]
    inn2_events = [e for e in events_data if e["innings"] == 2]

    stream_items: List[StreamItem] = []
    idx = 0

    # 1. REPLAY STARTED MARKER
    start_marker = ReplayMarker(
        marker_type=MarkerType.REPLAY_STARTED,
        payload={
            "match_id": match_id,
            "teams": info.get("teams", []),
            "venue": info.get("venue", ""),
            "city": info.get("city", ""),
            "dates": info.get("dates", []),
            "toss": info.get("toss", {}),
            "total_deliveries": len(events_data),
        },
    )
    stream_items.append(StreamItem(stream_index=idx, item_type="marker", marker=start_marker))
    idx += 1

    # 2. INNINGS 1 DELIVERIES
    for ev in inn1_events:
        ball_ev = BallEvent.model_validate(ev)
        stream_items.append(StreamItem(stream_index=idx, item_type="delivery", delivery=ball_ev))
        idx += 1

    # 3. INNINGS BREAK MARKER
    last_inn1 = inn1_events[-1]["situation"]
    break_marker = ReplayMarker(
        marker_type=MarkerType.INNINGS_BREAK,
        payload={
            "innings_completed": 1,
            "batting_team": inn1_events[0]["batting_team"],
            "score": last_inn1["score"],
            "wickets": last_inn1["wickets"],
            "overs": last_inn1["overs_completed"],
            "target": last_inn1["score"] + 1,
        },
    )
    stream_items.append(StreamItem(stream_index=idx, item_type="marker", marker=break_marker))
    idx += 1

    # 4. INNINGS 2 DELIVERIES
    for ev in inn2_events:
        ball_ev = BallEvent.model_validate(ev)
        stream_items.append(StreamItem(stream_index=idx, item_type="delivery", delivery=ball_ev))
        idx += 1

    # 5. MATCH FINISHED MARKER
    last_inn2 = inn2_events[-1]["situation"]
    finish_marker = ReplayMarker(
        marker_type=MarkerType.MATCH_FINISHED,
        payload={
            "outcome": info.get("outcome", {}),
            "winner": info.get("outcome", {}).get("winner", ""),
            "margin": info.get("outcome", {}).get("by", {}),
            "player_of_match": info.get("player_of_match", []),
            "final_score": f"{inn2_events[0]['batting_team']} {last_inn2['score']}/{last_inn2['wickets']} in {last_inn2['overs_completed']} ov",
        },
    )
    stream_items.append(StreamItem(stream_index=idx, item_type="marker", marker=finish_marker))

    return stream_items


class ReplaySession:
    def __init__(self, session_id: str, match_id: str = "1359487"):
        self.session_id = session_id
        self.match_id = match_id
        self.items: List[StreamItem] = load_match_stream_items(match_id)
        self.total_items = len(self.items)

        self.status = SessionStatus.INITIALIZED
        self.speed = ReplaySpeed.SPEED_1X
        self.current_index = 0  # Points to the next item to be consumed
        self.delivered_indices: List[int] = []

        # Lock for safe thread/task execution
        self._lock = asyncio.Lock()
        # Event flag to notify listeners when new items are ready or paused
        self._step_event = asyncio.Event()

    @property
    def interval_seconds(self) -> float:
        return SPEED_INTERVALS[self.speed]

    @property
    def is_finished(self) -> bool:
        return self.current_index >= self.total_items

    def get_state(self) -> SessionState:
        return SessionState(
            session_id=self.session_id,
            match_id=self.match_id,
            status=self.status,
            speed=self.speed,
            interval_seconds=self.interval_seconds,
            current_index=self.current_index,
            total_items=self.total_items,
            delivered_count=len(self.delivered_indices),
            is_finished=self.is_finished,
        )

    def start(self):
        if self.status != SessionStatus.FINISHED:
            self.status = SessionStatus.PLAYING
            self._step_event.set()

    def pause(self):
        if self.status == SessionStatus.PLAYING:
            self.status = SessionStatus.PAUSED
            self._step_event.clear()

    def resume(self):
        if self.status == SessionStatus.PAUSED:
            self.status = SessionStatus.PLAYING
            self._step_event.set()

    def restart(self):
        self.current_index = 0
        self.delivered_indices.clear()
        self.status = SessionStatus.PLAYING
        self._step_event.set()

    def set_speed(self, speed: ReplaySpeed):
        self.speed = speed

    def step(self, steps: int = 1) -> List[StreamItem]:
        """Deterministic step forward by N items (advances state immediately)."""
        emitted: List[StreamItem] = []
        for _ in range(steps):
            if self.current_index < self.total_items:
                item = self.items[self.current_index]
                self.delivered_indices.append(self.current_index)
                emitted.append(item)
                self.current_index += 1
            else:
                self.status = SessionStatus.FINISHED
                break

        if self.current_index >= self.total_items:
            self.status = SessionStatus.FINISHED

        return emitted

    def run_instant(self) -> List[StreamItem]:
        """Delivers all remaining items immediately to the end."""
        self.speed = ReplaySpeed.INSTANT
        self.status = SessionStatus.PLAYING
        remaining_count = self.total_items - self.current_index
        return self.step(remaining_count)

    def get_items_from(self, from_index: int = 0) -> List[StreamItem]:
        """
        Reconnect recovery: returns all items from from_index up to current_index.
        Guarantees that a reconnecting client receives exactly what they missed
        without duplicate or lost items.
        """
        if from_index < 0:
            from_index = 0
        if from_index > self.current_index:
            return []
        return self.items[from_index : self.current_index]

    def advance_one(self) -> Optional[StreamItem]:
        if self.current_index < self.total_items:
            item = self.items[self.current_index]
            self.delivered_indices.append(self.current_index)
            self.current_index += 1
            if self.current_index >= self.total_items:
                self.status = SessionStatus.FINISHED
            return item
        self.status = SessionStatus.FINISHED
        return None


class ReplayManager:
    def __init__(self):
        self._sessions: Dict[str, ReplaySession] = {}

    def create_session(self, match_id: str = "1359487") -> ReplaySession:
        session_id = str(uuid.uuid4())
        session = ReplaySession(session_id=session_id, match_id=match_id)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[ReplaySession]:
        return self._sessions.get(session_id)

    def remove_session(self, session_id: str):
        if session_id in self._sessions:
            del self._sessions[session_id]

    def active_session_count(self) -> int:
        return len(self._sessions)


replay_manager = ReplayManager()

