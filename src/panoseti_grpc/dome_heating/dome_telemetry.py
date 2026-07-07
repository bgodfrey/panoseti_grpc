#!/usr/bin/env python3
"""Read dome environmental sensors and publish snapshots via Telemetry gRPC."""

from __future__ import annotations

import argparse
import math
import time
import tomllib
from dataclasses import dataclass

from temp_config.Environmental_Monitoring_Panoseti.ds18b20 import DS1820BUSB
from temp_config.Environmental_Monitoring_Panoseti.sht45 import SHT45USB


PayloadValue = int | float | str | bool | None

# These mirror the Telemetry server's experimental Redis prefixes so the local
# process can print the expected key without querying the head node.
KNOWN_REDIS_PREFIXES = {
    "example": "DEV_EXAMPLE_",
    "dome_environment": "DEV_DOME_ENV_",
}

# Defaults are used when neither the TOML config nor CLI flags provide a value.
# CLI flags intentionally override TOML so field tests can tweak one setting
# without editing the deployed config file.
DEFAULTS = {
    "host": "localhost",
    "port": 50051,
    "device_type": "dome_environment",
    "device_id": "dome_test",
    "interval": 5.0,
    "roof_source": "ds18b20",
    "internal_source": "sht45",
    "sht45_port": None,
    "ds18b20_port": None,
    "heater_on": False,
    "delta_notice_threshold_c": None,
    "quiet": False,
}


def expected_redis_key(device_type: str, device_id: str) -> str:
    """Return the Redis key the current server config is expected to use."""
    prefix = KNOWN_REDIS_PREFIXES.get(device_type)
    if prefix:
        return f"{prefix}{device_id}"
    return f"SANDBOX:{device_type}:{device_id}"


