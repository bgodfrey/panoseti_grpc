"""
Unit tests for agent_v1.TelemetryAgg using fake UBX frames from
fake_gnss_generator.py.

These tests exercise the frame-parsing logic inside TelemetryAgg without
requiring a real serial port, gRPC connection, or Redis instance.
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import helpers: load agent_v1 and fake_gnss_generator from the submodule
# path without requiring them to be installed as packages.
# ---------------------------------------------------------------------------

SUBMOD = Path(__file__).resolve().parents[3] / "gnss_config" / "U-Blox_F9T_Config"

# Put submodule on sys.path so agent_v1's bare `import caster_setup_pb2` resolves.
if str(SUBMOD) not in sys.path:
    sys.path.insert(0, str(SUBMOD))


def _load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, SUBMOD / f"{name}.py")
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gen():
    return _load_module("fake_gnss_generator")


@pytest.fixture(scope="module")
def agent():
    return _load_module("agent_v1")


@pytest.fixture
def agg(agent):
    return agent.TelemetryAgg()


# ---------------------------------------------------------------------------
# TIM-TP: quantisation error and UTC flag
# ---------------------------------------------------------------------------

class TestTimTp:
    def test_qerr_populated(self, agg, gen, agent):
        frame = gen.make_tim_tp(qerr_ps=3000)
        agg.feed_ubx(frame)
        assert agg.qerr_ps == 3000

    def test_qerr_negative(self, agg, gen, agent):
        frame = gen.make_tim_tp(qerr_ps=-2500)
        agg.feed_ubx(frame)
        assert agg.qerr_ps == -2500

    def test_utc_ok_true(self, agg, gen, agent):
        frame = gen.make_tim_tp(utc_ok=True)
        agg.feed_ubx(frame)
        assert agg.utc_ok is True

    def test_utc_ok_false(self, agg, gen, agent):
        frame = gen.make_tim_tp(utc_ok=False)
        agg.feed_ubx(frame)
        assert agg.utc_ok is False


# ---------------------------------------------------------------------------
# NAV-SAT: satellite counts and avg C/N0
# ---------------------------------------------------------------------------

class TestNavSat:
    def test_empty_sat_list_zeroes_counts(self, agg, gen, agent):
        frame = gen.make_nav_sat(satellites=[])
        agg.feed_ubx(frame)
        assert agg.num_vis  == 0
        assert agg.num_used == 0
        assert agg.avg_cno  == 0.0

    def test_used_satellite_counted(self, agg, gen, agent):
        sats = [{"gnss_id": 0, "sv_id": 1, "cno": 40, "used": True}]
        frame = gen.make_nav_sat(satellites=sats)
        agg.feed_ubx(frame)
        assert agg.num_vis  == 1
        assert agg.num_used == 1
        assert agg.gps_used == 1

    def test_unused_satellite_not_counted(self, agg, gen, agent):
        sats = [{"gnss_id": 0, "sv_id": 1, "cno": 20, "used": False}]
        frame = gen.make_nav_sat(satellites=sats)
        agg.feed_ubx(frame)
        assert agg.num_vis  == 1
        assert agg.num_used == 0
        assert agg.gps_used == 0

    def test_multi_constellation(self, agg, gen, agent):
        sats = [
            {"gnss_id": 0, "sv_id": 1,  "cno": 40, "used": True},   # GPS
            {"gnss_id": 2, "sv_id": 10, "cno": 38, "used": True},   # Galileo
            {"gnss_id": 3, "sv_id": 20, "cno": 35, "used": True},   # BeiDou
            {"gnss_id": 6, "sv_id": 30, "cno": 33, "used": True},   # GLONASS
        ]
        frame = gen.make_nav_sat(satellites=sats)
        agg.feed_ubx(frame)
        assert agg.num_used  == 4
        assert agg.gps_used  == 1
        assert agg.gal_used  == 1
        assert agg.bds_used  == 1
        assert agg.glo_used  == 1

    def test_avg_cno_computed(self, agg, gen, agent):
        sats = [
            {"gnss_id": 0, "cno": 40, "used": True},
            {"gnss_id": 0, "cno": 30, "used": True},
        ]
        frame = gen.make_nav_sat(satellites=sats)
        agg.feed_ubx(frame)
        assert abs(agg.avg_cno - 35.0) < 0.01


# ---------------------------------------------------------------------------
# NAV-DOP: position dilution of precision
# ---------------------------------------------------------------------------

class TestNavDop:
    def test_pdop_populated(self, agg, gen, agent):
        frame = gen.make_nav_dop(pdop=2.5)
        agg.feed_ubx(frame)
        assert abs(agg.pdop - 2.5) < 0.02   # allow for × 100 integer rounding


# ---------------------------------------------------------------------------
# NAV-TIMEUTC: UTC validity
# ---------------------------------------------------------------------------

class TestNavTimeUtc:
    def test_valid_utc(self, agg, gen, agent):
        frame = gen.make_nav_timeutc(utc_ok=True)
        agg.feed_ubx(frame)
        assert agg.utc_ok is True

    def test_invalid_utc(self, agg, gen, agent):
        frame = gen.make_nav_timeutc(utc_ok=False)
        agg.feed_ubx(frame)
        assert agg.utc_ok is False


# ---------------------------------------------------------------------------
# Scenario helpers
# ---------------------------------------------------------------------------

class TestScenarios:
    def test_good_fix_populates_all_fields(self, agg, gen, agent):
        for frame in gen.scenario_good_fix(qerr_ps=1500, temp_c=42.0, pdop=1.2, num_sats=8):
            agg.feed_ubx(frame)
        assert agg.qerr_ps  == 1500
        assert agg.num_vis  == 8
        assert agg.num_used == 8
        assert agg.gps_used == 8
        assert abs(agg.pdop - 1.2) < 0.02
        assert agg.utc_ok   is True

    def test_no_fix_zeroes_sat_counts(self, agg, gen, agent):
        for frame in gen.scenario_no_fix():
            agg.feed_ubx(frame)
        assert agg.num_vis  == 0
        assert agg.num_used == 0
        assert agg.utc_ok   is False


# ---------------------------------------------------------------------------
# RTCM checksum validation: frames must pass _crc24q
# ---------------------------------------------------------------------------

class TestRtcmFrames:
    def test_rtcm_frame_passes_crc(self, gen):
        frame = gen.make_rtcm_frame(1005)
        L = ((frame[1] & 0x03) << 8) | frame[2]
        crc_computed = gen._crc24q(frame[:-3])
        crc_stored   = int.from_bytes(frame[-3:], "big")
        assert crc_computed == crc_stored

    def test_rtcm_scenario_all_pass_crc(self, gen):
        for frame in gen.scenario_rtcm_stream():
            L = ((frame[1] & 0x03) << 8) | frame[2]
            assert gen._crc24q(frame[:-3]) == int.from_bytes(frame[-3:], "big")


# ---------------------------------------------------------------------------
# Async: ubx_telemetry_loop feeds TelemetryAgg from a queue
# ---------------------------------------------------------------------------

class TestUbxTelemetryLoop:
    @pytest.mark.asyncio
    async def test_loop_feeds_agg_via_queue(self, gen, agent):
        """Feed fake UBX frames through ubx_telemetry_loop and check TelemetryAgg."""
        q   = asyncio.Queue()
        agg = agent.TelemetryAgg()

        for frame in gen.scenario_good_fix(qerr_ps=5000, num_sats=6):
            await q.put(frame)
        await q.put(None)  # sentinel to stop loop

        await agent.ubx_telemetry_loop(q, agg)

        assert agg.qerr_ps  == 5000
        assert agg.num_vis  == 6
        assert agg.num_used == 6
        assert agg.utc_ok   is True
