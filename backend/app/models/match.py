from typing import List, Optional
from pydantic import BaseModel


class FielderInfo(BaseModel):
    name: str
    substitute: bool = False


class WicketInfo(BaseModel):
    player_out: str
    kind: str
    fielders: List[FielderInfo] = []


class ExtrasBreakdown(BaseModel):
    wides: int = 0
    noballs: int = 0
    byes: int = 0
    legbyes: int = 0
    penalty: int = 0


class MatchSituation(BaseModel):
    score: int
    wickets: int
    legal_balls_bowled: int
    overs_completed: str
    target: Optional[int] = None
    runs_needed: Optional[int] = None
    balls_remaining: Optional[int] = None
    current_run_rate: float = 0.0
    required_run_rate: Optional[float] = None


class BallEvent(BaseModel):
    event_id: str
    match_id: str
    innings: int
    batting_team: str
    bowling_team: str
    over_number: int
    over_index: int
    ball_in_over: int
    ball_display: str
    delivery_in_innings: int
    is_legal_delivery: bool
    batter: str
    non_striker: str
    bowler: str
    runs_batter: int
    runs_extras: int
    runs_total: int
    extras: ExtrasBreakdown
    is_wicket: bool
    wickets: List[WicketInfo] = []
    situation: MatchSituation


class Player(BaseModel):
    name: str
    full_name: str
    cricsheet_id: str
    team: str
    role: str  # Strictly one of: 'Wicketkeeper', 'Batter', 'All-Rounder', 'Bowler'
    is_playing_xi: bool
    is_impact_player: bool
    is_substitute: bool
    notes: Optional[str] = None


class TeamSquad(BaseModel):
    name: str
    short_name: str
    captain: str
    wicketkeeper: str
    players: List[Player]


class SquadsResponse(BaseModel):
    match_id: str
    teams: dict[str, TeamSquad]


class MatchSummary(BaseModel):
    match_id: str
    season: str
    dates: List[str]
    venue: str
    city: str
    teams: List[str]
    toss: dict
    outcome: dict
    player_of_match: List[str]
    total_events: int
    innings_summaries: List[dict]

