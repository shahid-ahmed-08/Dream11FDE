import pytest
from backend.app.models.replay import (
    ControlAction,
    ControlRequest,
    MarkerType,
    ReplaySpeed,
    SessionStatus,
    SPEED_INTERVALS,
)
from backend.app.services.replay_engine import ReplaySession, replay_manager
from backend.app.routers.replay import (
    create_replay_session,
    control_session,
    step_session,
    run_session_instant,
    get_session_events,
    get_session_state,
)


def test_instant_mode_delivers_exact_events_and_markers():
    """
    Proves: Instant mode delivers exactly 250 ball events plus 3 markers (253 total items),
    ending on KKR's 207/7.
    """
    session = ReplaySession("test-instant-session")
    items = session.run_instant()

    assert len(items) == 253, f"Expected 253 total stream items, got {len(items)}"

    # Markers check
    markers = [item for item in items if item.item_type == "marker"]
    deliveries = [item for item in items if item.item_type == "delivery"]

    assert len(markers) == 3, f"Expected 3 markers, got {len(markers)}"
    assert len(deliveries) == 250, f"Expected 250 deliveries, got {len(deliveries)}"

    # Check marker 1: replay_started
    assert markers[0].marker.marker_type == MarkerType.REPLAY_STARTED
    assert markers[0].marker.payload["match_id"] == "1359487"

    # Check marker 2: innings_break
    assert markers[1].marker.marker_type == MarkerType.INNINGS_BREAK
    assert markers[1].marker.payload["innings_completed"] == 1
    assert markers[1].marker.payload["score"] == 204
    assert markers[1].marker.payload["wickets"] == 4
    assert markers[1].marker.payload["target"] == 205

    # Check marker 3: match_finished
    assert markers[2].marker.marker_type == MarkerType.MATCH_FINISHED
    assert markers[2].marker.payload["winner"] == "Kolkata Knight Riders"
    assert markers[2].marker.payload["margin"] == {"wickets": 3}
    assert markers[2].marker.payload["player_of_match"] == ["RK Singh"]

    # Check final delivery: KKR 207/7 on ball 19.6
    last_delivery = deliveries[-1].delivery
    assert last_delivery.batter == "RK Singh"
    assert last_delivery.runs_batter == 6
    assert last_delivery.situation.score == 207
    assert last_delivery.situation.wickets == 7
    assert session.is_finished is True


def test_events_are_strictly_in_order():
    """
    Proves: All stream items and ball deliveries are strictly in ascending order.
    """
    session = ReplaySession("test-order-session")
    items = session.run_instant()

    for idx, item in enumerate(items):
        assert item.stream_index == idx, f"Stream index mismatch at position {idx}"

    deliveries = [item.delivery for item in items if item.item_type == "delivery"]
    # Check Innings 1 order
    inn1_deliveries = [d for d in deliveries if d.innings == 1]
    assert len(inn1_deliveries) == 127
    for idx, d in enumerate(inn1_deliveries, start=1):
        assert d.delivery_in_innings == idx

    # Check Innings 2 order
    inn2_deliveries = [d for d in deliveries if d.innings == 2]
    assert len(inn2_deliveries) == 123
    for idx, d in enumerate(inn2_deliveries, start=1):
        assert d.delivery_in_innings == idx


def test_none_are_missing_or_duplicated():
    """
    Proves: No delivery is skipped, missed, or duplicated.
    """
    session = ReplaySession("test-integrity-session")
    items = session.run_instant()

    delivery_ids = [item.delivery.event_id for item in items if item.item_type == "delivery"]
    assert len(delivery_ids) == 250
    assert len(set(delivery_ids)) == 250, "Duplicate delivery IDs detected in replay stream!"


def test_controls_pause_resume_restart_speed():
    """
    Proves: start, pause, resume, restart, and speed controls function correctly.
    """
    session = ReplaySession("test-controls-session")
    assert session.status == SessionStatus.INITIALIZED

    # Start
    session.start()
    assert session.status == SessionStatus.PLAYING

    # Step forward 10 deliveries
    emitted = session.step(10)
    assert len(emitted) == 10
    assert session.current_index == 10

    # Pause
    session.pause()
    assert session.status == SessionStatus.PAUSED
    assert session.current_index == 10

    # Resume
    session.resume()
    assert session.status == SessionStatus.PLAYING

    # Speed changes
    assert session.speed == ReplaySpeed.SPEED_1X
    assert session.interval_seconds == 2.0

    session.set_speed(ReplaySpeed.SPEED_2X)
    assert session.speed == ReplaySpeed.SPEED_2X
    assert session.interval_seconds == 1.0

    session.set_speed(ReplaySpeed.SPEED_5X)
    assert session.speed == ReplaySpeed.SPEED_5X
    assert session.interval_seconds == 0.4

    session.set_speed(ReplaySpeed.INSTANT)
    assert session.speed == ReplaySpeed.INSTANT
    assert session.interval_seconds == 0.0

    # Restart
    session.restart()
    assert session.current_index == 0
    assert len(session.delivered_indices) == 0
    assert session.status == SessionStatus.PLAYING


