from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ScoringConfig(BaseModel):
    batting: dict
    strike_rate: dict
    bowling: dict
    economy_rate: dict
    fielding: dict
    other: dict
    switches: dict
    multipliers: dict
    team_rules: dict


class FantasyTeam(BaseModel):
    name: Optional[str] = "My Fantasy XI"
    players: List[str]  # Exactly 11 player names
    captain: str
    vice_captain: str


class ValidationResult(BaseModel):
    is_valid: bool
    errors: List[str] = []


class PlayerPointsBreakdown(BaseModel):
    player_name: str
    team: str
    role: str
    # Batting
    batting_runs: float = 0.0
    batting_fours: float = 0.0
    batting_sixes: float = 0.0
    batting_milestone: float = 0.0
    batting_duck: float = 0.0
    batting_strike_rate: float = 0.0
    # Bowling
    bowling_wickets: float = 0.0
    bowling_bowled_lbw: float = 0.0
    bowling_milestone: float = 0.0
    bowling_maidens: float = 0.0
    bowling_economy: float = 0.0
    # Fielding
    fielding_catches: float = 0.0
    fielding_stumpings: float = 0.0
    fielding_runouts: float = 0.0
    # Other
    other_starting_xi: float = 0.0
    # Total
    total: float = 0.0

    @property
    def category_totals(self) -> Dict[str, float]:
        return {
            "batting": round(
                self.batting_runs
                + self.batting_fours
                + self.batting_sixes
                + self.batting_milestone
                + self.batting_duck
                + self.batting_strike_rate,
                2,
            ),
            "bowling": round(
                self.bowling_wickets
                + self.bowling_bowled_lbw
                + self.bowling_milestone
                + self.bowling_maidens
                + self.bowling_economy,
                2,
            ),
            "fielding": round(
                self.fielding_catches
                + self.fielding_stumpings
                + self.fielding_runouts,
                2,
            ),
            "other": round(self.other_starting_xi, 2),
            "total": round(self.total, 2),
        }


class TeamPointsSnapshot(BaseModel):
    delivery_index: int
    team_total: float
    delivery_delta: float
    player_points: Dict[str, float]


class RankSnapshot(BaseModel):
    delivery_index: int
    team_total: float
    simulated_rank: int
    percentile: float
    rank_change: int
    label: str = "simulated rank among 10,000 sample teams"

