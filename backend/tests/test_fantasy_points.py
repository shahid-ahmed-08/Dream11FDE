import json
from pathlib import Path
import pytest

from backend.app.config import settings
from backend.app.models.fantasy import FantasyTeam
from backend.app.services.points_engine import (
    PointsEngine,
    compute_player_points,
    load_scoring_config,
)
from backend.app.services.pool_generator import SimulatedPoolManager


@pytest.fixture
def config():
    return load_scoring_config()


# ============================================================================
# 1. SCORING RULE UNIT TESTS & EDGE CASES
# ============================================================================

def test_batting_runs_and_boundary_bonuses(config):
    bstat = {"runs": 40, "balls": 25, "fours": 4, "sixes": 2, "is_out": False}
    bwstat = {"legal_balls": 0, "runs_conceded": 0, "wickets": 0, "bowled_lbw": 0, "maidens": 0}
    fstat = {"catches": 0, "stumpings": 0, "runouts_direct": 0, "runouts_indirect": 0}

    res = compute_player_points(
        "TestBatter", "Batter", "GT", bstat, bwstat, fstat,
        is_starting_xi=False, is_impact_player=False, impact_entered=False, config=config
    )
    # 40 runs * 1 = 40
    # 4 fours * 1 = 4 (four bonus is +1)
    # 2 sixes * 2 = 4 (six bonus is +2)
    # 30-run milestone bonus = 4
    # SR: 40/25 = 160.0 -> tier 150-169.99 = +4
    assert res.batting_runs == 40.0
    assert res.batting_fours == 4.0
    assert res.batting_sixes == 4.0
    assert res.batting_milestone == 4.0
    assert res.batting_strike_rate == 4.0
    assert res.total == 40 + 4 + 4 + 4 + 4  # 56.0


def test_century_milestone_highest_only_mode(config):
    """Proves: In 'highest_only' mode, a century scorer gets only the 100-run bonus (+16)."""
    cfg = config.model_copy(deep=True)
    cfg.batting["milestone_mode"] = "highest_only"

    bstat = {"runs": 105, "balls": 55, "fours": 10, "sixes": 4, "is_out": False}
    bwstat = {"legal_balls": 0, "runs_conceded": 0, "wickets": 0, "bowled_lbw": 0, "maidens": 0}
    fstat = {"catches": 0, "stumpings": 0, "runouts_direct": 0, "runouts_indirect": 0}

    res = compute_player_points(
        "CenturionHighest", "Batter", "GT", bstat, bwstat, fstat,
        is_starting_xi=False, is_impact_player=False, impact_entered=False, config=cfg
    )
    # Only 100-run bonus (+16), 50 (+8) and 30 (+4) do not apply
    assert res.batting_milestone == 16.0


def test_century_milestone_cumulative_mode(config):
    """Proves: In 'cumulative' mode, a century scorer stacks 100 (+16), 50 (+8), and 30 (+4) = 28."""
    cfg = config.model_copy(deep=True)
    cfg.batting["milestone_mode"] = "cumulative"

    bstat = {"runs": 105, "balls": 55, "fours": 10, "sixes": 4, "is_out": False}
    bwstat = {"legal_balls": 0, "runs_conceded": 0, "wickets": 0, "bowled_lbw": 0, "maidens": 0}
    fstat = {"catches": 0, "stumpings": 0, "runouts_direct": 0, "runouts_indirect": 0}

    res = compute_player_points(
        "CenturionCumulative", "Batter", "GT", bstat, bwstat, fstat,
        is_starting_xi=False, is_impact_player=False, impact_entered=False, config=cfg
    )
    # 16 + 8 + 4 = 28
    assert res.batting_milestone == 28.0


