import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

from backend.app.models.key_moment import AffectedPlayerInfo, FactsPacket, KeyMomentResult


def _load_km_config() -> Dict[str, Any]:
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "config" / "key_moments.json"
    with open(p) as f:
        return json.load(f)


def is_key_moment(
    delivery_event: Dict[str, Any],
    team_delta: float,
    fan_team_players: List[str],
    captain: str,
    vice_captain: str,
    prev_player_totals: Dict[str, float],
    curr_player_totals: Dict[str, float],
    bowler_wickets_before: Dict[str, int],
    bowler_wickets_after: Dict[str, int],
    batter_runs_before: Dict[str, int],
    batter_runs_after: Dict[str, int],
    km_config: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str]]:
    if km_config is None:
        km_config = _load_km_config()

    reasons = []
    cfg = km_config
    min_delta = cfg.get("min_points_delta", 5.0)
    hattrick_ids = set(cfg.get("hattrick_deliveries", []))
    milestone_runs = cfg.get("milestone_runs", [30, 50, 100])
    milestone_wickets = cfg.get("milestone_wickets", [3, 4, 5])

    # 1. Wicket involving a fan player
    if cfg.get("always_include_wickets", True) and delivery_event.get("is_wicket"):
        for w in delivery_event.get("wickets", []):
            player_out = w["player_out"]
            bowler = delivery_event["bowler"]
            if player_out in fan_team_players or bowler in fan_team_players:
                reasons.append(f"wicket: {player_out} dismissed")

    # 2. Six by a fan player
    striker = delivery_event["batter"]
    if cfg.get("always_include_boundary_six", True) and delivery_event["runs_batter"] == 6:
        if striker in fan_team_players:
            reasons.append(f"six by {striker}")

    # 3. Hat-trick delivery
    if delivery_event["event_id"] in hattrick_ids:
        reasons.append("hat-trick delivery")

    # 4. Batting milestone reached by fan player
    for p in fan_team_players:
        rb = batter_runs_before.get(p, 0)
        ra = batter_runs_after.get(p, 0)
        for ms in milestone_runs:
            if rb < ms <= ra:
                reasons.append(f"batting milestone: {p} reached {ms} runs")

    # 5. Bowling milestone reached by fan player
    for p in fan_team_players:
        wb = bowler_wickets_before.get(p, 0)
        wa = bowler_wickets_after.get(p, 0)
        for ms in milestone_wickets:
            if wb < ms <= wa:
                reasons.append(f"bowling milestone: {p} reached {ms} wickets")

    # 6. Captain or VC directly involved (batting boundary or wicket)
    if cfg.get("always_include_captain_vc", True):
        bowler = delivery_event["bowler"]
        cap_min_runs = cfg.get("captain_vc_min_runs", 4)
        if striker in (captain, vice_captain) and delivery_event["runs_batter"] >= cap_min_runs:
            reasons.append(f"captain/vc boundary: {striker}")
        if bowler in (captain, vice_captain) and delivery_event.get("is_wicket"):
            reasons.append(f"captain/vc wicket: {bowler}")

    # 7. Meaningful delta threshold
    if abs(team_delta) >= min_delta:
        reasons.append(f"points delta {team_delta:+.1f}")

    return len(reasons) > 0, list(dict.fromkeys(reasons))  # dedup, preserve order


