import subprocess
import sys
import time
import os

print("Starting Uvicorn server in background on 127.0.0.1:8000...", flush=True)
server_proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--port", "8000", "--host", "127.0.0.1"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

try:
    # Wait for server to bind
    time.sleep(2.5)

    # Run verification script
    print("Launching live real-time stream client test...", flush=True)
    test_proc = subprocess.run(
        [sys.executable, "backend/tests/verify_realtime_stream.py"],
        capture_output=False,
    )
    if test_proc.returncode != 0:
        print(f"Test failed with exit code {test_proc.returncode}", flush=True)
        sys.exit(test_proc.returncode)
finally:
    print("Shutting down Uvicorn server...", flush=True)
    server_proc.terminate()
    try:
        server_proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        server_proc.kill()
    print("Uvicorn server stopped.", flush=True)