def test_reconnect_resumes_without_duplicates_or_missed_events():
    """
    Proves: If a client disconnects at index 50 and reconnects asking for events from 50,
    the replay engine returns events strictly starting at 50, avoiding both duplicates and dropped deliveries.
    """
    session = ReplaySession("test-reconnect-session")
    session.start()

    # Step to 50 items
    first_batch = session.step(50)
    assert len(first_batch) == 50
    assert session.current_index == 50

    # Client reconnects asking for items from index 50 onwards
    # (they already acknowledged 0-49)
    recovered_items = session.get_items_from(from_index=50)
    assert len(recovered_items) == 0  # Since current_index is 50, nothing has been stepped yet

    # Step another 30 items
    second_batch = session.step(30)
    assert len(second_batch) == 30
    assert session.current_index == 80

    # Reconnection query from index 50 to current 80 returns exactly those 30 items
    catchup_items = session.get_items_from(from_index=50)
    assert len(catchup_items) == 30
    assert catchup_items[0].stream_index == 50
    assert catchup_items[-1].stream_index == 79

    # Verify no overlaps between first_batch and catchup_items
    first_indices = {i.stream_index for i in first_batch}
    catchup_indices = {i.stream_index for i in catchup_items}
    assert first_indices.isdisjoint(catchup_indices)
    assert first_indices.union(catchup_indices) == set(range(80))


def test_two_simultaneous_sessions_stay_independent():
    """
    Proves: Two separate viewer sessions remain fully independent:
    pausing or stepping Session 1 has zero effect on Session 2.
    """
    session1 = replay_manager.create_session("1359487")
    session2 = replay_manager.create_session("1359487")

    assert session1.session_id != session2.session_id

    # Start both
    session1.start()
    session2.start()

    # Advance session 1 by 15 steps
    session1.step(15)
    assert session1.current_index == 15
    assert session2.current_index == 0  # Session 2 must remain at 0

    # Pause session 1
    session1.pause()
    assert session1.status == SessionStatus.PAUSED
    assert session2.status == SessionStatus.PLAYING  # Session 2 still playing

    # Advance session 2 by 40 steps
    session2.step(40)
    assert session1.current_index == 15  # Session 1 still paused at 15
    assert session2.current_index == 40

    # Restart session 2
    session2.restart()
    assert session2.current_index == 0
    assert session1.current_index == 15  # Session 1 unaffected

    # Clean up
    replay_manager.remove_session(session1.session_id)
    replay_manager.remove_session(session2.session_id)


def test_api_endpoints_for_replay_controls():
    """
    Proves: API router endpoints handle create, control, step, instant, and query actions.
    """
    state = create_replay_session(match_id="1359487")
    sid = state.session_id

    # Verify initial state via API
    fetched_state = get_session_state(sid)
    assert fetched_state.session_id == sid
    assert fetched_state.total_items == 253

    # Start via API
    control_res = control_session(sid, ControlRequest(action=ControlAction.START))
    assert control_res.status == SessionStatus.PLAYING

    # Step 5 items via API
    stepped = step_session(sid, steps=5)
    assert len(stepped) == 5
    assert stepped[0].stream_index == 0

    # Pause via API
    paused_res = control_session(sid, ControlRequest(action=ControlAction.PAUSE))
    assert paused_res.status == SessionStatus.PAUSED

    # Set speed via API
    speed_res = control_session(sid, ControlRequest(action=ControlAction.SET_SPEED, speed=ReplaySpeed.SPEED_5X))
    assert speed_res.speed == ReplaySpeed.SPEED_5X

    # Instant completion via API
    instant_items = run_session_instant(sid)
    assert len(instant_items) == 248  # 253 - 5 already stepped
    final_state = get_session_state(sid)
    assert final_state.is_finished is True
    assert final_state.current_index == 253

    # Clean up
    replay_manager.remove_session(sid)