def load_toml_config(path: str | None) -> dict:
    """Load a DAQ-node config file; missing path means use defaults/CLI only."""
    if path is None:
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def clean_optional_string(value: object) -> str | None:
    """Treat empty strings in TOML as unset serial-port paths."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def config_value(config: dict, section: str, key: str, cli_value: object, default: object) -> object:
    """Resolve one setting with precedence: CLI flag, TOML, then default."""
    if cli_value is not None:
        return cli_value
    section_data = config.get(section, {})
    if key in section_data:
        return section_data[key]
    return default


@dataclass(frozen=True)
class SensorReadings:
    """One synchronized-enough sample from the two USB sensor streams."""

    sht45_temp_c: float
    humidity_percent: float
    ds18b20_temp_c: float


@dataclass(frozen=True)
class HeaterNotice:
    """Telemetry-only heater recommendation derived from environmental data."""

    active: bool
    notice: str


def dew_point_c(temp_c: float, humidity_percent: float) -> float:
    """Approximate dew point using the Magnus formula."""
    if humidity_percent <= 0:
        return float("nan")
    humidity = min(humidity_percent, 100.0)
    a = 17.625
    b = 243.04
    gamma = math.log(humidity / 100.0) + (a * temp_c) / (b + temp_c)
    return (b * gamma) / (a - gamma)


def evaluate_heater_notice(
    *,
    roof_temp_c: float,
    internal_temp_c: float,
    delta_temp_c: float,
    humidity_percent: float,
    dewpoint_c: float,
    delta_notice_threshold_c: float | None,
) -> HeaterNotice:
    """Decide whether to emit a telemetry-only heater notice.

    This is intentionally not heater control. It is the decision point where
    future rules can consider humidity, dew point, sensor confidence, and
    hysteresis in addition to the current temperature-delta threshold.
    """
    notice_active = (
        delta_notice_threshold_c is not None
        and delta_temp_c >= delta_notice_threshold_c
    )
    if notice_active:
        return HeaterNotice(
            active=True,
            notice="TURN_ON_HEATER",
        )
    return HeaterNotice(active=False, notice="none")


def read_sensors(sht: SHT45USB, ds: DS1820BUSB) -> SensorReadings:
    """Read one blocking sample from each sensor wrapper."""
    _sht_ms, sht_temp_c, humidity_percent, _sht_extra = sht.read()
    _ds_ms, ds_temp_c, _ds_extra = ds.read()
    return SensorReadings(
        sht45_temp_c=sht_temp_c,
        humidity_percent=humidity_percent,
        ds18b20_temp_c=ds_temp_c,
    )


def build_payload(
    readings: SensorReadings,
    *,
    roof_source: str,
    internal_source: str,
    heater_on: bool,
    delta_notice_threshold_c: float | None,
) -> dict[str, PayloadValue]:
    """Build the flexible Telemetry payload stored as the latest Redis hash."""
    temps = {
        "sht45": readings.sht45_temp_c,
        "ds18b20": readings.ds18b20_temp_c,
    }
    roof_temp_c = temps[roof_source]
    internal_temp_c = temps[internal_source]
    delta_temp_c = abs(roof_temp_c - internal_temp_c)
    dewpoint_c = dew_point_c(readings.sht45_temp_c, readings.humidity_percent)
    # This is only a telemetry notice. It does not assert that heater hardware
    # has changed state; heater_on remains separately reported.
    heater_notice = evaluate_heater_notice(
        roof_temp_c=roof_temp_c,
        internal_temp_c=internal_temp_c,
        delta_temp_c=delta_temp_c,
        humidity_percent=readings.humidity_percent,
        dewpoint_c=dewpoint_c,
        delta_notice_threshold_c=delta_notice_threshold_c,
    )

    return {
        "roof_temp_c": roof_temp_c,
        "internal_temp_c": internal_temp_c,
        "delta_temp_c": delta_temp_c,
        "humidity_percent": readings.humidity_percent,
        "dew_point_c": dewpoint_c,
        "heater_notice": heater_notice.notice,
        "heater_notice_active": heater_notice.active,
        "heater_on": heater_on,
        "client_unix_time": time.time(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None, help="Path to DAQ-node TOML config")
    parser.add_argument("--once", action="store_true", help="Publish one sample and exit")
    parser.add_argument("--no-publish", action="store_true", help="Read and print payloads without gRPC publish")
    parser.add_argument("--verbose", action="store_true", help="Print Telemetry connection state changes")

    # Advanced overrides are intentionally hidden from normal help. The service
    # should usually be configured through TOML, but these remain useful during
    # bench tests and one-off debugging.
    advanced = argparse.SUPPRESS
    parser.add_argument("--host", default=None, help=advanced)
    parser.add_argument("--port", type=int, default=None, help=advanced)
    parser.add_argument("--device-type", default=None, help=advanced)
    parser.add_argument("--device-id", default=None, help=advanced)
    parser.add_argument("--interval", type=float, default=None, help=advanced)
    parser.add_argument(
        "--roof-source",
        choices=("sht45", "ds18b20"),
        default=None,
        help=advanced,
    )
    parser.add_argument(
        "--internal-source",
        choices=("sht45", "ds18b20"),
        default=None,
        help=advanced,
    )
    parser.add_argument("--sht45-port", default=None, help=advanced)
    parser.add_argument("--ds18b20-port", default=None, help=advanced)
    parser.add_argument(
        "--heater-on",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=advanced,
    )
    parser.add_argument(
        "--delta-notice-threshold-c",
        type=float,
        default=None,
        help=advanced,
    )
    parser.add_argument(
        "--quiet",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=advanced,
    )
    args = parser.parse_args()

    # Resolve deployment config after parsing so any CLI flag can override the
    # local dome TOML for one-off tests.
    config = load_toml_config(args.config)
    args.host = str(config_value(config, "telemetry", "host", args.host, DEFAULTS["host"]))
    args.port = int(config_value(config, "telemetry", "port", args.port, DEFAULTS["port"]))
    args.device_type = str(
        config_value(config, "telemetry", "device_type", args.device_type, DEFAULTS["device_type"])
    )
    args.device_id = str(config_value(config, "dome", "device_id", args.device_id, DEFAULTS["device_id"]))
    args.interval = float(
        config_value(config, "telemetry", "interval_seconds", args.interval, DEFAULTS["interval"])
    )
    args.roof_source = str(
        config_value(config, "sensors", "roof_source", args.roof_source, DEFAULTS["roof_source"])
    )
    args.internal_source = str(
        config_value(config, "sensors", "internal_source", args.internal_source, DEFAULTS["internal_source"])
    )
    args.sht45_port = clean_optional_string(
        config_value(config, "sensors", "sht45_port", args.sht45_port, DEFAULTS["sht45_port"])
    )
    args.ds18b20_port = clean_optional_string(
        config_value(config, "sensors", "ds18b20_port", args.ds18b20_port, DEFAULTS["ds18b20_port"])
    )
    args.heater_on = bool(config_value(config, "heater", "heater_on", args.heater_on, DEFAULTS["heater_on"]))
    delta_notice_threshold = config_value(
        config,
        "notices",
        "delta_notice_threshold_c",
        args.delta_notice_threshold_c,
        DEFAULTS["delta_notice_threshold_c"],
    )
    args.delta_notice_threshold_c = None if delta_notice_threshold is None else float(delta_notice_threshold)
    args.quiet = bool(config_value(config, "logging", "quiet", args.quiet, DEFAULTS["quiet"]))

    if args.roof_source not in ("sht45", "ds18b20"):
        parser.error("--roof-source/config sensors.roof_source must be 'sht45' or 'ds18b20'")
    if args.internal_source not in ("sht45", "ds18b20"):
        parser.error("--internal-source/config sensors.internal_source must be 'sht45' or 'ds18b20'")
    if args.roof_source == args.internal_source:
        parser.error("--roof-source and --internal-source must be different for delta_temp_c")

    # Print enough startup context that systemd/journal logs show what key this
    # service is maintaining on the head node.
    if args.config:
        print(f"loaded config: {args.config}")
    print(
        f"publishing device_type={args.device_type} device_id={args.device_id} "
        f"to {args.host}:{args.port}"
    )
    print(f"expected Redis key: {expected_redis_key(args.device_type, args.device_id)}")
    if args.delta_notice_threshold_c is not None:
        print(f"heater notice threshold: delta >= {args.delta_notice_threshold_c:.2f} C")
    if args.quiet:
        print("quiet mode: suppressing normal sample lines")

    client = None
    if not args.no_publish:
        from panoseti_grpc.telemetry.client import TelemetryClient

        client = TelemetryClient(host=args.host, port=args.port, verbose=args.verbose)

    sht = SHT45USB(port=args.sht45_port)
    ds = DS1820BUSB(port=args.ds18b20_port)

    last_notice_active = None
    try:
        while True:
            readings = read_sensors(sht, ds)
            payload = build_payload(
                readings,
                roof_source=args.roof_source,
                internal_source=args.internal_source,
                heater_on=args.heater_on,
                delta_notice_threshold_c=args.delta_notice_threshold_c,
            )

            notice_text = ""
            if payload["heater_notice_active"]:
                notice_text = f" notice={payload['heater_notice']}"
            sample_text = (
                f"roof={payload['roof_temp_c']:.2f} C "
                f"internal={payload['internal_temp_c']:.2f} C "
                f"delta={payload['delta_temp_c']:.2f} C "
                f"rh={payload['humidity_percent']:.2f}%"
                f"{notice_text}"
            )
            notice_active = bool(payload["heater_notice_active"])
            if not args.quiet:
                print(sample_text)
            elif last_notice_active is None or notice_active != last_notice_active:
                # In quiet service mode, normal readings are still published to
                # Redis but only notice transitions are written to the journal.
                print(sample_text)
            last_notice_active = notice_active

            if not args.no_publish:
                try:
                    client.log_flexible(args.device_type, args.device_id, payload)
                except Exception as exc:
                    print(f"Telemetry publish failed: {exc}")

            if args.once:
                break
            time.sleep(args.interval)
    finally:
        sht.close()
        ds.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
