"""
Preset Fantasy Teams for GT vs KKR IPL 2023 Match 13.
All teams validated against the pickable pool and role/team rules.

Role limits: WK 1-4, Bat 3-6, AR 1-4, Bowl 3-6
Team limit: max 7 from one team
Total: exactly 11 players
"""
from backend.app.models.fantasy import FantasyTeam

PRESET_TEAMS = {
    "safe_pick": FantasyTeam(
        # Standard safe selection. C: Shubman Gill (form batter), VC: WP Saha (reliable WK-bat).
        # GT(7), KKR(4). WK=1, Bat=3, AR=4, Bowl=3
        name="Safe Pick",
        captain="Shubman Gill",
        vice_captain="WP Saha",
        players=[
            "WP Saha",          # GT  Wicketkeeper
            "Shubman Gill",     # GT  Batter
            "DA Miller",        # GT  Batter
            "V Shankar",        # GT  All-Rounder
            "Rashid Khan",      # GT  All-Rounder
            "Mohammed Shami",   # GT  Bowler
            "Yash Dayal",       # GT  Bowler
            "RK Singh",         # KKR Batter
            "SP Narine",        # KKR All-Rounder
            "SN Thakur",        # KKR All-Rounder
            "CV Varun",         # KKR Bowler
        ],
    ),
    "differential": FantasyTeam(
        # Differential pick. C: Rashid Khan (punt on his bowling haul), VC: SP Narine.
        # GT-heavy (7). WK=1, Bat=3, AR=4, Bowl=3
        name="Differential",
        captain="Rashid Khan",
        vice_captain="SP Narine",
        players=[
            "WP Saha",          # GT  Wicketkeeper
            "Shubman Gill",     # GT  Batter
            "B Sai Sudharsan",  # GT  Batter
            "R Tewatia",        # GT  All-Rounder
            "V Shankar",        # GT  All-Rounder
            "Rashid Khan",      # GT  All-Rounder
            "Mohammed Shami",   # GT  Bowler
            "RK Singh",         # KKR Batter
            "SP Narine",        # KKR All-Rounder
            "LH Ferguson",      # KKR Bowler
            "CV Varun",         # KKR Bowler
        ],
    ),
    "finisher_fan": FantasyTeam(
        # Bet on the finishers. C: AD Russell (explosive AR), VC: RK Singh (match hero).
        # KKR-heavy (7). WK=2, Bat=3, AR=3, Bowl=3
        name="Finisher Fan",
        captain="AD Russell",
        vice_captain="RK Singh",
        players=[
            "WP Saha",            # GT  Wicketkeeper
            "Shubman Gill",       # GT  Batter
            "Mohammed Shami",     # GT  Bowler
            "Yash Dayal",         # GT  Bowler
            "N Jagadeesan",       # KKR Wicketkeeper
            "RK Singh",           # KKR Batter
            "N Rana",             # KKR Batter
            "AD Russell",         # KKR All-Rounder
            "SP Narine",          # KKR All-Rounder
            "VR Iyer",            # KKR All-Rounder
            "CV Varun",           # KKR Bowler
        ],
    ),
}