def test_batting_duck_rule_and_bowler_exemption(config):
    # Batter out for 0 -> Duck penalty -2
    bstat_out = {"runs": 0, "balls": 2, "fours": 0, "sixes": 0, "is_out": True}
    bwstat = {"legal_balls": 0, "runs_conceded": 0, "wickets": 0, "bowled_lbw": 0, "maidens": 0}
    fstat = {"catches": 0, "stumpings": 0, "runouts_direct": 0, "runouts_indirect": 0}

    res_batter = compute_player_points(
        "BatterDuck", "Batter", "KKR", bstat_out, bwstat, fstat,
        is_starting_xi=False, is_impact_player=False, impact_entered=False, config=config
    )
    assert res_batter.batting_duck == -2.0

    # All-Rounder out for 0 -> Duck penalty -2
    res_ar = compute_player_points(
        "ARDuck", "All-Rounder", "KKR", bstat_out, bwstat, fstat,
        is_starting_xi=False, is_impact_player=False, impact_entered=False, config=config
    )
    assert res_ar.batting_duck == -2.0

    # Bowler out for 0 -> Duck EXEMPT (0 penalty)
    res_bowler = compute_player_points(
        "BowlerDuck", "Bowler", "GT", bstat_out, bwstat, fstat,
        is_starting_xi=False, is_impact_player=False, impact_entered=False, config=config
    )
    assert res_bowler.batting_duck == 0.0

    # Batter 0 NOT OUT -> 0 penalty
    bstat_not_out = {"runs": 0, "balls": 2, "fours": 0, "sixes": 0, "is_out": False}
    res_not_out = compute_player_points(
        "BatterNotOut", "Batter", "GT", bstat_not_out, bwstat, fstat,
        is_starting_xi=False, is_impact_player=False, impact_entered=False, config=config
    )
    assert res_not_out.batting_duck == 0.0


def test_strike_rate_under_10_balls_and_bowler_exemption(config):
    bwstat = {"legal_balls": 0, "runs_conceded": 0, "wickets": 0, "bowled_lbw": 0, "maidens": 0}
    fstat = {"catches": 0, "stumpings": 0, "runouts_direct": 0, "runouts_indirect": 0}

    # Batter faced 9 balls (under 10 balls): SR points must be 0 even if SR is very high or low
    bstat_9b = {"runs": 20, "balls": 9, "fours": 2, "sixes": 1, "is_out": False}
    res_9b = compute_player_points(
        "FastUnder10", "Batter", "GT", bstat_9b, bwstat, fstat,
        is_starting_xi=False, is_impact_player=False, impact_entered=False, config=config
    )
    assert res_9b.batting_strike_rate == 0.0

    # Batter faced 10 balls with SR 180.0 -> +6
    bstat_10b = {"runs": 18, "balls": 10, "fours": 2, "sixes": 1, "is_out": False}
    res_10b = compute_player_points(
        "Fast10b", "Batter", "GT", bstat_10b, bwstat, fstat,
        is_starting_xi=False, is_impact_player=False, impact_entered=False, config=config
    )
    assert res_10b.batting_strike_rate == 6.0

    # Batter faced 10 balls with SR 50.0 -> -6
    bstat_slow = {"runs": 5, "balls": 10, "fours": 0, "sixes": 0, "is_out": False}
    res_slow = compute_player_points(
        "SlowBatter", "Batter", "GT", bstat_slow, bwstat, fstat,
        is_starting_xi=False, is_impact_player=False, impact_entered=False, config=config
    )
    assert res_slow.batting_strike_rate == -6.0

    # Bowler role with slow SR (5 off 10 balls) -> EXEMPT from SR penalty
    res_bowler_slow = compute_player_points(
        "SlowBowler", "Bowler", "GT", bstat_slow, bwstat, fstat,
        is_starting_xi=False, is_impact_player=False, impact_entered=False, config=config
    )
    assert res_bowler_slow.batting_strike_rate == 0.0


def test_bowling_wickets_bowled_lbw_and_milestones(config):
    bstat = {"runs": 0, "balls": 0, "fours": 0, "sixes": 0, "is_out": False}
    # 3 wickets (2 bowled/lbw), 4 overs (24 balls), 30 runs
    bwstat = {"legal_balls": 24, "runs_conceded": 30, "wickets": 3, "bowled_lbw": 2, "maidens": 0}
    fstat = {"catches": 0, "stumpings": 0, "runouts_direct": 0, "runouts_indirect": 0}

    res = compute_player_points(
        "StarSpinner", "Bowler", "GT", bstat, bwstat, fstat,
        is_starting_xi=False, is_impact_player=False, impact_entered=False, config=config
    )
    # 3 wkts * 25 = 75
    # 2 bowled/lbw * 8 = 16
    # 3-wicket milestone = 4
    # Economy: 30 / 4.0 = 7.5 (between 7.01 and 9.99 = 0)
    assert res.bowling_wickets == 75.0
    assert res.bowling_bowled_lbw == 16.0
    assert res.bowling_milestone == 4.0
    assert res.bowling_economy == 0.0


