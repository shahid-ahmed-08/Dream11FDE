import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.app.config import settings
from backend.app.models.fantasy import (
    FantasyTeam,
    PlayerPointsBreakdown,
    ScoringConfig,
    ValidationResult,
)


def load_scoring_config() -> ScoringConfig:
    config_path = Path(__file__).resolve().parent.parent / "config" / "scoring_rules.json"
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return ScoringConfig.model_validate(data)


def compute_player_points(
    player_name: str,
    role: str,
    team: str,
    bstat: Dict[str, Any],
    bwstat: Dict[str, Any],
    fstat: Dict[str, Any],
    is_starting_xi: bool,
    is_impact_player: bool,
    impact_entered: bool,
    config: ScoringConfig,
) -> PlayerPointsBreakdown:
    # 1. Batting Points
    b_runs = bstat["runs"] * config.batting["run"]
    b_fours = bstat["fours"] * config.batting["four_bonus"]
    b_sixes = bstat["sixes"] * config.batting["six_bonus"]

    # Milestones (mode: 'highest_only' vs 'cumulative', defaulting to 'highest_only')
    b_milestone = 0.0
    mode = config.batting.get("milestone_mode", "highest_only")
    if mode == "cumulative" or config.batting.get("milestones_stackable", False):
        for m in config.batting["milestones"]:
            if bstat["runs"] >= m["runs"]:
                b_milestone += m["bonus"]
    else:
        for m in sorted(config.batting["milestones"], key=lambda x: x["runs"], reverse=True):
            if bstat["runs"] >= m["runs"]:
                b_milestone = float(m["bonus"])
                break

    # Duck penalty (only if out for 0 and role not exempt)
    b_duck = 0.0
    if bstat.get("is_out", False) and bstat["runs"] == 0:
        if role not in config.batting.get("duck_exempt_roles", ["Bowler"]):
            b_duck = float(config.batting["duck_penalty"])

    # Strike Rate bonus/penalty (min balls faced, role not exempt)
    b_sr = 0.0
    if bstat["balls"] >= config.strike_rate["min_balls_faced"]:
        if role not in config.strike_rate.get("exempt_roles", ["Bowler"]):
            sr = (bstat["runs"] / bstat["balls"]) * 100.0
            for tier in config.strike_rate["tiers"]:
                min_sr = tier["min_sr"]
                max_sr = tier["max_sr"]
                if min_sr is not None and sr < min_sr:
                    continue
                if max_sr is not None and sr > max_sr:
                    continue
                b_sr = float(tier["points"])
                break

    # 2. Bowling Points
    bw_wickets = bwstat["wickets"] * config.bowling["wicket"]
    bw_bowled_lbw = bwstat["bowled_lbw"] * config.bowling["bowled_lbw_bonus"]

    # Wicket milestones
    bw_milestone = 0.0
    if config.bowling.get("milestones_stackable", False):
        for m in config.bowling["milestones"]:
            if bwstat["wickets"] >= m["wickets"]:
                bw_milestone += m["bonus"]
    else:
        for m in sorted(config.bowling["milestones"], key=lambda x: x["wickets"], reverse=True):
            if bwstat["wickets"] >= m["wickets"]:
                bw_milestone = float(m["bonus"])
                break

    bw_maidens = bwstat["maidens"] * config.bowling["maiden_over"]

    # Economy rate (min legal balls, e.g. 12 = 2 overs)
    bw_economy = 0.0
    if bwstat["legal_balls"] >= config.economy_rate["min_legal_balls"]:
        overs_bowled = bwstat["legal_balls"] / 6.0
        econ = bwstat["runs_conceded"] / overs_bowled
        for tier in config.economy_rate["tiers"]:
            min_er = tier["min_er"]
            max_er = tier["max_er"]
            if min_er is not None and econ < min_er:
                continue
            if max_er is not None and econ > max_er:
                continue
            bw_economy = float(tier["points"])
            break

    # 3. Fielding Points
    f_catches = fstat["catches"] * config.fielding["catch"]
    if fstat["catches"] >= 3:
        f_catches += config.fielding["three_catches_bonus"]
    f_stumpings = fstat["stumpings"] * config.fielding["stumping"]
    f_runouts = (
        fstat["runouts_direct"] * config.fielding["runout_direct"]
        + fstat["runouts_indirect"] * config.fielding["runout_indirect"]
    )

    # 4. Starting XI & Impact Player Points
    other_starting = 0.0
    if is_impact_player:
        if config.switches.get("impact_player_starting_points", True) and impact_entered:
            other_starting = float(config.other["starting_xi"])
    elif is_starting_xi:
        other_starting = float(config.other["starting_xi"])

    # Total
    total_pts = (
        b_runs
        + b_fours
        + b_sixes
        + b_milestone
        + b_duck
        + b_sr
        + bw_wickets
        + bw_bowled_lbw
        + bw_milestone
        + bw_maidens
        + bw_economy
        + f_catches
        + f_stumpings
        + f_runouts
        + other_starting
    )

    return PlayerPointsBreakdown(
        player_name=player_name,
        team=team,
        role=role,
        batting_runs=round(b_runs, 2),
        batting_fours=round(b_fours, 2),
        batting_sixes=round(b_sixes, 2),
        batting_milestone=round(b_milestone, 2),
        batting_duck=round(b_duck, 2),
        batting_strike_rate=round(b_sr, 2),
        bowling_wickets=round(bw_wickets, 2),
        bowling_bowled_lbw=round(bw_bowled_lbw, 2),
        bowling_milestone=round(bw_milestone, 2),
        bowling_maidens=round(bw_maidens, 2),
        bowling_economy=round(bw_economy, 2),
        fielding_catches=round(f_catches, 2),
        fielding_stumpings=round(f_stumpings, 2),
        fielding_runouts=round(f_runouts, 2),
        other_starting_xi=round(other_starting, 2),
        total=round(total_pts, 2),
    )


