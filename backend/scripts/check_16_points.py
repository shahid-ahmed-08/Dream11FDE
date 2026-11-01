import sys
sys.path.insert(0, r"d:\Project\Dream11")
from backend.app.services.fan_session import FanSession
from backend.app.services.preset_teams import PRESET_TEAMS
from backend.app.services.replay_engine import load_match_stream_items

items = load_match_stream_items("1359487")
session = FanSession("diff", PRESET_TEAMS["differential"])

for item in items:
    if item.item_type == "delivery" and item.delivery:
        ev = item.delivery.model_dump()
        session.process_one_delivery(ev)
        if ev.get("innings") == 2 and ev.get("ball_display") in ("16.1", "16.2"):
            rk = session.engine.points_history[-1]["Rashid Khan"]
            print(f"Ball {ev['ball_display']} Rashid Khan: total={rk.total}")
            print(f"  wickets={rk.bowling_wickets}, bowled_lbw={rk.bowling_bowled_lbw}, maidens={rk.bowling_maidens}, econ={rk.bowling_economy}, milestone={rk.bowling_milestone}")
            sn = session.engine.points_history[-1]["SP Narine"]
            print(f"Ball {ev['ball_display']} SP Narine: total={sn.total}")
            print(f"  runs={sn.batting_runs}, duck={sn.batting_duck}, sr={sn.batting_strike_rate}, wkts={sn.bowling_wickets}")
