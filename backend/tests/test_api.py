import pytest
from backend.app.main import healthcheck
from backend.app.routers.match import (
    get_match_summary,
    get_match_squads,
    get_match_events,
    get_event_by_id,
)


def test_healthcheck():
    data = healthcheck()
    assert data["status"] == "healthy"
    assert data["match_id"] == "1359487"
    assert "gemini_api_configured" in data


def test_get_match_summary():
    summary = get_match_summary()
    assert summary.match_id == "1359487"
    assert "Gujarat Titans" in summary.teams
    assert "Kolkata Knight Riders" in summary.teams
    assert summary.total_events == 250
    assert len(summary.innings_summaries) == 2

    # Innings 1 check
    inn1 = summary.innings_summaries[0]
    assert inn1["team"] == "Gujarat Titans"
    assert inn1["score"] == 204
    assert inn1["wickets"] == 4

    # Innings 2 check
    inn2 = summary.innings_summaries[1]
    assert inn2["team"] == "Kolkata Knight Riders"
    assert inn2["score"] == 207
    assert inn2["wickets"] == 7


def test_get_match_squads():
    data = get_match_squads()
    assert "Gujarat Titans" in data["teams"]
    assert "Kolkata Knight Riders" in data["teams"]

    gt_players = data["teams"]["Gujarat Titans"]["players"]
    kkr_players = data["teams"]["Kolkata Knight Riders"]["players"]

    assert len(gt_players) == 14
    assert len(kkr_players) == 13

    # Check key players and their exact roles
    rashid = next(p for p in gt_players if p["name"] == "Rashid Khan")
    assert rashid["role"] == "All-Rounder"

    shankar = next(p for p in gt_players if p["name"] == "V Shankar")
    assert shankar["role"] == "All-Rounder"

    jagadeesan = next(p for p in kkr_players if p["name"] == "N Jagadeesan")
    assert jagadeesan["role"] == "Wicketkeeper"

    vr_iyer = next(p for p in kkr_players if p["name"] == "VR Iyer")
    assert vr_iyer["role"] == "All-Rounder"

    rinku = next(p for p in kkr_players if p["name"] == "RK Singh")
    assert rinku["role"] == "Batter"


def test_get_match_events():
    events = get_match_events()
    assert len(events) == 250

    # Innings 1 filter
    inn1 = get_match_events(innings=1)
    assert len(inn1) == 127

    # Innings 2 filter
    inn2 = get_match_events(innings=2)
    assert len(inn2) == 123


def test_event_by_id():
    event = get_event_by_id("inn2_d123")
    assert event["event_id"] == "inn2_d123"
    assert event["batter"] == "RK Singh"
    assert event["runs_batter"] == 6
    assert event["situation"]["score"] == 207
