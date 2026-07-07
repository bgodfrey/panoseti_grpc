from __future__ import annotations

import math

import pytest

from panoseti_grpc.dome_heating import dome_telemetry as dt


# The dome_environment device type should map to the Redis prefix registered in
# telemetry_config.toml, so operators can predict the key for each dome.
def test_expected_redis_key_uses_registered_prefix() -> None:
    assert dt.expected_redis_key("dome_environment", "example_dome_id") == "DEV_DOME_ENV_example_dome_id"


# Unknown experimental device types should still produce the server's sandbox
# key shape instead of pretending they are registered production devices.
def test_expected_redis_key_falls_back_for_unknown_type() -> None:
    assert dt.expected_redis_key("new_device", "example_device_id") == "SANDBOX:new_device:example_device_id"


# Blank TOML serial-port fields mean "auto-discover this sensor by USB VID:PID";
# explicit nonblank paths are preserved for bench debugging.
def test_clean_optional_string_treats_blank_values_as_unset() -> None:
    assert dt.clean_optional_string(None) is None
    assert dt.clean_optional_string("") is None
    assert dt.clean_optional_string("   ") is None
    assert dt.clean_optional_string("/dev/ttyACM0") == "/dev/ttyACM0"


# One-off CLI overrides should beat TOML values, and TOML values should beat the
# script defaults. This keeps deployed configs stable but easy to override.
def test_config_value_precedence_cli_then_toml_then_default() -> None:
    config = {"telemetry": {"host": "toml-host"}}

    assert dt.config_value(config, "telemetry", "host", "cli-host", "default-host") == "cli-host"
    assert dt.config_value(config, "telemetry", "host", None, "default-host") == "toml-host"
    assert dt.config_value(config, "telemetry", "port", None, 50051) == 50051


# Check the Magnus dew-point approximation against a known lab-like reading.
def test_dew_point_matches_known_value() -> None:
    dewpoint = dt.dew_point_c(temp_c=23.56, humidity_percent=53.84)

    assert dewpoint == pytest.approx(13.67, abs=0.02)


# Nonpositive humidity is not physically useful for this calculation, so the
# helper returns NaN rather than raising inside the telemetry loop.
def test_dew_point_returns_nan_for_nonphysical_humidity() -> None:
    assert math.isnan(dt.dew_point_c(temp_c=20.0, humidity_percent=0.0))


# With no configured threshold, the daemon should report telemetry only and not
# emit a heater notice even if the temperature delta is large.
def test_heater_notice_inactive_without_threshold() -> None:
    notice = dt.evaluate_heater_notice(
        roof_temp_c=20.0,
        internal_temp_c=24.0,
        delta_temp_c=4.0,
        humidity_percent=50.0,
        dewpoint_c=10.0,
        delta_notice_threshold_c=None,
    )

    assert notice == dt.HeaterNotice(active=False, notice="none")


# The current prototype turns the notice on exactly at the configured delta
# threshold. This protects the boundary behavior.
def test_heater_notice_active_at_or_above_threshold() -> None:
    notice = dt.evaluate_heater_notice(
        roof_temp_c=20.0,
        internal_temp_c=22.5,
        delta_temp_c=2.5,
        humidity_percent=50.0,
        dewpoint_c=10.0,
        delta_notice_threshold_c=2.5,
    )

    assert notice == dt.HeaterNotice(active=True, notice="TURN_ON_HEATER")


# Deltas below threshold should stay telemetry-only. Future humidity/dew-point
# logic can extend evaluate_heater_notice without changing this baseline case.
def test_heater_notice_inactive_below_threshold() -> None:
    notice = dt.evaluate_heater_notice(
        roof_temp_c=20.0,
        internal_temp_c=22.4,
        delta_temp_c=2.4,
        humidity_percent=50.0,
        dewpoint_c=10.0,
        delta_notice_threshold_c=2.5,
    )

    assert notice == dt.HeaterNotice(active=False, notice="none")


# Build the compact Redis payload from one fake sensor sample. The monkeypatch
# fixes time.time() so the expected payload is deterministic.
def test_build_payload_uses_configured_sensor_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dt.time, "time", lambda: 123.456)
    readings = dt.SensorReadings(
        sht45_temp_c=23.56,
        humidity_percent=53.84,
        ds18b20_temp_c=20.87,
    )

    payload = dt.build_payload(
        readings,
        roof_source="ds18b20",
        internal_source="sht45",
        heater_on=False,
        delta_notice_threshold_c=2.5,
    )

    assert payload == {
        "roof_temp_c": 20.87,
        "internal_temp_c": 23.56,
        "delta_temp_c": pytest.approx(2.69),
        "humidity_percent": 53.84,
        "dew_point_c": pytest.approx(13.67, abs=0.02),
        "heater_notice": "TURN_ON_HEATER",
        "heater_notice_active": True,
        "heater_on": False,
        "client_unix_time": 123.456,
    }


# Sensor roles are config-driven, so the payload builder must respect a swapped
# roof/internal assignment without changing the underlying sensor readings.
def test_build_payload_can_swap_sensor_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dt.time, "time", lambda: 123.456)
    readings = dt.SensorReadings(
        sht45_temp_c=23.56,
        humidity_percent=53.84,
        ds18b20_temp_c=20.87,
    )

    payload = dt.build_payload(
        readings,
        roof_source="sht45",
        internal_source="ds18b20",
        heater_on=True,
        delta_notice_threshold_c=10.0,
    )

    assert payload["roof_temp_c"] == 23.56
    assert payload["internal_temp_c"] == 20.87
    assert payload["heater_notice"] == "none"
    assert payload["heater_notice_active"] is False
    assert payload["heater_on"] is True
