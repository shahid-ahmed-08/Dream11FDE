from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AffectedPlayerInfo(BaseModel):
    player_name: str
    team: str
    role: str
    multiplier: float
    is_captain: bool
    is_vice_captain: bool
    raw_delta: float
    weighted_delta: float
    current_player_total: float


class FactsPacket(BaseModel):
    delivery_index: int
    ball_display: str
    innings: int
    match_situation: str
    event_description: str
    is_wicket: bool
    is_six: bool
    is_milestone: bool
    is_hattrick: bool
    affected_fan_players: List[AffectedPlayerInfo] = []
    team_total_before: float
    team_total_after: float
    team_delta: float
    simulated_rank_before: int
    simulated_rank_after: int
    rank_movement: int
    rank_label: str = "simulated rank among 10,000 sample teams"
    points_rose_but_rank_dropped: bool = False
    upcoming_thresholds: List[str] = []
    packet_hash: str


class AIExplanation(BaseModel):
    explanation_en: str
    explanation_hi: str
    watch_next_en: str
    watch_next_hi: str
    is_fallback: bool = False
    validation_passed: bool = True
    ai_error: Optional[str] = None


class KeyMomentResult(BaseModel):
    is_key_moment: bool
    reasons: List[str] = []
    facts_packet: Optional[FactsPacket] = None
    explanation: Optional[AIExplanation] = None


class OptimalCaptainAnalysis(BaseModel):
    current_captain: str
    current_team_score: float
    optimal_captain: str
    optimal_team_score: float
    score_difference: float


class MatchReplaySummary(BaseModel):
    fan_team_name: str
    final_points: float
    final_simulated_rank: int
    percentile: float
    rank_label: str = "simulated rank among 10,000 sample teams"
    total_key_moments: int
    best_moment: Optional[Dict[str, Any]] = None
    worst_moment: Optional[Dict[str, Any]] = None
    optimal_captain_analysis: Optional[OptimalCaptainAnalysis] = None

