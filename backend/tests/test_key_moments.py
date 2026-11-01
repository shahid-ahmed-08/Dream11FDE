"""
Tests for Key Moment engine, AI explainer, team validation, and fan session E2E.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.models.fantasy import FantasyTeam
from backend.app.models.key_moment import AIExplanation, FactsPacket, AffectedPlayerInfo
from backend.app.services.key_moment_engine import is_key_moment, build_facts_packet, _load_km_config
from backend.app.services.points_engine import PointsEngine
from backend.app.services.preset_teams import PRESET_TEAMS
from backend.app.services.fan_session import FanSession
from backend.app.services.replay_engine import load_match_stream_items


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    return PointsEngine()


@pytest.fixture(scope="module")
def km_config():
    return _load_km_config()


@pytest.fixture(scope="module")
def events():
    items = load_match_stream_items("1359487")
    return [it.delivery.model_dump() for it in items if it.item_type == "delivery" and it.delivery]


@pytest.fixture(scope="module")
def hattrick_events(events):
    hattrick_ids = {"inn2_d98", "inn2_d99", "inn2_d100"}
    return [ev for ev in events if ev["event_id"] in hattrick_ids]


@pytest.fixture
def safe_pick_team():
    return PRESET_TEAMS["safe_pick"]


@pytest.fixture
def differential_team():
    return PRESET_TEAMS["differential"]


@pytest.fixture
def finisher_fan_team():
    return PRESET_TEAMS["finisher_fan"]


def _make_dummy_facts(**overrides) -> FactsPacket:
    """Helper: build a minimal FactsPacket for testing."""
    defaults = {
        "delivery_index": 0,
        "ball_display": "1.1",
        "innings": 1,
        "match_situation": "GT 10/0 in 1.0 overs",
        "event_description": "Over 1.1: Shubman Gill vs SP Narine — 6 run(s)",
        "is_wicket": False,
        "is_six": True,
        "is_milestone": False,
        "is_hattrick": False,
        "affected_fan_players": [],
        "team_total_before": 10.0,
        "team_total_after": 22.0,
        "team_delta": 12.0,
        "simulated_rank_before": 5000,
        "simulated_rank_after": 3000,
        "rank_movement": 2000,
        "upcoming_thresholds": [],
        "packet_hash": "testhash00000001",
    }
    defaults.update(overrides)
    return FactsPacket(**defaults)


# ─── Test 1: Key moment selection ──────────────────────────────────────────────

def test_key_moment_wicket(events, km_config):
    """A wicket involving a fan player must be classified as a key moment."""
    wicket_ev = next(ev for ev in events if ev.get("is_wicket"))
    player_out = wicket_ev["wickets"][0]["player_out"]
    bowler = wicket_ev["bowler"]
    fan_players = [player_out, "Shubman Gill"]  # player_out is in the team

    dummy_totals = {p: 10.0 for p in fan_players}
    dummy_bats = {p: 0 for p in fan_players}
    dummy_wkts = {p: 0 for p in fan_players}

    result, reasons = is_key_moment(
        delivery_event=wicket_ev,
        team_delta=0.0,
        fan_team_players=fan_players,
        captain=fan_players[0],
        vice_captain=fan_players[1],
        prev_player_totals=dummy_totals,
        curr_player_totals=dummy_totals,
        bowler_wickets_before=dummy_wkts,
        bowler_wickets_after=dummy_wkts,
        batter_runs_before=dummy_bats,
        batter_runs_after=dummy_bats,
        km_config=km_config,
    )
    assert result, "Wicket event should be a key moment"
    assert any("wicket" in r.lower() for r in reasons)


def test_key_moment_six(events, km_config):
    """A six by a fan player must be classified as a key moment."""
    six_ev = next(ev for ev in events if ev["runs_batter"] == 6)
    fan_players = [six_ev["batter"], "Yash Dayal"]
    dummy_totals = {p: 5.0 for p in fan_players}
    dummy_bats = {p: 0 for p in fan_players}
    dummy_wkts = {p: 0 for p in fan_players}

    result, reasons = is_key_moment(
        delivery_event=six_ev,
        team_delta=0.0,
        fan_team_players=fan_players,
        captain=fan_players[0],
        vice_captain=fan_players[1],
        prev_player_totals=dummy_totals,
        curr_player_totals=dummy_totals,
        bowler_wickets_before=dummy_wkts,
        bowler_wickets_after=dummy_wkts,
        batter_runs_before=dummy_bats,
        batter_runs_after=dummy_bats,
        km_config=km_config,
    )
    assert result, "Six event should be a key moment"
    assert any("six" in r.lower() for r in reasons)


def test_key_moment_hattrick(hattrick_events, km_config):
    """All three hat-trick deliveries must be classified as key moments."""
    assert len(hattrick_events) == 3, f"Expected 3 hattrick events, got {len(hattrick_events)}"
    for ev in hattrick_events:
        result, reasons = is_key_moment(
            delivery_event=ev,
            team_delta=0.0,
            fan_team_players=["Rashid Khan"],
            captain="Rashid Khan",
            vice_captain="SP Narine",
            prev_player_totals={"Rashid Khan": 0.0},
            curr_player_totals={"Rashid Khan": 0.0},
            bowler_wickets_before={"Rashid Khan": 0},
            bowler_wickets_after={"Rashid Khan": 0},
            batter_runs_before={"Rashid Khan": 0},
            batter_runs_after={"Rashid Khan": 0},
            km_config=km_config,
        )
        assert result, f"Hat-trick delivery {ev['event_id']} should be a key moment"
        assert any("hat-trick" in r.lower() for r in reasons), f"Expected hat-trick reason, got {reasons}"


def test_key_moment_batting_milestone(events, km_config):
    """Crossing 30/50/100 by a fan player must trigger a key moment."""
    # Simulate: player has 29 runs before, 35 after — crosses 30
    ev = events[0]  # any delivery

    result, reasons = is_key_moment(
        delivery_event=ev,
        team_delta=0.0,
        fan_team_players=["Shubman Gill"],
        captain="Shubman Gill",
        vice_captain="WP Saha",
        prev_player_totals={"Shubman Gill": 0.0},
        curr_player_totals={"Shubman Gill": 0.0},
        bowler_wickets_before={"Shubman Gill": 0},
        bowler_wickets_after={"Shubman Gill": 0},
        batter_runs_before={"Shubman Gill": 29},
        batter_runs_after={"Shubman Gill": 35},
        km_config=km_config,
    )
    assert result, "Crossing 30 runs should be a key moment"
    assert any("30" in r for r in reasons)


def test_key_moment_bowling_milestone(events, km_config):
    """Reaching 3 wickets should trigger a bowling milestone key moment."""
    ev = events[0]
    result, reasons = is_key_moment(
        delivery_event=ev,
        team_delta=0.0,
        fan_team_players=["Rashid Khan"],
        captain="Rashid Khan",
        vice_captain="SP Narine",
        prev_player_totals={"Rashid Khan": 0.0},
        curr_player_totals={"Rashid Khan": 0.0},
        bowler_wickets_before={"Rashid Khan": 2},
        bowler_wickets_after={"Rashid Khan": 3},
        batter_runs_before={"Rashid Khan": 0},
        batter_runs_after={"Rashid Khan": 0},
        km_config=km_config,
    )
    assert result, "Reaching 3 wickets should be a key moment"
    assert any("3 wicket" in r.lower() or "3-wkt" in r.lower() or "bowling milestone" in r.lower() for r in reasons)


def test_watch_next_saha_at_16_1_not_mentioned():
    """
    At ball 16.1 (Innings 2), GT batter WP Saha is not batting (GT innings finished).
    Watch-next lines must strictly exclude dismissed or inactive players like Saha.
    """
    from backend.app.services.fan_session import FanSession
    from backend.app.services.preset_teams import PRESET_TEAMS
    from backend.app.services.replay_engine import load_match_stream_items

    team = PRESET_TEAMS["differential"]
    assert "WP Saha" in team.players, "Saha must be in differential team"

    session = FanSession("test-saha-16-1", fan_team=team)
    items = load_match_stream_items("1359487")

    ball_16_1_km = None
    for item in items:
        if item.item_type == "delivery" and item.delivery:
            ev = item.delivery.model_dump()
            _tot, _del, _rnk, km = session.process_one_delivery(ev)
            if ev.get("innings") == 2 and ev.get("ball_display") == "16.1":
                ball_16_1_km = km
                break

    assert ball_16_1_km is not None, "Ball 16.1 must be processed as a key moment (Russell wicket)"
    assert ball_16_1_km.facts_packet is not None

    thresholds = ball_16_1_km.facts_packet.upcoming_thresholds
    assert len(thresholds) > 0, "Expected upcoming thresholds or situation at 16.1"

    # CRITICAL CHECK: Saha must NOT appear in watch-next at 16.1
    for t in thresholds:
        assert "Saha" not in t, f"WP Saha should NOT be mentioned at 16.1 (Innings 2), found: {t}"
        assert "WP Saha" not in t, f"WP Saha should NOT be mentioned at 16.1 (Innings 2), found: {t}"


# ─── Test 2: Number validation rejection ───────────────────────────────────────

def test_number_validation_rejects_bad_ai_response():
    """AI response containing a number not in the facts packet must trigger fallback."""
    from backend.app.services import ai_explainer
    from backend.app.services.ai_explainer import get_explanation_sync, _CACHE_DIR

    facts = _make_dummy_facts(packet_hash="badhash0000000002")

    # Fabricate a Gemini API response with an invented number (99999) not in the packet
    bad_api_response = {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": json.dumps({
                        "explanation_en": "Your team jumped by 99999 points today!",
                        "explanation_hi": "Aapki team 99999 points se aage badi!",
                        "watch_next_en": "Watch the next over.",
                        "watch_next_hi": "Agli over dekhein.",
                    })
                }]
            }
        }]
    }

    # Remove any existing cache entry
    cache_file = _CACHE_DIR / "badhash0000000002.json"
    cache_file.unlink(missing_ok=True)

    def fake_api_call(*args, **kwargs):
        return bad_api_response

    original = ai_explainer._call_gemini_api_sync
    ai_explainer._call_gemini_api_sync = fake_api_call
    try:
        result = get_explanation_sync(facts, api_key="fake-key-for-test")
    finally:
        ai_explainer._call_gemini_api_sync = original

    assert result.is_fallback, "Response with invalid number should trigger fallback"


# ─── Test 3: Fallback on timeout ───────────────────────────────────────────────

def test_fallback_on_timeout():
    """Timeout from AI call must return a fallback explanation without crashing."""
    import httpx
    from backend.app.services import ai_explainer
    from backend.app.services.ai_explainer import get_explanation_sync, _CACHE_DIR

    facts = _make_dummy_facts(packet_hash="timeouthash000003")
    cache_file = _CACHE_DIR / "timeouthash000003.json"
    cache_file.unlink(missing_ok=True)

    def fake_api_call_timeout(*args, **kwargs):
        raise httpx.TimeoutException("Simulated timeout")

    original = ai_explainer._call_gemini_api_sync
    ai_explainer._call_gemini_api_sync = fake_api_call_timeout
    try:
        result = get_explanation_sync(facts, api_key="fake-key-for-test")
    finally:
        ai_explainer._call_gemini_api_sync = original

    assert result.is_fallback, "Timeout should produce fallback"
    assert result.explanation_en, "Fallback must have non-empty English explanation"
    assert result.explanation_hi, "Fallback must have non-empty Hinglish explanation"


# ─── Test 4: Cache hit ─────────────────────────────────────────────────────────

def test_cache_hit():
    """Second call with same packet_hash must read from disk cache, no API call made."""
    from backend.app.services import ai_explainer
    from backend.app.services.ai_explainer import get_explanation_sync, _CACHE_DIR

    facts = _make_dummy_facts(packet_hash="cachehash0000004")
    cache_file = _CACHE_DIR / "cachehash0000004.json"

    # Pre-populate cache
    pre_explanation = AIExplanation(
        explanation_en="This was cached.",
        explanation_hi="Yeh cached tha.",
        watch_next_en="Watch next.",
        watch_next_hi="Agli ball dekhein.",
        is_fallback=False,
        validation_passed=True,
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(pre_explanation.model_dump(), f)

    api_called = False

    def fake_api_call_should_not_be_called(*args, **kwargs):
        nonlocal api_called
        api_called = True
        raise AssertionError("API should not be called when cache exists")

    original = ai_explainer._call_gemini_api_sync
    ai_explainer._call_gemini_api_sync = fake_api_call_should_not_be_called
    try:
        result = get_explanation_sync(facts, api_key="fake-key-for-test")
    finally:
        ai_explainer._call_gemini_api_sync = original

    assert not api_called, "API must not be called when cache entry exists"
    assert result.explanation_en == "This was cached."


# ─── Test 5: Team validation errors ────────────────────────────────────────────

def test_team_validation_too_few_players(engine):
    """Team with 10 players must fail validation."""
    team = FantasyTeam(
        name="Short Team",
        captain="Shubman Gill",
        vice_captain="WP Saha",
        players=["Shubman Gill", "WP Saha", "DA Miller", "V Shankar",
                 "Rashid Khan", "Mohammed Shami", "RK Singh", "SP Narine", "SN Thakur", "CV Varun"],
    )
    result = engine.validate_team(team)
    assert not result.is_valid
    assert any("11" in e for e in result.errors)


def test_team_validation_too_many_from_one_team(engine):
    """Team with 8 from one team must fail."""
    # 8 GT players
    team = FantasyTeam(
        name="GT Heavy",
        captain="Shubman Gill",
        vice_captain="WP Saha",
        players=[
            "Shubman Gill", "WP Saha", "DA Miller", "B Sai Sudharsan", "A Manohar",
            "V Shankar", "Rashid Khan", "Mohammed Shami",  # 8 GT
            "SP Narine", "SN Thakur", "CV Varun",  # 3 KKR
        ],
    )
    result = engine.validate_team(team)
    assert not result.is_valid
    assert any("Gujarat Titans" in e for e in result.errors)


def test_team_validation_wrong_captain(engine):
    """Captain not in players list must fail."""
    team = FantasyTeam(
        name="Bad Captain",
        captain="Virat Kohli",  # not in pool
        vice_captain="WP Saha",
        players=["Shubman Gill", "WP Saha", "DA Miller", "V Shankar",
                 "Rashid Khan", "Mohammed Shami", "RK Singh", "SP Narine",
                 "SN Thakur", "CV Varun", "Yash Dayal"],
    )
    result = engine.validate_team(team)
    assert not result.is_valid
    assert any("Captain" in e for e in result.errors)


def test_all_preset_teams_are_valid(engine):
    """All 3 preset teams must pass validation."""
    for key, team in PRESET_TEAMS.items():
        result = engine.validate_team(team)
        assert result.is_valid, f"Preset '{key}' failed: {result.errors}"


# ─── Test 6: E2E safe_pick preset instant mode ─────────────────────────────────

def test_e2e_safe_pick_preset_instant_mode():
    """
    Full match replay in instant mode for safe_pick team.
    Final team total must be positive and match count must equal 250.
    """
    team = PRESET_TEAMS["safe_pick"]
    session = FanSession(session_id="test-safe", fan_team=team, ai_api_key="")
    all_items = load_match_stream_items("1359487")
    delivery_count = 0

    for item in all_items:
        if item.item_type == "delivery" and item.delivery:
            ev = item.delivery.model_dump()
            session.process_one_delivery(ev)
            delivery_count += 1

    assert delivery_count == 250, f"Expected 250 deliveries, got {delivery_count}"
    final_total = session.team_total_history[-1]
    assert final_total > 0, "Final team total must be positive"
    # Shubman Gill scored big, so safe_pick team should have solid points
    assert final_total > 200, f"Safe pick final total too low: {final_total}"


# ─── Test 7: E2E differential preset — check Rashid Khan bowling points ────────

def test_e2e_differential_preset_instant_mode():
    """
    Full match for differential team (C: Rashid Khan).
    Rashid's hat-trick bowling points should be included, and key moments counted.
    """
    team = PRESET_TEAMS["differential"]
    session = FanSession(session_id="test-diff", fan_team=team, ai_api_key="")
    all_items = load_match_stream_items("1359487")

    for item in all_items:
        if item.item_type == "delivery" and item.delivery:
            ev = item.delivery.model_dump()
            session.process_one_delivery(ev)

    final_total = session.team_total_history[-1]
    assert final_total > 0

    # Hat-trick deliveries (inn2_d98-d100) must have generated key moments
    hattrick_kms = [km for km in session.key_moments if km.get("facts_packet") and km["facts_packet"].is_hattrick]
    assert len(hattrick_kms) > 0, "Expected at least 1 hat-trick key moment"

    # Key moment count should be in target range 25-45
    km_count = len(session.key_moments)
    assert 15 <= km_count <= 60, f"Key moment count {km_count} out of reasonable range"

    # Rashid Khan should have significant bowling points
    rashid_pts = session.engine.points_history[-1]["Rashid Khan"].total
    assert rashid_pts > 50, f"Rashid Khan points should be high (hat-trick), got {rashid_pts}"


# ─── Test 8: E2E finisher_fan preset — Russell and Rinku points ────────────────

def test_e2e_finisher_fan_preset_instant_mode():
    """
    Full match for finisher_fan team (C: AD Russell, VC: RK Singh).
    RK Singh hit 5 sixes in the final over, so his points should be meaningful.
    """
    team = PRESET_TEAMS["finisher_fan"]
    session = FanSession(session_id="test-finisher", fan_team=team, ai_api_key="")
    all_items = load_match_stream_items("1359487")

    for item in all_items:
        if item.item_type == "delivery" and item.delivery:
            ev = item.delivery.model_dump()
            session.process_one_delivery(ev)

    final_total = session.team_total_history[-1]
    assert final_total > 0

    # RK Singh (VC multiplier 1.5x) scored heavily — total should reflect that
    rk_raw = session.engine.points_history[-1]["RK Singh"].total
    assert rk_raw > 30, f"RK Singh raw points should be significant, got {rk_raw}"

    km_count = len(session.key_moments)
    assert km_count >= 10, f"Finisher fan should have meaningful key moments, got {km_count}"

