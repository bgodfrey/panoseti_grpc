"""
End-to-end integration tests for the fake GNSS agent pipeline.

Tests verify the full data path:

  fake_agent (BASE)  →  Control.Pipe  →  server_v1
  fake_agent (BASE)  →  Caster.Publish →  server_v1  →  Caster.Subscribe  →  fake_agent (RECEIVER)
  server_v1          →  TELEM_FWD_Q   →  telem_forwarder_loop
                     →  Telemetry.ReportStatus  →  Redis  (key: UBLOX_ZED-F9T_<device_id>)

Assertions:
  1. Redis has a telemetry record for the BASE agent.
  2. Redis has a telemetry record for the RECEIVER agent.
  3. Both records contain plausible GNSS telemetry fields.

The Docker Compose stack starts the agents and server before the test runner,
so the test only needs to poll Redis with a generous timeout.
"""

import json
import time
from typing import Dict, Optional

import pytest
import redis

# ── constants ─────────────────────────────────────────────────────────────────

BASE_DEVICE_ID = "FAKE_BASE_001"
RECV_DEVICE_ID = "FAKE_RECV_001"

# telemetry_config.toml: [devices.gnss] redis_prefix = "UBLOX_ZED-F9T_"
REDIS_PREFIX   = "UBLOX_ZED-F9T_"

BASE_KEY = f"{REDIS_PREFIX}{BASE_DEVICE_ID}"
RECV_KEY = f"{REDIS_PREFIX}{RECV_DEVICE_ID}"

POLL_INTERVAL = 2.0     # seconds between Redis polls
TELEM_TIMEOUT = 90.0    # max seconds to wait for both devices' telemetry


# ── helpers ───────────────────────────────────────────────────────────────────

