import bisect
import json
import random
from typing import Dict, List, Optional, Tuple
import numpy as np

from backend.app.config import settings
from backend.app.models.fantasy import FantasyTeam, RankSnapshot, TeamPointsSnapshot
from backend.app.services.points_engine import PointsEngine, load_scoring_config


class SimulatedPoolManager:
    def __init__(self, match_id: str = "1359487", pool_size: int = 10000, seed: int = 42):
        self.match_id = match_id
        self.pool_size = pool_size
        self.seed = seed

        self.points_engine = PointsEngine(match_id=match_id)
        self.pickable_players = self.points_engine.pickable_players
        self.player_to_idx = {p: i for i, p in enumerate(self.pickable_players)}
        self.idx_to_player = {i: p for i, p in enumerate(self.pickable_players)}

        # Generate reproducible pool
        self.teams: List[FantasyTeam] = self._generate_pool()

        # Build weight matrix (10000 x 24)
        self.weight_matrix = self._build_weight_matrix()

        # Run match events and precompute delivery matrices
        self.all_player_points_matrix = None  # (num_deliveries + 1, 24)
        self.team_scores_by_delivery = None   # (num_deliveries + 1, 10000)
        self.sorted_team_scores = None        # (num_deliveries + 1, 10000)

        self._precompute_match()

    def _generate_pool(self) -> List[FantasyTeam]:
        """
        Generates 10,000 valid fantasy teams using a fixed random seed.
        Only uses pre-match plausibility without match outcome foresight.
        """
        rng = random.Random(self.seed)
        roles = self.points_engine.player_roles
        teams_map = self.points_engine.player_teams

        # Categorize pickable players by role
        by_role = {"Wicketkeeper": [], "Batter": [], "All-Rounder": [], "Bowler": []}
        for p in self.pickable_players:
            by_role[roles[p]].append(p)

        # Pre-match popularity weighting (favouring established starters and key players)
        # Top-order batters, primary keepers, star allrounders, frontline bowlers
        player_weights = {
            # GT
            "Shubman Gill": 2.5, "WP Saha": 1.8, "B Sai Sudharsan": 1.8, "V Shankar": 1.4,
            "DA Miller": 1.5, "Rashid Khan": 2.2, "Mohammed Shami": 2.0, "AS Joseph": 1.5,
            "R Tewatia": 1.1, "A Manohar": 1.0, "Yash Dayal": 1.0, "J Little": 0.8,
            # KKR
            "Rahmanullah Gurbaz": 2.0, "N Rana": 2.0, "AD Russell": 2.3, "SP Narine": 2.0,
            "VR Iyer": 1.6, "SN Thakur": 1.5, "UT Yadav": 1.4, "CV Varun": 1.4,
            "RK Singh": 1.1, "N Jagadeesan": 1.0, "LH Ferguson": 1.2, "Suyash Sharma": 0.9,
        }

        # Captaincy pre-match weights (top order, elite all-rounders, frontline pacers/spinners)
        c_weights = {
            "Shubman Gill": 4.0, "Rashid Khan": 3.5, "AD Russell": 3.5, "SP Narine": 3.0,
            "Mohammed Shami": 2.5, "Rahmanullah Gurbaz": 2.5, "N Rana": 2.0, "B Sai Sudharsan": 2.0,
            "WP Saha": 1.5, "AS Joseph": 1.2, "VR Iyer": 1.5, "V Shankar": 1.2,
            "SN Thakur": 1.0, "DA Miller": 1.0, "UT Yadav": 1.0, "CV Varun": 1.0,
            "R Tewatia": 0.5, "A Manohar": 0.5, "RK Singh": 0.5, "N Jagadeesan": 0.5,
            "LH Ferguson": 0.6, "Yash Dayal": 0.4, "Suyash Sharma": 0.4, "J Little": 0.4,
        }

        valid_teams: List[FantasyTeam] = []
        attempts = 0
        max_attempts = 100000

        while len(valid_teams) < self.pool_size and attempts < max_attempts:
            attempts += 1
            # Sample role distribution within legal bounds:
            # Wicketkeeper 1-4, Batter 3-6, All-Rounder 1-4, Bowler 3-6, total 11
            num_wk = rng.choice([1, 2])
            num_bat = rng.choice([3, 4, 5])
            num_ar = rng.choice([1, 2, 3])
            num_bowl = 11 - (num_wk + num_bat + num_ar)

            if not (3 <= num_bowl <= 6):
                continue

            # Weighted sampling per role
            def sample_unique(pool_list, k):
                if k > len(pool_list):
                    return None
                w = [player_weights.get(p, 1.0) for p in pool_list]
                # Sample without replacement using weights
                chosen = []
                pool_copy = list(pool_list)
                w_copy = list(w)
                for _ in range(k):
                    sel = rng.choices(pool_copy, weights=w_copy, k=1)[0]
                    chosen.append(sel)
                    idx = pool_copy.index(sel)
                    pool_copy.pop(idx)
                    w_copy.pop(idx)
                return chosen

            wk_sel = sample_unique(by_role["Wicketkeeper"], num_wk)
            bat_sel = sample_unique(by_role["Batter"], num_bat)
            ar_sel = sample_unique(by_role["All-Rounder"], num_ar)
            bowl_sel = sample_unique(by_role["Bowler"], num_bowl)

            if not wk_sel or not bat_sel or not ar_sel or not bowl_sel:
                continue

            selected_11 = wk_sel + bat_sel + ar_sel + bowl_sel

            # Check team limits: at most 7 from one team
            gt_count = sum(1 for p in selected_11 if teams_map[p] == "Gujarat Titans")
            kkr_count = 11 - gt_count
            if gt_count > 7 or kkr_count > 7:
                continue

            # Sample Captain and Vice-Captain
            cap_w = [c_weights.get(p, 1.0) for p in selected_11]
            captain = rng.choices(selected_11, weights=cap_w, k=1)[0]

            vc_candidates = [p for p in selected_11 if p != captain]
            vc_w = [c_weights.get(p, 1.0) for p in vc_candidates]
            vice_captain = rng.choices(vc_candidates, weights=vc_w, k=1)[0]

            team = FantasyTeam(
                name=f"Team_{len(valid_teams)+1:05d}",
                players=selected_11,
                captain=captain,
                vice_captain=vice_captain,
            )

            validation = self.points_engine.validate_team(team)
            if validation.is_valid:
                valid_teams.append(team)

        if len(valid_teams) < self.pool_size:
            raise RuntimeError(f"Could only generate {len(valid_teams)} valid teams in {attempts} attempts.")

        return valid_teams

    def _build_weight_matrix(self) -> np.ndarray:
        """
        Builds a (10000 x 24) matrix of player multipliers:
        1.0 for normal selection, 2.0 for captain, 1.5 for vice-captain, 0.0 otherwise.
        """
        W = np.zeros((self.pool_size, len(self.pickable_players)), dtype=np.float32)
        c_mult = self.points_engine.config.multipliers["captain"]
        vc_mult = self.points_engine.config.multipliers["vice_captain"]

        for i, team in enumerate(self.teams):
            for p in team.players:
                col = self.player_to_idx[p]
                if p == team.captain:
                    W[i, col] = c_mult
                elif p == team.vice_captain:
                    W[i, col] = vc_mult
                else:
                    W[i, col] = 1.0

        return W

    def _precompute_match(self):
        """
        Feeds all normalized match events through the PointsEngine and
        precomputes team totals across all 10,000 teams for every delivery.
        """
        events_path = settings.DATA_DIR / "normalized" / f"{self.match_id}_events.json"
        with open(events_path, "r", encoding="utf-8") as f:
            events = json.load(f)

        self.points_engine.reset()
        for ev in events:
            self.points_engine.process_delivery(ev)

        # points_history has 251 snapshots (delivery 0 to 250)
        num_snaps = len(self.points_engine.points_history)
        P = np.zeros((num_snaps, len(self.pickable_players)), dtype=np.float32)

        for d_idx, snap in enumerate(self.points_engine.points_history):
            for p, idx in self.player_to_idx.items():
                P[d_idx, idx] = snap[p].total

        self.all_player_points_matrix = P

        # Team scores: (num_snaps, 10000) = (num_snaps, 24) @ (24, 10000)
        # Note: W is (10000, 24), so P @ W.T is (num_snaps, 10000)
        self.team_scores_by_delivery = np.dot(P, self.weight_matrix.T)

        # Precompute sorted scores for ultra-fast rank lookup
        self.sorted_team_scores = np.sort(self.team_scores_by_delivery, axis=1)

    def get_team_score_vector(self, team: FantasyTeam) -> np.ndarray:
        """Computes a single team's score across all 251 match deliveries."""
        w = np.zeros(len(self.pickable_players), dtype=np.float32)
        c_mult = self.points_engine.config.multipliers["captain"]
        vc_mult = self.points_engine.config.multipliers["vice_captain"]

        for p in team.players:
            col = self.player_to_idx[p]
            if p == team.captain:
                w[col] = c_mult
            elif p == team.vice_captain:
                w[col] = vc_mult
            else:
                w[col] = 1.0

        # P is (num_snaps, 24), w is (24,) -> result is (num_snaps,)
        return np.dot(self.all_player_points_matrix, w)

    def get_simulated_rank(self, team: FantasyTeam, delivery_index: int) -> RankSnapshot:
        """
        Instant simulated rank calculation:
        Finds the rank of the user's team among the 10,000 pool at delivery_index.
        Executes in < 5 microseconds.
        """
        if delivery_index < 0:
            delivery_index = 0
        if delivery_index >= len(self.sorted_team_scores):
            delivery_index = len(self.sorted_team_scores) - 1

        team_scores = self.get_team_score_vector(team)
        current_score = float(team_scores[delivery_index])

        # Standard sports competition rank: 1 + number of teams with strictly higher score
        sorted_pool = self.sorted_team_scores[delivery_index]
        # np.searchsorted with side='right' finds number of items <= current_score
        count_le = int(np.searchsorted(sorted_pool, current_score, side="right"))
        higher_count = self.pool_size - count_le
        rank = higher_count + 1

        percentile = round(((self.pool_size - rank) / self.pool_size) * 100.0, 2)

        rank_change = 0
        if delivery_index > 0:
            prev_score = float(team_scores[delivery_index - 1])
            prev_sorted = self.sorted_team_scores[delivery_index - 1]
            prev_count_le = int(np.searchsorted(prev_sorted, prev_score, side="right"))
            prev_rank = (self.pool_size - prev_count_le) + 1
            rank_change = prev_rank - rank  # positive = climbed, negative = dropped

        return RankSnapshot(
            delivery_index=delivery_index,
            team_total=round(current_score, 2),
            simulated_rank=rank,
            percentile=percentile,
            rank_change=rank_change,
            label="simulated rank among 10,000 sample teams",
        )