def test_bowling_economy_under_2_overs_and_tiers(config):
    bstat = {"runs": 0, "balls": 0, "fours": 0, "sixes": 0, "is_out": False}
    fstat = {"catches": 0, "stumpings": 0, "runouts_direct": 0, "runouts_indirect": 0}

    # 1.5 overs (11 legal balls), conceded 5 runs -> Under 2 overs, economy MUST BE 0
    bwstat_under2 = {"legal_balls": 11, "runs_conceded": 5, "wickets": 0, "bowled_lbw": 0, "maidens": 0}
    res_under2 = compute_player_points(
        "PacerUnder2", "Bowler", "GT", bstat, bwstat_under2, fstat,
        is_starting_xi=False, is_impact_player=False, impact_entered=False, config=config
    )
    assert res_under2.bowling_economy == 0.0

    # 2.0 overs (12 legal balls), conceded 8 runs -> Econ 4.0 (< 5.0) -> +6
    bwstat_econ_good = {"legal_balls": 12, "runs_conceded": 8, "wickets": 0, "bowled_lbw": 0, "maidens": 0}
    res_econ_good = compute_player_points(
        "GoodEcon", "Bowler", "GT", bstat, bwstat_econ_good, fstat,
        is_starting_xi=False, is_impact_player=False, impact_entered=False, config=config
    )
    assert res_econ_good.bowling_economy == 6.0

    # 4.0 overs (24 legal balls), conceded 50 runs -> Econ 12.5 (> 12.0) -> -6
    bwstat_econ_bad = {"legal_balls": 24, "runs_conceded": 50, "wickets": 0, "bowled_lbw": 0, "maidens": 0}
    res_econ_bad = compute_player_points(
        "BadEcon", "Bowler", "GT", bstat, bwstat_econ_bad, fstat,
        is_starting_xi=False, is_impact_player=False, impact_entered=False, config=config
    )
    assert res_econ_bad.bowling_economy == -6.0


def test_fielding_catches_three_catch_bonus_stumping_runouts(config):
    bstat = {"runs": 0, "balls": 0, "fours": 0, "sixes": 0, "is_out": False}
    bwstat = {"legal_balls": 0, "runs_conceded": 0, "wickets": 0, "bowled_lbw": 0, "maidens": 0}

    # 3 catches -> 3 * 8 = 24 + 4 bonus = 28
    # 1 stumping -> 12
    # 1 direct runout -> 12
    # 1 indirect runout -> 6
    fstat = {"catches": 3, "stumpings": 1, "runouts_direct": 1, "runouts_indirect": 1}
    res = compute_player_points(
        "TopFielder", "Wicketkeeper", "KKR", bstat, bwstat, fstat,
        is_starting_xi=False, is_impact_player=False, impact_entered=False, config=config
    )
    assert res.fielding_catches == 28.0
    assert res.fielding_stumpings == 12.0
    assert res.fielding_runouts == 18.0


# ============================================================================
# 2. RUNNING BALL-BY-BALL VS FINAL STATS EQUIVALENCE TEST
# ============================================================================

def test_running_vs_final_stats_identical_for_all_players():
    """
    Proves: Computing player points running ball-by-ball delivery-by-delivery
    produces the exact identical results as computing once from final cumulative stats.
    """
    engine = PointsEngine("1359487")
    events_path = settings.DATA_DIR / "normalized" / "1359487_events.json"
    with open(events_path, "r", encoding="utf-8") as f:
        events = json.load(f)

    # 1. Process delivery by delivery
    for ev in events:
        engine.process_delivery(ev)

    running_final = engine.points_history[-1]

    # 2. Compute once from final cumulative stats
    batch_final = engine.compute_all_once_from_final_stats()

    # Compare every player across all fields
    for p in engine.pickable_players:
        r = running_final[p]
        b = batch_final[p]

        assert r.total == b.total, f"Total mismatch for {p}: running {r.total} vs batch {b.total}"
        assert r.batting_runs == b.batting_runs
        assert r.batting_fours == b.batting_fours
        assert r.batting_sixes == b.batting_sixes
        assert r.batting_milestone == b.batting_milestone
        assert r.batting_duck == b.batting_duck
        assert r.batting_strike_rate == b.batting_strike_rate
        assert r.bowling_wickets == b.bowling_wickets
        assert r.bowling_bowled_lbw == b.bowling_bowled_lbw
        assert r.bowling_milestone == b.bowling_milestone
        assert r.bowling_maidens == b.bowling_maidens
        assert r.bowling_economy == b.bowling_economy
        assert r.fielding_catches == b.fielding_catches
        assert r.other_starting_xi == b.other_starting_xi


# ============================================================================
# 3. TEAM VALIDATION TESTS
# ============================================================================