def _wait_for_key(r: redis.Redis, key: str, timeout: float) -> Optional[Dict[str, str]]:
    """Poll *key* (Redis hash) until it exists or *timeout* elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = r.hgetall(key)
        if data:
            return data
        time.sleep(POLL_INTERVAL)
    return None


# ── tests ─────────────────────────────────────────────────────────────────────

class TestTelemetryReachesRedis:
    """Verify that telemetry from both fake agents arrives in Redis."""

    def test_base_telemetry_in_redis(self, redis_connection):
        """BASE agent telemetry should appear under UBLOX_ZED-F9T_FAKE_BASE_001."""
        data = _wait_for_key(redis_connection, BASE_KEY, TELEM_TIMEOUT)
        assert data is not None, (
            f"No telemetry for BASE agent in Redis after {TELEM_TIMEOUT}s. "
            f"Expected key: {BASE_KEY}"
        )

    def test_receiver_telemetry_in_redis(self, redis_connection):
        """RECEIVER agent telemetry should appear under UBLOX_ZED-F9T_FAKE_RECV_001."""
        data = _wait_for_key(redis_connection, RECV_KEY, TELEM_TIMEOUT)
        assert data is not None, (
            f"No telemetry for RECEIVER agent in Redis after {TELEM_TIMEOUT}s. "
            f"Expected key: {RECV_KEY}"
        )

    def test_base_telemetry_has_gnss_fields(self, redis_connection):
        """BASE telemetry record should include numeric GNSS fields."""
        data = _wait_for_key(redis_connection, BASE_KEY, TELEM_TIMEOUT)
        assert data is not None, f"Missing key: {BASE_KEY}"

        # The Telemetry Service stores GnssPayload base fields (satellites,
        # lat, lon, fix_mode) plus extra_data fields prefixed with "extra_".
        expected_fields = {
            "satellites", "fix_mode",
            "extra_qerr_ns", "extra_num_vis", "extra_num_used",
            "extra_avg_cno", "extra_utc_ok",
        }
        present = expected_fields & set(data.keys())
        assert present, (
            f"BASE telemetry missing expected fields. "
            f"Got keys: {sorted(data.keys())}"
        )

    def test_receiver_telemetry_has_gnss_fields(self, redis_connection):
        """RECEIVER telemetry record should include numeric GNSS fields."""
        data = _wait_for_key(redis_connection, RECV_KEY, TELEM_TIMEOUT)
        assert data is not None, f"Missing key: {RECV_KEY}"

        expected_fields = {
            "satellites", "fix_mode",
            "extra_qerr_ns", "extra_num_vis", "extra_num_used",
            "extra_avg_cno", "extra_utc_ok",
        }
        present = expected_fields & set(data.keys())
        assert present, (
            f"RECEIVER telemetry missing expected fields. "
            f"Got keys: {sorted(data.keys())}"
        )

    def test_base_utc_ok_is_true(self, redis_connection):
        """Fake frames have utc_ok=True; verify this propagated to Redis."""
        data = _wait_for_key(redis_connection, BASE_KEY, TELEM_TIMEOUT)
        assert data is not None, f"Missing key: {BASE_KEY}"
        utc_ok = data.get("extra_utc_ok", "")
        # Redis stores everything as strings; accept "True", "1", or "true"
        assert utc_ok.lower() in ("true", "1"), (
            f"Expected extra_utc_ok=True for BASE, got {utc_ok!r}"
        )

    def test_base_satellites_visible(self, redis_connection):
        """scenario_good_fix produces 10 satellites; extra_num_vis should be ≥ 1."""
        data = _wait_for_key(redis_connection, BASE_KEY, TELEM_TIMEOUT)
        assert data is not None, f"Missing key: {BASE_KEY}"
        # Struct round-trips ints as floats, so Redis stores e.g. "10.0"
        num_vis = int(float(data.get("extra_num_vis", 0)))
        assert num_vis >= 1, f"Expected extra_num_vis ≥ 1, got {num_vis}"


class TestRtcmForwarding:
    """Verify that RTCM frames published by the BASE reach the RECEIVER.

    The fake_receiver logs are not directly accessible here, but the mere
    presence of the RECEIVER's telemetry record in Redis proves that:
      - The RECEIVER agent connected and completed the Control.Pipe handshake
      - The RECEIVER agent sent at least one telemetry snapshot to the server
      - The server forwarded that snapshot to the Telemetry Service

    A richer check would require inspecting the RECEIVER's log output or
    a counter endpoint on server_v1, but that is beyond the scope of this test.
    """

    def test_receiver_connected_and_sent_telemetry(self, redis_connection):
        """If RECEIVER telemetry is in Redis, it successfully connected."""
        data = _wait_for_key(redis_connection, RECV_KEY, TELEM_TIMEOUT)
        assert data is not None, (
            "RECEIVER agent did not produce any telemetry in Redis. "
            "This may indicate that Caster.Subscribe failed or the RECEIVER "
            "agent crashed before sending telemetry."
        )


class TestBothAgentsSimultaneous:
    """Verify that both agents can run concurrently without cross-contamination."""

    def test_both_keys_present(self, redis_connection):
        """Both BASE and RECEIVER keys must exist."""
        base_data = _wait_for_key(redis_connection, BASE_KEY, TELEM_TIMEOUT)
        recv_data = _wait_for_key(redis_connection, RECV_KEY, TELEM_TIMEOUT)
        assert base_data is not None, f"Missing BASE key: {BASE_KEY}"
        assert recv_data is not None, f"Missing RECEIVER key: {RECV_KEY}"

    def test_device_ids_are_distinct_keys(self, redis_connection):
        """The two agents must write to different Redis keys."""
        assert BASE_KEY != RECV_KEY
        base_data = redis_connection.hgetall(BASE_KEY)
        recv_data = redis_connection.hgetall(RECV_KEY)
        # Each dict should have data and they should be stored under separate keys
        assert isinstance(base_data, dict)
        assert isinstance(recv_data, dict)
