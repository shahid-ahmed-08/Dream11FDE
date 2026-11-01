"""
Fan Session Service
Wraps PointsEngine + SimulatedPoolManager + KeyMomentEngine + AIExplainer
into a per-fan-team replay experience.
"""
import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from backend.app.models.fantasy import FantasyTeam, PlayerPointsBreakdown
from backend.app.models.key_moment import (
    KeyMomentResult,
    MatchReplaySummary,
    OptimalCaptainAnalysis,
)
from backend.app.services.key_moment_engine import (
    build_facts_packet,
    is_key_moment,
    _load_km_config,
)
from backend.app.services.points_engine import PointsEngine
from backend.app.services.pool_generator import SimulatedPoolManager

logger = logging.getLogger(__name__)


class FanSession:
    """
    A single fan's replay session.
    Processes the match event-by-event, tracking points, rank, and key moments.
    """

    def __init__(
        self,
        session_id: str,
        fan_team: FantasyTeam,
        match_id: str = "1359487",
        ai_api_key: str = "",
    ):
        self.session_id = session_id
        self.fan_team = fan_team
        self.match_id = match_id
        self.ai_api_key = ai_api_key

        self.engine = PointsEngine(match_id=match_id)
        self.pool = SimulatedPoolManager(match_id=match_id)
        self.km_config = _load_km_config()

        # Running state
        self.delivery_count = 0  # how many deliveries processed so far
        self.team_total_history: List[float] = [self._team_total_from_snap(self.engine.points_history[0])]
        self.rank_history: List[int] = [self._get_rank_at(0)]
        self.key_moments: List[Dict[str, Any]] = []
        self.is_finished = False

    def _get_rank_at(self, delivery_index: int) -> int:
        """Get simulated rank at a given delivery index."""
        snap = self.pool.get_simulated_rank(self.fan_team, delivery_index)
        return snap.simulated_rank

    def _team_total_from_snap(self, snap: Dict[str, PlayerPointsBreakdown]) -> float:
        c_mult = self.engine.config.multipliers["captain"]
        vc_mult = self.engine.config.multipliers["vice_captain"]
        total = 0.0
        for p in self.fan_team.players:
            raw = snap[p].total if p in snap else 0.0
            mult = c_mult if p == self.fan_team.captain else (vc_mult if p == self.fan_team.vice_captain else 1.0)
            total += raw * mult
        return round(total, 2)

    def _team_total_as_captain(self, snap: Dict[str, PlayerPointsBreakdown], captain_candidate: str) -> float:
        """Compute what the fan's team total would be if `captain_candidate` were captain."""
        c_mult = self.engine.config.multipliers["captain"]
        vc_mult = self.engine.config.multipliers["vice_captain"]
        total = 0.0
        for p in self.fan_team.players:
            raw = snap[p].total if p in snap else 0.0
            if p == captain_candidate:
                mult = c_mult
            elif p == self.fan_team.vice_captain and p != captain_candidate:
                mult = vc_mult
            else:
                mult = 1.0
            total += raw * mult
        return round(total, 2)

    def process_one_delivery(
        self, delivery_event: Dict[str, Any]
    ) -> Tuple[float, float, int, Optional[KeyMomentResult]]:
        """
        Process one delivery event.
        Returns: (team_total_after, delta, rank_after, key_moment_result_or_None)
        """
        # Snapshots before
        prev_snap = self.engine.points_history[-1]
        batter_runs_before = {p: self.engine.batting_stats[p]["runs"] for p in self.engine.pickable_players}
        bowler_wickets_before = {p: self.engine.bowling_stats[p]["wickets"] for p in self.engine.pickable_players}

        # Process through points engine
        new_snap, _deltas = self.engine.process_delivery(delivery_event)

        batter_runs_after = {p: self.engine.batting_stats[p]["runs"] for p in self.engine.pickable_players}
        bowler_wickets_after = {p: self.engine.bowling_stats[p]["wickets"] for p in self.engine.pickable_players}

        # Team totals
        total_before = self.team_total_history[-1]
        total_after = self._team_total_from_snap(new_snap)
        team_delta = round(total_after - total_before, 2)
        self.team_total_history.append(total_after)

        # Rank from precomputed pool (delivery_index = engine.current_delivery_index)
        delivery_idx = self.engine.current_delivery_index  # 1-based after process_delivery
        rank_after = self._get_rank_at(delivery_idx)
        rank_before = self.rank_history[-1]
        self.rank_history.append(rank_after)

        self.delivery_count += 1

        # Key moment check
        is_km, reasons = is_key_moment(
            delivery_event=delivery_event,
            team_delta=team_delta,
            fan_team_players=self.fan_team.players,
            captain=self.fan_team.captain,
            vice_captain=self.fan_team.vice_captain,
            prev_player_totals={p: prev_snap[p].total if p in prev_snap else 0.0 for p in self.fan_team.players},
            curr_player_totals={p: new_snap[p].total if p in new_snap else 0.0 for p in self.fan_team.players},
            bowler_wickets_before=bowler_wickets_before,
            bowler_wickets_after=bowler_wickets_after,
            batter_runs_before=batter_runs_before,
            batter_runs_after=batter_runs_after,
            km_config=self.km_config,
        )

        km_result = None
        if is_km:
            facts = build_facts_packet(
                delivery_index=delivery_idx - 1,  # 0-based index for packet reference
                delivery_event=delivery_event,
                fan_team=self.fan_team,
                team_total_before=total_before,
                team_total_after=total_after,
                rank_before=rank_before,
                rank_after=rank_after,
                prev_snap=prev_snap,
                curr_snap=new_snap,
                reasons=reasons,
                km_config=self.km_config,
                player_teams=self.engine.player_teams,
                player_roles=self.engine.player_roles,
                batting_stats=self.engine.batting_stats,
                bowling_stats=self.engine.bowling_stats,
            )
            km_result = KeyMomentResult(
                is_key_moment=True,
                reasons=reasons,
                facts_packet=facts,
                explanation=None,  # AI explanation filled in async by route handler
            )
            self.key_moments.append({
                "delivery_index": delivery_idx - 1,
                "ball_display": delivery_event.get("ball_display", ""),
                "reasons": reasons,
                "team_delta": team_delta,
                "team_total_after": total_after,
                "rank_after": rank_after,
                "facts_packet": facts,
            })

        return total_after, team_delta, rank_after, km_result

    def get_final_summary(self) -> MatchReplaySummary:
        """Build the final match summary after all events have been processed."""
        final_total = self.team_total_history[-1] if self.team_total_history else 0.0
        final_rank = self.rank_history[-1] if self.rank_history else 10000
        percentile = round((1 - final_rank / 10000) * 100, 1)

        best = None
        worst = None
        if self.key_moments:
            best_km = max(self.key_moments, key=lambda k: k["team_delta"])
            worst_km = min(self.key_moments, key=lambda k: k["team_delta"])
            best = {
                "ball": best_km["ball_display"],
                "reasons": best_km["reasons"],
                "team_delta": best_km["team_delta"],
                "team_total_after": best_km["team_total_after"],
            }
            worst = {
                "ball": worst_km["ball_display"],
                "reasons": worst_km["reasons"],
                "team_delta": worst_km["team_delta"],
                "team_total_after": worst_km["team_total_after"],
            }

        # Optimal captain from final snap
        final_snap = self.engine.points_history[-1]
        optimal_cap = self.fan_team.captain
        optimal_total = final_total
        for p in self.fan_team.players:
            candidate_total = self._team_total_as_captain(final_snap, p)
            if candidate_total > optimal_total:
                optimal_total = candidate_total
                optimal_cap = p

        cap_analysis = OptimalCaptainAnalysis(
            current_captain=self.fan_team.captain,
            current_team_score=final_total,
            optimal_captain=optimal_cap,
            optimal_team_score=optimal_total,
            score_difference=round(optimal_total - final_total, 2),
        )

        return MatchReplaySummary(
            fan_team_name=self.fan_team.name or "My Fantasy XI",
            final_points=final_total,
            final_simulated_rank=final_rank,
            percentile=percentile,
            total_key_moments=len(self.key_moments),
            best_moment=best,
            worst_moment=worst,
            optimal_captain_analysis=cap_analysis,
        )


class FanSessionManager:
    """Global store for all active FanSession objects."""

    def __init__(self):
        self._sessions: Dict[str, FanSession] = {}

    def create(self, fan_team: FantasyTeam, match_id: str = "1359487", ai_api_key: str = "") -> FanSession:
        session_id = str(uuid.uuid4())
        session = FanSession(
            session_id=session_id,
            fan_team=fan_team,
            match_id=match_id,
            ai_api_key=ai_api_key,
        )
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Optional[FanSession]:
        return self._sessions.get(session_id)

    def delete(self, session_id: str):
        self._sessions.pop(session_id, None)

    def list_ids(self) -> List[str]:
        return list(self._sessions.keys())


# Singleton
fan_session_manager = FanSessionManager()
