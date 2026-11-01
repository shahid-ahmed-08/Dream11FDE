import asyncio
import json
import time
import urllib.request
import httpx
from datetime import datetime


BASE_URL = "http://127.0.0.1:8000"


def log(msg):
    now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{now}] {msg}", flush=True)


async def run_live_tests():
    log("=== STARTING LIVE REAL-TIME STREAM VERIFICATION ===")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # ---------------------------------------------------------
        # TEST 1: Default Speed (1x = ~2.0s) for ~15 seconds
        # ---------------------------------------------------------
        log("\n--- TEST 1: Default Speed Stream for ~15s (Expected Spacing ~2.0s) ---")
        res = await client.post("/api/replay/sessions?match_id=1359487")
        assert res.status_code == 200
        session_a = res.json()["session_id"]
        log(f"Created Session A: {session_a}")

        # Start session
        await client.post(f"/api/replay/sessions/{session_a}/control", json={"action": "start"})
        log("Started Session A. Connecting to live SSE stream...")

        t1_events = []
        t1_start_time = time.time()

        async with client.stream("GET", f"/api/replay/sessions/{session_a}/stream") as response:
            assert response.status_code == 200
            current_event_type = None
            current_id = None

            async for line in response.aiter_lines():
                recv_time = time.time()
                if line.startswith("id:"):
                    current_id = int(line.split(":", 1)[1].strip())
                elif line.startswith("event:"):
                    current_event_type = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    raw_data = line.split(":", 1)[1].strip()
                    try:
                        data = json.loads(raw_data)
                        delta = recv_time - (t1_events[-1]["time"] if t1_events else t1_start_time)
                        t1_events.append({
                            "id": current_id,
                            "type": data.get("item_type"),
                            "time": recv_time,
                            "delta": delta,
                            "desc": (
                                data["marker"]["marker_type"]
                                if data.get("item_type") == "marker"
                                else f"Inn{data['delivery']['innings']} {data['delivery']['ball_display']} {data['delivery']['batter']} ({data['delivery']['runs_total']}r) -> {data['delivery']['situation']['score']}/{data['delivery']['situation']['wickets']}"
                            ),
                        })
                        log(f"Received Event #{current_id} ({t1_events[-1]['desc']}) | Arrival delta: {delta:.2f}s")
                    except Exception as e:
                        pass

                if time.time() - t1_start_time >= 15.0:
                    log("15 seconds elapsed for Test 1.")
                    break

        # Verify spacing
        deltas = [e["delta"] for e in t1_events[1:]]
        avg_delta = sum(deltas) / len(deltas) if deltas else 0.0
        log(f"Test 1 Summary: Received {len(t1_events)} events in {time.time() - t1_start_time:.2f}s. Average spacing: {avg_delta:.2f}s (Target: 2.0s).")
        assert 1.8 <= avg_delta <= 2.2, f"Expected ~2.0s spacing, got {avg_delta:.2f}s"

        # ---------------------------------------------------------
        # TEST 2: Pause for ~5s, then Resume
        # ---------------------------------------------------------
        log("\n--- TEST 2: Pause for ~5s, then Resume ---")
        last_id_before_pause = t1_events[-1]["id"]
        log(f"Sending PAUSE at index {last_id_before_pause}...")
        await client.post(f"/api/replay/sessions/{session_a}/control", json={"action": "pause"})

        pause_start = time.time()
        # Connect to stream during pause and verify nothing arrives for 5 seconds
        paused_received = []
        try:
            async with client.stream("GET", f"/api/replay/sessions/{session_a}/stream?from_index={last_id_before_pause+1}") as response:
                while time.time() - pause_start < 5.0:
                    line_task = response.aiter_lines().__anext__()
                    try:
                        line = await asyncio.wait_for(line_task, timeout=1.0)
                        if line.startswith("data:"):
                            paused_received.append(line)
                    except asyncio.TimeoutError:
                        pass
        except Exception:
            pass

        pause_duration = time.time() - pause_start
        log(f"Paused for {pause_duration:.2f}s. Events received while paused: {len(paused_received)} (Expected: 0)")
        assert len(paused_received) == 0, "Events were received while paused!"

        # Resume stream
        log("Sending RESUME...")
        await client.post(f"/api/replay/sessions/{session_a}/control", json={"action": "resume"})

        resumed_events = []
        resume_start = time.time()
        async with client.stream("GET", f"/api/replay/sessions/{session_a}/stream?from_index={last_id_before_pause+1}") as response:
            current_id = None
            async for line in response.aiter_lines():
                recv_time = time.time()
                if line.startswith("id:"):
                    current_id = int(line.split(":", 1)[1].strip())
                elif line.startswith("data:"):
                    raw_data = line.split(":", 1)[1].strip()
                    try:
                        data = json.loads(raw_data)
                        delta = recv_time - (resumed_events[-1]["time"] if resumed_events else resume_start)
                        resumed_events.append({
                            "id": current_id,
                            "desc": (
                                data["marker"]["marker_type"]
                                if data.get("item_type") == "marker"
                                else f"Inn{data['delivery']['innings']} {data['delivery']['ball_display']} {data['delivery']['batter']}"
                            ),
                            "time": recv_time,
                            "delta": delta,
                        })
                        log(f"Resumed Event #{current_id} ({resumed_events[-1]['desc']}) | Delta: {delta:.2f}s")
                    except Exception:
                        pass
                if len(resumed_events) >= 3:
                    break

        first_resumed_id = resumed_events[0]["id"]
        log(f"First event after resume was #{first_resumed_id}. Expected #{last_id_before_pause + 1}.")
        assert first_resumed_id == last_id_before_pause + 1, "Gap or duplicate upon resume!"

        # ---------------------------------------------------------
        # TEST 3: Switch to 5x Speed (Interval = 0.4s)
        # ---------------------------------------------------------
        log("\n--- TEST 3: Switch Speed to 5x (Expected Spacing ~0.4s) ---")
        log("Sending SET_SPEED = 5x...")
        await client.post(f"/api/replay/sessions/{session_a}/control", json={"action": "set_speed", "speed": "5x"})

        speed5x_events = []
        s5_start = time.time()
        async with client.stream("GET", f"/api/replay/sessions/{session_a}/stream?from_index={resumed_events[-1]['id']+1}") as response:
            current_id = None
            async for line in response.aiter_lines():
                recv_time = time.time()
                if line.startswith("id:"):
                    current_id = int(line.split(":", 1)[1].strip())
                elif line.startswith("data:"):
                    raw_data = line.split(":", 1)[1].strip()
                    try:
                        data = json.loads(raw_data)
                        delta = recv_time - (speed5x_events[-1]["time"] if speed5x_events else s5_start)
                        speed5x_events.append({
                            "id": current_id,
                            "time": recv_time,
                            "delta": delta,
                            "desc": (
                                data["marker"]["marker_type"]
                                if data.get("item_type") == "marker"
                                else f"Inn{data['delivery']['innings']} {data['delivery']['ball_display']} {data['delivery']['batter']}"
                            ),
                        })
                        log(f"5x Event #{current_id} ({speed5x_events[-1]['desc']}) | Delta: {delta:.2f}s")
                    except Exception:
                        pass
                if len(speed5x_events) >= 6:
                    break

        s5_deltas = [e["delta"] for e in speed5x_events[1:]]
        avg_s5_delta = sum(s5_deltas) / len(s5_deltas)
        log(f"5x Speed Average Spacing: {avg_s5_delta:.2f}s (Target: 0.4s).")
        assert 0.35 <= avg_s5_delta <= 0.45, f"Expected ~0.4s spacing for 5x, got {avg_s5_delta:.2f}s"

        # ---------------------------------------------------------
        # TEST 4: Disconnect mid-replay and Reconnect
        # ---------------------------------------------------------
        log("\n--- TEST 4: Disconnect Mid-Replay and Reconnect ---")
        last_before_disconnect = speed5x_events[-1]["id"]
        log(f"Client disconnecting abruptly after index #{last_before_disconnect}...")
        log("Waiting 3.0 seconds offline...")
        await asyncio.sleep(3.0)

        log(f"Client reconnecting with Last-Event-ID = {last_before_disconnect} (asking from index {last_before_disconnect+1})...")
        reconnect_events = []
        async with client.stream(
            "GET",
            f"/api/replay/sessions/{session_a}/stream",
            headers={"Last-Event-ID": str(last_before_disconnect)},
        ) as response:
            current_id = None
            async for line in response.aiter_lines():
                if line.startswith("id:"):
                    current_id = int(line.split(":", 1)[1].strip())
                elif line.startswith("data:"):
                    raw_data = line.split(":", 1)[1].strip()
                    try:
                        data = json.loads(raw_data)
                        reconnect_events.append({
                            "id": current_id,
                            "desc": (
                                data["marker"]["marker_type"]
                                if data.get("item_type") == "marker"
                                else f"Inn{data['delivery']['innings']} {data['delivery']['ball_display']}"
                            ),
                        })
                        log(f"Reconnected Stream received Event #{current_id} ({reconnect_events[-1]['desc']})")
                    except Exception:
                        pass
                if len(reconnect_events) >= 5:
                    break

        assert reconnect_events[0]["id"] == last_before_disconnect + 1, (
            f"Expected first reconnected item to be {last_before_disconnect + 1}, got {reconnect_events[0]['id']}"
        )
        log("SUCCESS: Reconnect resumed cleanly at exact next delivery with zero loss and zero duplicates!")

        # ---------------------------------------------------------
        # TEST 5: Two simultaneous streams with different speeds
        # ---------------------------------------------------------
        log("\n--- TEST 5: Two Simultaneous Independent Streams at Different Speeds ---")
        s1_res = await client.post("/api/replay/sessions?match_id=1359487")
        s2_res = await client.post("/api/replay/sessions?match_id=1359487")
        sid1 = s1_res.json()["session_id"]
        sid2 = s2_res.json()["session_id"]
        log(f"Session 1 (Speed 1x, 2.0s): {sid1}")
        log(f"Session 2 (Speed 5x, 0.4s): {sid2}")

        # Configure speeds & start both
        await client.post(f"/api/replay/sessions/{sid1}/control", json={"action": "set_speed", "speed": "1x"})
        await client.post(f"/api/replay/sessions/{sid2}/control", json={"action": "set_speed", "speed": "5x"})
        await client.post(f"/api/replay/sessions/{sid1}/control", json={"action": "start"})
        await client.post(f"/api/replay/sessions/{sid2}/control", json={"action": "start"})

        s1_count = 0
        s2_count = 0

        async def listen_s1():
            nonlocal s1_count
            async with client.stream("GET", f"/api/replay/sessions/{sid1}/stream") as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("id:"):
                        s1_count += 1
                        log(f"  [Session 1 - 1x] Got item #{s1_count}")

        async def listen_s2():
            nonlocal s2_count
            async with client.stream("GET", f"/api/replay/sessions/{sid2}/stream") as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("id:"):
                        s2_count += 1
                        log(f"  [Session 2 - 5x] Got item #{s2_count}")

        log("Running both streams concurrently for 5.0 seconds...")
        task1 = asyncio.create_task(listen_s1())
        task2 = asyncio.create_task(listen_s2())

        await asyncio.sleep(5.0)
        task1.cancel()
        task2.cancel()

        log(f"Concurrent Run Results over 5.0s:")
        log(f"  Session 1 (1x / 2.0s): Received {s1_count} items (Expected ~2-3)")
        log(f"  Session 2 (5x / 0.4s): Received {s2_count} items (Expected ~11-13)")
        assert s1_count >= 2, f"Session 1 received fewer than expected: {s1_count}"
        assert s2_count >= 10, f"Session 2 received fewer than expected: {s2_count}"
        assert s2_count > (s1_count * 3), "Session 2 should deliver substantially more events than Session 1!"
        log("SUCCESS: Two parallel sessions ran simultaneously at different speeds without interfering!")

    log("\n=== ALL 5 REAL-TIME STREAMING TESTS PASSED! ===")


if __name__ == "__main__":
    asyncio.run(run_live_tests())

