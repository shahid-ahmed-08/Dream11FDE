import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_raw_match(raw_path: Path) -> Dict[str, Any]:
    with open(raw_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_squads(info: Dict[str, Any], match_id: str) -> Dict[str, Any]:
    registry = info.get("registry", {}).get("people", {})

    # Roles strictly one of: 'Wicketkeeper', 'Batter', 'All-Rounder', 'Bowler'
    # Impact players and substitute fielders clearly marked.
    player_meta = {
        # Gujarat Titans
        "WP Saha": {
            "full_name": "Wriddhiman Saha",
            "team": "Gujarat Titans",
            "role": "Wicketkeeper",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Starting primary wicketkeeper, kept 20 overs",
        },
        "Shubman Gill": {
            "full_name": "Shubman Gill",
            "team": "Gujarat Titans",
            "role": "Batter",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Opening specialist batter",
        },
        "B Sai Sudharsan": {
            "full_name": "Bharath Sai Sudharsan",
            "team": "Gujarat Titans",
            "role": "Batter",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Top-order batter; replaced by Impact Player J Little for 2nd innings",
        },
        "A Manohar": {
            "full_name": "Abhinav Manohar",
            "team": "Gujarat Titans",
            "role": "Batter",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Middle-order specialist batter",
        },
        "V Shankar": {
            "full_name": "Vijay Shankar",
            "team": "Gujarat Titans",
            "role": "All-Rounder",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Fast-medium batting all-rounder (batted 5, 63* off 24; did not bowl)",
        },
        "DA Miller": {
            "full_name": "David Miller",
            "team": "Gujarat Titans",
            "role": "Batter",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Middle-order specialist batter/finisher",
        },
        "R Tewatia": {
            "full_name": "Rahul Tewatia",
            "team": "Gujarat Titans",
            "role": "All-Rounder",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Leg-spin bowling all-rounder / finisher",
        },
        "Rashid Khan": {
            "full_name": "Rashid Khan Arman",
            "team": "Gujarat Titans",
            "role": "All-Rounder",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Captain, leg-spin all-rounder (4 overs, 3/37 hat-trick)",
        },
        "AS Joseph": {
            "full_name": "Alzarri Shaheim Joseph",
            "team": "Gujarat Titans",
            "role": "Bowler",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Specialist fast bowler (bowled 4 overs)",
        },
        "Mohammed Shami": {
            "full_name": "Mohammed Shami Ahmed",
            "team": "Gujarat Titans",
            "role": "Bowler",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Specialist fast bowler (bowled 4 overs)",
        },
        "Yash Dayal": {
            "full_name": "Yash Dayal",
            "team": "Gujarat Titans",
            "role": "Bowler",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Specialist fast-medium bowler (bowled 4 overs)",
        },
        "J Little": {
            "full_name": "Joshua Brian Little",
            "team": "Gujarat Titans",
            "role": "Bowler",
            "is_playing_xi": False,
            "is_impact_player": True,
            "is_substitute": False,
            "notes": "Impact Player (substituted for B Sai Sudharsan in Innings 2; bowled 4 overs)",
        },
        "KS Bharat": {
            "full_name": "Kona Srikar Bharat",
            "team": "Gujarat Titans",
            "role": "Wicketkeeper",
            "is_playing_xi": False,
            "is_impact_player": False,
            "is_substitute": True,
            "notes": "Substitute wicketkeeper/fielder (took catch of Andre Russell on 16.1)",
        },
        "J Yadav": {
            "full_name": "Jayant Yadav",
            "team": "Gujarat Titans",
            "role": "All-Rounder",
            "is_playing_xi": False,
            "is_impact_player": False,
            "is_substitute": True,
            "notes": "Substitute fielder (took catch of Sunil Narine on 16.2)",
        },
        # Kolkata Knight Riders
        "Rahmanullah Gurbaz": {
            "full_name": "Rahmanullah Gurbaz",
            "team": "Kolkata Knight Riders",
            "role": "Wicketkeeper",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Starting primary wicketkeeper, kept 20 overs",
        },
        "N Jagadeesan": {
            "full_name": "Narayan Jagadeesan",
            "team": "Kolkata Knight Riders",
            "role": "Wicketkeeper",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Wicketkeeper-batter (played as top-order batter; took catch of Saha)",
        },
        "VR Iyer": {
            "full_name": "Venkatesh Iyer",
            "team": "Kolkata Knight Riders",
            "role": "All-Rounder",
            "is_playing_xi": False,
            "is_impact_player": True,
            "is_substitute": False,
            "notes": "Impact Player (All-rounder; subbed in for Suyash Sharma in Innings 2; scored 83 off 40; did not bowl)",
        },
        "N Rana": {
            "full_name": "Nitish Rana",
            "team": "Kolkata Knight Riders",
            "role": "Batter",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Captain, middle-order specialist batter (did not bowl)",
        },
        "RK Singh": {
            "full_name": "Rinku Singh",
            "team": "Kolkata Knight Riders",
            "role": "Batter",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Middle-order specialist batter/finisher (48* off 21)",
        },
        "AD Russell": {
            "full_name": "Andre Dwayne Russell",
            "team": "Kolkata Knight Riders",
            "role": "All-Rounder",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Fast bowling all-rounder (batted 6; did not bowl in this match)",
        },
        "SP Narine": {
            "full_name": "Sunil Philip Narine",
            "team": "Kolkata Knight Riders",
            "role": "All-Rounder",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Spin bowling all-rounder (bowled 4 overs, 3/33, batted 7)",
        },
        "SN Thakur": {
            "full_name": "Shardul Narendra Thakur",
            "team": "Kolkata Knight Riders",
            "role": "All-Rounder",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Fast bowling all-rounder (bowled 3 overs, batted 8)",
        },
        "UT Yadav": {
            "full_name": "Umesh Kumar Yadav",
            "team": "Kolkata Knight Riders",
            "role": "Bowler",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Specialist fast bowler (bowled 4 overs, batted 9)",
        },
        "LH Ferguson": {
            "full_name": "Lachlan Hammond Ferguson",
            "team": "Kolkata Knight Riders",
            "role": "Bowler",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Specialist fast bowler (bowled 2 overs)",
        },
        "CV Varun": {
            "full_name": "Varun Chakravarthy",
            "team": "Kolkata Knight Riders",
            "role": "Bowler",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Specialist mystery spinner (bowled 3 overs)",
        },
        "Suyash Sharma": {
            "full_name": "Suyash Sharma",
            "team": "Kolkata Knight Riders",
            "role": "Bowler",
            "is_playing_xi": True,
            "is_impact_player": False,
            "is_substitute": False,
            "notes": "Specialist leg-spinner (bowled 4 overs, 1/35; replaced by Impact Player VR Iyer)",
        },
        "AS Roy": {
            "full_name": "Anukul Sudhakar Roy",
            "team": "Kolkata Knight Riders",
            "role": "All-Rounder",
            "is_playing_xi": False,
            "is_impact_player": False,
            "is_substitute": True,
            "notes": "Substitute fielder (took catch of Sai Sudharsan on 17.3)",
        },
    }

    gt_players = []
    kkr_players = []

    for name, pdata in player_meta.items():
        entry = {
            "name": name,
            "full_name": pdata["full_name"],
            "cricsheet_id": registry.get(name, ""),
            "team": pdata["team"],
            "role": pdata["role"],
            "is_playing_xi": pdata["is_playing_xi"],
            "is_impact_player": pdata["is_impact_player"],
            "is_substitute": pdata["is_substitute"],
            "notes": pdata["notes"],
        }
        if pdata["team"] == "Gujarat Titans":
            gt_players.append(entry)
        else:
            kkr_players.append(entry)

    return {
        "match_id": match_id,
        "teams": {
            "Gujarat Titans": {
                "name": "Gujarat Titans",
                "short_name": "GT",
                "captain": "Rashid Khan",
                "wicketkeeper": "WP Saha",
                "players": gt_players,
            },
            "Kolkata Knight Riders": {
                "name": "Kolkata Knight Riders",
                "short_name": "KKR",
                "captain": "N Rana",
                "wicketkeeper": "Rahmanullah Gurbaz",
                "players": kkr_players,
            },
        },
    }


def normalize_events(match: Dict[str, Any], match_id: str) -> List[Dict[str, Any]]:
    innings_list = match["innings"]
    all_events: List[Dict[str, Any]] = []

    target_innings2: Optional[int] = None
    target_score: Optional[int] = None

    for inn_idx, inn in enumerate(innings_list, start=1):
        team_batting = inn["team"]
        team_bowling = (
            match["info"]["teams"][1]
            if team_batting == match["info"]["teams"][0]
            else match["info"]["teams"][0]
        )

        running_score = 0
        running_wickets = 0
        total_legal_balls = 0
        delivery_in_innings = 0

        for over_data in inn["overs"]:
            over_index = over_data["over"]  # 0-indexed (e.g. 0 to 19)
            over_number = over_index + 1    # 1-indexed (1 to 20)
            ball_counter = 0

            for deliv in over_data["deliveries"]:
                delivery_in_innings += 1
                ball_counter += 1

                extras_dict = deliv.get("extras", {})
                wides = extras_dict.get("wides", 0)
                noballs = extras_dict.get("noballs", 0)
                byes = extras_dict.get("byes", 0)
                legbyes = extras_dict.get("legbyes", 0)
                penalty = extras_dict.get("penalty", 0)

                runs_batter = deliv["runs"]["batter"]
                runs_extras = deliv["runs"]["extras"]
                runs_total = deliv["runs"]["total"]

                is_legal_ball = (wides == 0 and noballs == 0)
                if is_legal_ball:
                    total_legal_balls += 1

                running_score += runs_total

                wickets_list = []
                if "wickets" in deliv:
                    for w in deliv["wickets"]:
                        running_wickets += 1
                        fielders = []
                        for f in w.get("fielders", []):
                            fielders.append({
                                "name": f.get("name", ""),
                                "substitute": f.get("substitute", False),
                            })
                        wickets_list.append({
                            "player_out": w.get("player_out", ""),
                            "kind": w.get("kind", ""),
                            "fielders": fielders,
                        })

                # Overs completed calculation for CRR
                completed_overs = total_legal_balls // 6
                remaining_balls_in_over = total_legal_balls % 6
                overs_completed_str = f"{completed_overs}.{remaining_balls_in_over}"

                crr = round(
                    (running_score / (total_legal_balls / 6.0)) if total_legal_balls > 0 else 0.0,
                    2,
                )

                runs_needed = None
                balls_remaining = None
                rrr = None

                if inn_idx == 2 and target_score is not None:
                    runs_needed = max(0, target_score - running_score)
                    balls_remaining = max(0, 120 - total_legal_balls)
                    if balls_remaining > 0:
                        rrr = round((runs_needed / (balls_remaining / 6.0)), 2)
                    else:
                        rrr = 0.0 if runs_needed == 0 else 99.99

                event = {
                    "event_id": f"inn{inn_idx}_d{delivery_in_innings}",
                    "match_id": match_id,
                    "innings": inn_idx,
                    "batting_team": team_batting,
                    "bowling_team": team_bowling,
                    "over_number": over_number,
                    "over_index": over_index,
                    "ball_in_over": ball_counter,
                    "ball_display": f"{over_index}.{ball_counter}",
                    "delivery_in_innings": delivery_in_innings,
                    "is_legal_delivery": is_legal_ball,
                    "batter": deliv["batter"],
                    "non_striker": deliv["non_striker"],
                    "bowler": deliv["bowler"],
                    "runs_batter": runs_batter,
                    "runs_extras": runs_extras,
                    "runs_total": runs_total,
                    "extras": {
                        "wides": wides,
                        "noballs": noballs,
                        "byes": byes,
                        "legbyes": legbyes,
                        "penalty": penalty,
                    },
                    "is_wicket": len(wickets_list) > 0,
                    "wickets": wickets_list,
                    "situation": {
                        "score": running_score,
                        "wickets": running_wickets,
                        "legal_balls_bowled": total_legal_balls,
                        "overs_completed": overs_completed_str,
                        "target": target_score if inn_idx == 2 else None,
                        "runs_needed": runs_needed,
                        "balls_remaining": balls_remaining,
                        "current_run_rate": crr,
                        "required_run_rate": rrr,
                    },
                }
                all_events.append(event)

        if inn_idx == 1:
            target_innings2 = running_score
            target_score = running_score + 1  # 204 + 1 = 205

    return all_events


def run_pipeline(match_id: str = "1359487"):
    raw_path = Path(f"data/raw/{match_id}.json")
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw file {raw_path} not found.")

    match_data = load_raw_match(raw_path)
    squads = build_squads(match_data["info"], match_id)
    events = normalize_events(match_data, match_id)

    norm_dir = Path("data/normalized")
    norm_dir.mkdir(parents=True, exist_ok=True)

    squads_path = norm_dir / f"{match_id}_squads.json"
    with open(squads_path, "w", encoding="utf-8") as f:
        json.dump(squads, f, indent=2)

    events_path = norm_dir / f"{match_id}_events.json"
    with open(events_path, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)

    print(f"Normalized {len(events)} events written to {events_path}")
    print(f"Squad metadata written to {squads_path}")


if __name__ == "__main__":
    run_pipeline("1359487")