def build_upcoming_thresholds(
    fan_team_players: List[str],
    curr_batter_runs: Dict[str, int],
    curr_bowler_wickets: Dict[str, int],
    milestone_runs: List[int],
    milestone_wickets: List[int],
    delivery_event: Optional[Dict[str, Any]] = None,
    player_teams: Optional[Dict[str, str]] = None,
    player_roles: Optional[Dict[str, str]] = None,
    batting_stats: Optional[Dict[str, Any]] = None,
    bowling_stats: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Watch-next lines must ONLY refer to fan players who are still active at this moment
    (still batting or yet to bat in this innings, or still eligible to bowl in this innings).
    Dismissed players, players whose batting innings is finished, or bowlers who finished
    their 4-over quota are strictly excluded.
    Falls back to match situation if no player thresholds are active.
    """
    thresholds = []
    batting_team = delivery_event.get("batting_team", "") if delivery_event else ""
    bowling_team = delivery_event.get("bowling_team", "") if delivery_event else ""
    current_innings = delivery_event.get("innings", 1) if delivery_event else 1

    # 1. Active Batters (only players belonging to the currently batting team and not dismissed)
    for p in fan_team_players:
        p_team = player_teams.get(p, "") if player_teams else ""
        if p_team and batting_team and p_team != batting_team:
            continue
        if batting_stats and batting_stats.get(p, {}).get("is_out", False):
            continue

        runs = int(curr_batter_runs.get(p, 0))
        for ms in sorted(milestone_runs):
            if runs < ms:
                diff = ms - runs
                thresholds.append(f"{p} needs {diff} more run{'s' if diff != 1 else ''} for {ms}-run milestone bonus")
                break

    # 2. Active Bowlers (only players belonging to the currently bowling team with overs remaining)
    for p in fan_team_players:
        p_team = player_teams.get(p, "") if player_teams else ""
        p_role = player_roles.get(p, "") if player_roles else ""
        if p_team and bowling_team and p_team != bowling_team:
            continue

        bw = bowling_stats.get(p, {}) if bowling_stats else {}
        legal_balls = bw.get("legal_balls", 0)
        # Maximum quota in T20 is 4 overs = 24 legal balls
        if legal_balls >= 24:
            continue

        # Wicketkeeper who has not bowled cannot be treated as an upcoming bowler
        if p_role == "Wicketkeeper" and legal_balls == 0:
            continue

        wkts = int(curr_bowler_wickets.get(p, 0))
        for ms in sorted(milestone_wickets):
            if wkts < ms:
                diff = ms - wkts
                thresholds.append(f"{p} needs {diff} more wicket{'s' if diff != 1 else ''} for {ms}-wicket haul bonus")
                break

    # 3. Match Situation Fallback if no active player threshold applies
    if not thresholds and delivery_event:
        sit = delivery_event.get("situation", {})
        if current_innings == 2:
            runs_needed = sit.get("runs_needed")
            balls_rem = sit.get("balls_remaining")
            wkts_down = sit.get("wickets", 0)
            wkts_in_hand = 10 - wkts_down
            if runs_needed is not None and balls_rem is not None:
                if runs_needed <= 0 or balls_rem <= 0:
                    thresholds.append(f"Match finale: {batting_team} chase reached the final ball")
                else:
                    thresholds.append(f"{batting_team} need {runs_needed} runs off {balls_rem} balls with {wkts_in_hand} wickets in hand")
            else:
                thresholds.append(f"Chase underway: {batting_team} at {sit.get('score', 0)}/{wkts_down}")
        else:
            thresholds.append(f"{batting_team} are {sit.get('score', 0)}/{sit.get('wickets', 0)} after {sit.get('overs_completed', 0)} overs in first innings")

    return thresholds[:4]


def build_facts_packet(
    delivery_index: int,
    delivery_event: Dict[str, Any],
    fan_team,  # FantasyTeam
    team_total_before: float,
    team_total_after: float,
    rank_before: int,
    rank_after: int,
    prev_snap: Dict[str, Any],
    curr_snap: Dict[str, Any],
    reasons: List[str],
    km_config: Dict[str, Any],
    player_teams: Optional[Dict[str, str]] = None,
    player_roles: Optional[Dict[str, str]] = None,
    batting_stats: Optional[Dict[str, Any]] = None,
    bowling_stats: Optional[Dict[str, Any]] = None,
) -> FactsPacket:
    milestone_runs = km_config.get("milestone_runs", [30, 50, 100])
    milestone_wickets = km_config.get("milestone_wickets", [3, 4, 5])
    c_mult = 2.0
    vc_mult = 1.5

    affected: List[AffectedPlayerInfo] = []
    for p in fan_team.players:
        prev_pts = prev_snap[p].total if p in prev_snap else 0.0
        curr_pts = curr_snap[p].total if p in curr_snap else 0.0
        raw_delta = round(curr_pts - prev_pts, 2)
        is_cap = p == fan_team.captain
        is_vc = p == fan_team.vice_captain
        mult = c_mult if is_cap else (vc_mult if is_vc else 1.0)
        if raw_delta != 0 or is_cap or is_vc:
            affected.append(AffectedPlayerInfo(
                player_name=p,
                team=curr_snap[p].team if p in curr_snap else "",
                role=curr_snap[p].role if p in curr_snap else "",
                multiplier=mult,
                is_captain=is_cap,
                is_vice_captain=is_vc,
                raw_delta=raw_delta,
                weighted_delta=round(raw_delta * mult, 2),
                current_player_total=round(curr_pts * mult, 2),
            ))

    curr_batter_runs = {p: int(curr_snap[p].batting_runs // 1) if p in curr_snap else 0 for p in fan_team.players}
    curr_bowler_wkts = {p: int(curr_snap[p].bowling_wickets // 25) if p in curr_snap else 0 for p in fan_team.players}

    thresholds = build_upcoming_thresholds(
        fan_team_players=fan_team.players,
        curr_batter_runs=curr_batter_runs,
        curr_bowler_wickets=curr_bowler_wkts,
        milestone_runs=milestone_runs,
        milestone_wickets=milestone_wickets,
        delivery_event=delivery_event,
        player_teams=player_teams,
        player_roles=player_roles,
        batting_stats=batting_stats,
        bowling_stats=bowling_stats,
    )

    sit = delivery_event["situation"]
    match_sit = (
        f"{'GT' if delivery_event['batting_team'] == 'Gujarat Titans' else 'KKR'} "
        f"{sit['score']}/{sit['wickets']} in {sit['overs_completed']} overs"
    )
    if sit.get("target"):
        match_sit += f" | Need {sit.get('runs_needed', 0)} off {sit.get('balls_remaining', 0)} balls"

    w_desc = ""
    if delivery_event.get("is_wicket"):
        w = delivery_event["wickets"][0]
        w_desc = f" | WICKET: {w['player_out']} {w['kind']}"
    desc = (
        f"Over {delivery_event['ball_display']}: {delivery_event['batter']} "
        f"vs {delivery_event['bowler']} — {delivery_event['runs_total']} run(s){w_desc}"
    )

    team_delta = round(team_total_after - team_total_before, 2)
    rank_movement = rank_before - rank_after
    points_rose_but_rank_dropped = (team_delta > 0 and rank_movement < 0)

    packet = {
        "delivery_index": delivery_index,
        "ball_display": delivery_event["ball_display"],
        "innings": delivery_event["innings"],
        "match_situation": match_sit,
        "event_description": desc,
        "is_wicket": bool(delivery_event.get("is_wicket")),
        "is_six": delivery_event["runs_batter"] == 6,
        "is_milestone": any("milestone" in r for r in reasons),
        "is_hattrick": "hat-trick" in " ".join(reasons),
        "team_total_before": team_total_before,
        "team_total_after": team_total_after,
        "team_delta": team_delta,
        "simulated_rank_before": rank_before,
        "simulated_rank_after": rank_after,
        "rank_movement": rank_movement,
        "points_rose_but_rank_dropped": points_rose_but_rank_dropped,
        "upcoming_thresholds": thresholds,
    }
    packet_hash = hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()[:16]

    return FactsPacket(
        **packet,
        affected_fan_players=affected,
        packet_hash=packet_hash,
    )
