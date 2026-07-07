#!/usr/bin/env python3
"""Send one test dome-environment packet to the PANOSETI Telemetry service."""

from __future__ import annotations

import argparse
import time

from panoseti_grpc.telemetry.client import TelemetryClient


def build_payload() -> dict[str, int | float | str | bool | None]:
    roof_temp_c = 12.4
    internal_temp_c = 14.9
    delta_temp_c = abs(roof_temp_c - internal_temp_c)

    return {
        "roof_temp_c": roof_temp_c,
        "internal_temp_c": internal_temp_c,
        "delta_temp_c": delta_temp_c,
        "humidity_percent": 48.2,
        "heater_mode": "dry_run",
        "heater_on": False,
        "decision": "local_smoke_test",
        "roof_sensor_ok": True,
        "internal_sensor_ok": True,
        "humidity_sensor_ok": True,
        "client_unix_time": time.time(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost", help="Telemetry server host")
    parser.add_argument("--port", type=int, default=50051, help="Telemetry server gRPC port")
    parser.add_argument("--device-type", default="example", help="Telemetry device type")
    parser.add_argument("--device-id", default="dome_test", help="Telemetry device id")
    args = parser.parse_args()

    payload = build_payload()
    client = TelemetryClient(host=args.host, port=args.port, verbose=True)
    client.log_flexible(args.device_type, args.device_id, payload)

    print(f"Sent {args.device_type}/{args.device_id} to {args.host}:{args.port}")
    if args.device_type == "example":
        print(f"Expected Redis key: DEV_EXAMPLE_{args.device_id}")
    else:
        print(f"Expected Redis key for unregistered type: SANDBOX:{args.device_type}:{args.device_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
