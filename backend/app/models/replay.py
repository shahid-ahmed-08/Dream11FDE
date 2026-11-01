from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field

from backend.app.models.match import BallEvent


class SessionStatus(str, Enum):
    INITIALIZED = "initialized"
    PLAYING = "playing"
    PAUSED = "paused"
    FINISHED = "finished"


class ReplaySpeed(str, Enum):
    SPEED_1X = "1x"
    SPEED_2X = "2x"
    SPEED_5X = "5x"
    INSTANT = "instant"


SPEED_INTERVALS = {
    ReplaySpeed.SPEED_1X: 2.0,
    ReplaySpeed.SPEED_2X: 1.0,
    ReplaySpeed.SPEED_5X: 0.4,
    ReplaySpeed.INSTANT: 0.0,
}


class MarkerType(str, Enum):
    REPLAY_STARTED = "replay_started"
    INNINGS_BREAK = "innings_break"
    MATCH_FINISHED = "match_finished"


class ReplayMarker(BaseModel):
    marker_type: MarkerType
    timestamp_virtual: float = 0.0
    payload: Dict[str, Any]


class StreamItem(BaseModel):
    stream_index: int
    item_type: Literal["marker", "delivery"]
    marker: Optional[ReplayMarker] = None
    delivery: Optional[BallEvent] = None


class SessionState(BaseModel):
    session_id: str
    match_id: str
    status: SessionStatus
    speed: ReplaySpeed
    interval_seconds: float
    current_index: int
    total_items: int
    delivered_count: int
    is_finished: bool


class ControlAction(str, Enum):
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    RESTART = "restart"
    SET_SPEED = "set_speed"


class ControlRequest(BaseModel):
    action: ControlAction
    speed: Optional[ReplaySpeed] = None