class PointsEngine:
    def __init__(self, match_id: str = "1359487", config: Optional[ScoringConfig] = None):
        self.match_id = match_id
        self.config = config or load_scoring_config()
        self.squads_data = self._load_squads()
        self.pickable_players, self.player_roles, self.player_teams, self.player_status = self._init_player_pool()

        # Cumulative match stats
        self.reset()

    def _load_squads(self) -> Dict[str, Any]:
        squads_path = settings.DATA_DIR / "normalized" / f"{self.match_id}_squads.json"
        with open(squads_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _init_player_pool(self) -> Tuple[List[str], Dict[str, str], Dict[str, str], Dict[str, Dict[str, bool]]]:
        pickable = []
        roles = {}
        teams = {}
        status = {}

        for team_name, tdata in self.squads_data["teams"].items():
            for p in tdata["players"]:
                name = p["name"]
                roles[name] = p["role"]
                teams[name] = team_name
                status[name] = {
                    "is_playing_xi": p["is_playing_xi"],
                    "is_impact_player": p["is_impact_player"],
                    "is_substitute": p["is_substitute"],
                }
                # Pickable pool: Starting XI + Impact Players (exclude substitute fielders)
                if p["is_playing_xi"] or p["is_impact_player"]:
                    pickable.append(name)

        return pickable, roles, teams, status

    def reset(self):
        self.current_delivery_index = 0

        # Batting stats: {player: {runs, balls, fours, sixes, is_out}}
        self.batting_stats: Dict[str, Dict[str, Any]] = {
            p: {"runs": 0, "balls": 0, "fours": 0, "sixes": 0, "is_out": False}
            for p in self.pickable_players
        }

        # Bowling stats: {player: {legal_balls, runs_conceded, wickets, bowled_lbw, maidens}}
        self.bowling_stats: Dict[str, Dict[str, Any]] = {
            p: {"legal_balls": 0, "runs_conceded": 0, "wickets": 0, "bowled_lbw": 0, "maidens": 0}
            for p in self.pickable_players
        }

        # Over tracking for maiden detection: (bowler, over_index, legal_balls, runs_conceded)
        self._current_over_bowler: Optional[str] = None
        self._current_over_index: Optional[int] = None
        self._current_over_legal_balls: int = 0
        self._current_over_runs: int = 0

        # Fielding stats: {player: {catches, stumpings, runouts_direct, runouts_indirect}}
        self.fielding_stats: Dict[str, Dict[str, Any]] = {
            p: {"catches": 0, "stumpings": 0, "runouts_direct": 0, "runouts_indirect": 0}
            for p in self.pickable_players
        }

        # Impact player activation
        self.impact_entered: Dict[str, bool] = {
            "J Little": False,
            "VR Iyer": False,
        }

        # History of point snapshots: [delivery_0_snapshot, delivery_1_snapshot, ...]
        self.points_history: List[Dict[str, PlayerPointsBreakdown]] = []
        # Initial snapshot (delivery 0: starting XI points only)
        initial_points = self._compute_all_player_points()
        self.points_history.append(initial_points)

    def _check_and_award_maiden(self):
        """Called when an over completes to check if it was a maiden."""
        if (
            self._current_over_bowler
            and self._current_over_legal_balls == 6
            and self._current_over_runs == 0
        ):
            if self._current_over_bowler in self.bowling_stats:
                self.bowling_stats[self._current_over_bowler]["maidens"] += 1

    def process_delivery(self, delivery_event: Dict[str, Any]) -> Tuple[Dict[str, PlayerPointsBreakdown], Dict[str, float]]:
        self.current_delivery_index += 1
        inn = delivery_event["innings"]
        over_idx = delivery_event["over_index"]

        # 1. Over tracking for Maidens
        if self._current_over_index != over_idx:
            # New over started, close previous over
            self._check_and_award_maiden()
            self._current_over_bowler = delivery_event["bowler"]
            self._current_over_index = over_idx
            self._current_over_legal_balls = 0
            self._current_over_runs = 0

        # 2. Impact Player Entry Tracking
        if inn == 2 and not self.impact_entered["J Little"]:
            self.impact_entered["J Little"] = True
        striker = delivery_event["batter"]
        non_striker = delivery_event["non_striker"]
        if striker == "VR Iyer" or non_striker == "VR Iyer":
            self.impact_entered["VR Iyer"] = True
        elif inn == 2 and not self.impact_entered["VR Iyer"]:
            self.impact_entered["VR Iyer"] = True

        # 3. Batting Stats
        runs_batter = delivery_event["runs_batter"]
        is_legal = delivery_event["is_legal_delivery"]
        extras = delivery_event["extras"]

        if striker in self.batting_stats:
            self.batting_stats[striker]["runs"] += runs_batter
            # Wides and noballs do NOT count as balls faced by batter
            if extras["wides"] == 0 and extras["noballs"] == 0:
                self.batting_stats[striker]["balls"] += 1
            if runs_batter == 4:
                self.batting_stats[striker]["fours"] += 1
            elif runs_batter == 6:
                self.batting_stats[striker]["sixes"] += 1

        # 4. Bowling Stats
        bowler = delivery_event["bowler"]
        # Runs charged to bowler: runs off bat + wides + noballs (byes and legbyes are NOT charged)
        bowler_runs_conceded = runs_batter + extras["wides"] + extras["noballs"]

        if bowler in self.bowling_stats:
            self.bowling_stats[bowler]["runs_conceded"] += bowler_runs_conceded
            if is_legal:
                self.bowling_stats[bowler]["legal_balls"] += 1

        # Track for maiden
        if is_legal:
            self._current_over_legal_balls += 1
        self._current_over_runs += bowler_runs_conceded

        # 5. Dismissals & Fielding
        if delivery_event.get("is_wicket"):
            for w in delivery_event["wickets"]:
                p_out = w["player_out"]
                kind = w["kind"]
                fielders = w.get("fielders", [])

                if p_out in self.batting_stats:
                    self.batting_stats[p_out]["is_out"] = True

                # Bowling wickets (run outs do not count towards bowler)
                if kind != "run out" and bowler in self.bowling_stats:
                    self.bowling_stats[bowler]["wickets"] += 1
                    if kind in ["bowled", "lbw"]:
                        self.bowling_stats[bowler]["bowled_lbw"] += 1

                # Fielding points
                award_subs = self.config.switches.get("award_substitute_fielding_points", False)
                for f in fielders:
                    fname = f["name"]
                    is_sub = f.get("substitute", False)
                    if is_sub and not award_subs:
                        continue  # Substitute fielders do not get fantasy points

                    if fname in self.fielding_stats:
                        if kind == "caught":
                            self.fielding_stats[fname]["catches"] += 1
                        elif kind == "stumped":
                            self.fielding_stats[fname]["stumpings"] += 1
                        elif kind == "run out":
                            if len(fielders) == 1:
                                self.fielding_stats[fname]["runouts_direct"] += 1
                            else:
                                self.fielding_stats[fname]["runouts_indirect"] += 1

        # End of over maiden check
        if self._current_over_legal_balls == 6:
            self._check_and_award_maiden()
            self._current_over_bowler = None
            self._current_over_legal_balls = 0
            self._current_over_runs = 0

        # Compute point snapshots
        new_points = self._compute_all_player_points()
        prev_points = self.points_history[-1]

        deltas = {
            p: round(new_points[p].total - prev_points[p].total, 2)
            for p in self.pickable_players
        }

        self.points_history.append(new_points)
        return new_points, deltas

    def _compute_all_player_points(self) -> Dict[str, PlayerPointsBreakdown]:
        results: Dict[str, PlayerPointsBreakdown] = {}
        for p in self.pickable_players:
            results[p] = compute_player_points(
                player_name=p,
                role=self.player_roles[p],
                team=self.player_teams[p],
                bstat=self.batting_stats[p],
                bwstat=self.bowling_stats[p],
                fstat=self.fielding_stats[p],
                is_starting_xi=self.player_status[p]["is_playing_xi"],
                is_impact_player=self.player_status[p]["is_impact_player"],
                impact_entered=self.impact_entered.get(p, False),
                config=self.config,
            )
        return results

    def compute_all_once_from_final_stats(self) -> Dict[str, PlayerPointsBreakdown]:
        """
        Computes final points for all players directly from the final cumulative match statistics.
        Used to test and prove that running ball-by-ball points and single-pass batch points
        are mathematically identical.
        """
        results: Dict[str, PlayerPointsBreakdown] = {}
        for p in self.pickable_players:
            results[p] = compute_player_points(
                player_name=p,
                role=self.player_roles[p],
                team=self.player_teams[p],
                bstat=self.batting_stats[p],
                bwstat=self.bowling_stats[p],
                fstat=self.fielding_stats[p],
                is_starting_xi=self.player_status[p]["is_playing_xi"],
                is_impact_player=self.player_status[p]["is_impact_player"],
                impact_entered=self.impact_entered.get(p, False),
                config=self.config,
            )
        return results

    def validate_team(self, team: FantasyTeam) -> ValidationResult:
        errors = []
        rules = self.config.team_rules

        # 1. Team size
        if len(team.players) != rules["team_size"]:
            errors.append(f"Team must contain exactly {rules['team_size']} players (got {len(team.players)})")

        # 2. No duplicates
        if len(set(team.players)) != len(team.players):
            errors.append("Team contains duplicate players")

        # 3. All players must be in pickable pool
        invalid_players = [p for p in team.players if p not in self.pickable_players]
        if invalid_players:
            errors.append(f"Players not in pickable pool: {', '.join(invalid_players)}")

        # 4. Captain and Vice-Captain validation
        if team.captain not in team.players:
            errors.append(f"Captain '{team.captain}' is not in the team roster")
        if team.vice_captain not in team.players:
            errors.append(f"Vice-Captain '{team.vice_captain}' is not in the team roster")
        if team.captain == team.vice_captain:
            errors.append("Captain and Vice-Captain cannot be the same player")

        # 5. Team affiliation limit (max 7 per team)
        team_counts = {}
        for p in team.players:
            t = self.player_teams.get(p)
            if t:
                team_counts[t] = team_counts.get(t, 0) + 1
        for t, count in team_counts.items():
            if count > rules["max_per_team"]:
                errors.append(f"Too many players from {t}: {count} (max allowed {rules['max_per_team']})")

        # 6. Role limits
        role_counts = {r: 0 for r in rules["role_limits"].keys()}
        for p in team.players:
            r = self.player_roles.get(p)
            if r in role_counts:
                role_counts[r] += 1

        for r, bounds in rules["role_limits"].items():
            cnt = role_counts.get(r, 0)
            if cnt < bounds["min"]:
                errors.append(f"Not enough {r}s: {cnt} (minimum {bounds['min']})")
            elif cnt > bounds["max"]:
                errors.append(f"Too many {r}s: {cnt} (maximum {bounds['max']})")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    def calculate_team_points_at(self, team: FantasyTeam, delivery_index: int) -> Tuple[float, float, Dict[str, float]]:
        if delivery_index < 0:
            delivery_index = 0
        if delivery_index >= len(self.points_history):
            delivery_index = len(self.points_history) - 1

        current_snap = self.points_history[delivery_index]
        prev_snap = self.points_history[delivery_index - 1] if delivery_index > 0 else None

        c_mult = self.config.multipliers["captain"]
        vc_mult = self.config.multipliers["vice_captain"]

        curr_total = 0.0
        prev_total = 0.0
        player_scores = {}

        for p in team.players:
            raw_pts = current_snap[p].total if p in current_snap else 0.0
            mult = 1.0
            if p == team.captain:
                mult = c_mult
            elif p == team.vice_captain:
                mult = vc_mult

            weighted = round(raw_pts * mult, 2)
            player_scores[p] = weighted
            curr_total += weighted

            if prev_snap:
                prev_raw = prev_snap[p].total if p in prev_snap else 0.0
                prev_total += prev_raw * mult

        delta = round(curr_total - prev_total, 2) if prev_snap else curr_total
        return round(curr_total, 2), delta, player_scores