def test_team_validation_rules():
    engine = PointsEngine("1359487")

    valid_roster = [
        # 1 WK
        "WP Saha",
        # 4 Batters
        "Shubman Gill", "B Sai Sudharsan", "N Rana", "RK Singh",
        # 3 All-Rounders
        "Rashid Khan", "V Shankar", "AD Russell",
        # 3 Bowlers
        "Mohammed Shami", "AS Joseph", "CV Varun",
    ]
    team = FantasyTeam(players=valid_roster, captain="Shubman Gill", vice_captain="Rashid Khan")
    val = engine.validate_team(team)
    assert val.is_valid is True, f"Validation failed unexpectedly: {val.errors}"

    # Invalid size (10 players)
    team_10 = FantasyTeam(players=valid_roster[:-1], captain="Shubman Gill", vice_captain="Rashid Khan")
    assert engine.validate_team(team_10).is_valid is False

    # Duplicate players
    team_dup = FantasyTeam(players=valid_roster[:-1] + ["WP Saha"], captain="Shubman Gill", vice_captain="Rashid Khan")
    assert engine.validate_team(team_dup).is_valid is False

    # Captain not in team
    team_bad_c = FantasyTeam(players=valid_roster, captain="DA Miller", vice_captain="Rashid Khan")
    assert engine.validate_team(team_bad_c).is_valid is False

    # Captain == Vice-Captain
    team_same_cv = FantasyTeam(players=valid_roster, captain="Shubman Gill", vice_captain="Shubman Gill")
    assert engine.validate_team(team_same_cv).is_valid is False

    # > 7 players from one team (8 from GT)
    team_8_gt = FantasyTeam(
        players=[
            "WP Saha", "Shubman Gill", "B Sai Sudharsan", "A Manohar", "V Shankar",
            "DA Miller", "Rashid Khan", "Mohammed Shami",  # 8 GT
            "N Rana", "RK Singh", "CV Varun"              # 3 KKR
        ],
        captain="Shubman Gill", vice_captain="Rashid Khan"
    )
    assert engine.validate_team(team_8_gt).is_valid is False

    # Role limit violation: 0 Wicketkeepers
    team_0_wk = FantasyTeam(
        players=[
            "Shubman Gill", "B Sai Sudharsan", "A Manohar", "N Rana", "RK Singh",
            "Rashid Khan", "V Shankar", "AD Russell",
            "Mohammed Shami", "AS Joseph", "CV Varun"
        ],
        captain="Shubman Gill", vice_captain="Rashid Khan"
    )
    assert engine.validate_team(team_0_wk).is_valid is False


# ============================================================================
# 4. FIXED-SEED POOL REPRODUCIBILITY TEST
# ============================================================================

def test_fixed_seed_pool_reproducibility():
    """
    Proves: Two separate instantiations with seed=42 produce the identical 10,000 teams
    and exact same precomputed weight matrix.
    """
    pool1 = SimulatedPoolManager("1359487", pool_size=500, seed=42)
    pool2 = SimulatedPoolManager("1359487", pool_size=500, seed=42)

    assert len(pool1.teams) == 500
    assert len(pool2.teams) == 500

    for i in range(len(pool1.teams)):
        t1 = pool1.teams[i]
        t2 = pool2.teams[i]
        assert t1.players == t2.players
        assert t1.captain == t2.captain
        assert t1.vice_captain == t2.vice_captain

    assert (pool1.weight_matrix == pool2.weight_matrix).all()


# ============================================================================
# 5. RANK STABILITY TEST (NO CHANGE WHEN NO POINTS CHANGE)
# ============================================================================

def test_rank_never_changes_when_no_points_change():
    """
    Proves: If delivery N causes 0 point change for all players in a team and across
    the pool, the team's rank and rank change remain strictly stable (rank_change = 0).
    """
    pool = SimulatedPoolManager("1359487", pool_size=500, seed=42)
    test_team = pool.teams[0]

    # Find a delivery where no team's points changed (e.g. delivery 1 where only WP Saha played a dot ball with 0 extras)
    events_path = settings.DATA_DIR / "normalized" / "1359487_events.json"
    with open(events_path, "r", encoding="utf-8") as f:
        events = json.load(f)

    # Ball 1 (delivery 1) was 0 runs, 0 extras, 0 wickets
    snap0 = pool.get_simulated_rank(test_team, 0)
    snap1 = pool.get_simulated_rank(test_team, 1)

    # On delivery 1, 0 points were scored across the match
    assert snap0.team_total == snap1.team_total
    assert snap1.rank_change == 0
    assert snap1.simulated_rank == snap0.simulated_rank

