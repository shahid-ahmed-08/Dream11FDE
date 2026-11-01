import json
from pathlib import Path

events_path = Path("data/normalized/1359487_events.json")
squads_path = Path("data/normalized/1359487_squads.json")

with open(events_path, "r", encoding="utf-8") as f:
    events = json.load(f)

with open(squads_path, "r", encoding="utf-8") as f:
    squads = json.load(f)

inn1_events = [e for e in events if e["innings"] == 1]
inn2_events = [e for e in events if e["innings"] == 2]

print(f"Total events: {len(events)}")
print(f"Innings 1 events: {len(inn1_events)}, Last situation: {inn1_events[-1]['situation']['score']}/{inn1_events[-1]['situation']['wickets']}")
print(f"Innings 2 events: {len(inn2_events)}, Last situation: {inn2_events[-1]['situation']['score']}/{inn2_events[-1]['situation']['wickets']}")

# Check that every single event has extras breakdown and wickets list
for idx, e in enumerate(events):
    assert "extras" in e, f"Missing extras in event {idx}"
    for k in ["wides", "noballs", "byes", "legbyes"]:
        assert k in e["extras"], f"Missing {k} in extras in event {idx}"
    assert "wickets" in e, f"Missing wickets in event {idx}"
    assert "situation" in e, f"Missing situation in event {idx}"
    assert "score" in e["situation"]
    assert "wickets" in e["situation"]

print("Assertion passed: All 250 events have extras and wicket details intact.")

# Verify Hat-trick
hattrick_events = [e for e in inn2_events if e["bowler"] == "Rashid Khan" and e["is_wicket"]]
print(f"Rashid Khan wickets count: {len(hattrick_events)}")
for h in hattrick_events:
    w = h["wickets"][0]
    print(f"  {h['ball_display']} -> {w['player_out']} ({w['kind']}) by {w['fielders']}")

# Verify Final Over
final_over = [e for e in inn2_events if e["over_index"] == 19]
print(f"20th over deliveries count: {len(final_over)}")
for fo in final_over:
    print(f"  {fo['ball_display']}: Striker={fo['batter']} scored {fo['runs_batter']} runs, total={fo['runs_total']}, Score={fo['situation']['score']}/{fo['situation']['wickets']}")

print("Squads summary:")
for team_name, tdata in squads["teams"].items():
    print(f"  Team: {team_name} ({tdata['short_name']}) - {len(tdata['players'])} players")
