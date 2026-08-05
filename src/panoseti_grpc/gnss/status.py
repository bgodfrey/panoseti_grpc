"""PANOSETI latest-status publisher for the U-Blox F9T runtime."""

from __future__ import annotations

from typing import Any

from ublox_f9t.status import PublisherConfig

from panoseti_grpc.telemetry.client import TelemetryClient


def _split_endpoint(endpoint: str) -> tuple[str, int]:
    host, separator, port = endpoint.rpartition(":")
    if not separator or not host:
        raise ValueError(f"invalid PANOSETI telemetry endpoint {endpoint!r}; expected host:port")
    return host, int(port)


def _payload(alias: str, record: dict[str, Any]) -> dict[str, Any]:
    extra_data = {
        "alias": alias,
        "unix_ms": int(record.get("unix_ms", 0)),
        "temp_c": float(record.get("temp_c", 0.0)),
        "qerr_ns": record.get("qerr_ns"),
        "qerr_valid": bool(record.get("qerr_valid", False)),
        "qerr_age_ms": int(record.get("qerr_age_ms", 0) or 0),
        "nav_sat_valid": bool(record.get("nav_sat_valid", False)),
        "nav_sat_age_ms": int(record.get("nav_sat_age_ms", 0) or 0),
        "telemetry_stale": bool(record.get("telemetry_stale", False)),
        "utc_ok": bool(record.get("utc_ok", False)),
        "num_vis": int(record.get("num_vis", 0)),
        "num_used": int(record.get("num_used", 0)),
        "gps_used": int(record.get("gps_used", 0)),
        "gal_used": int(record.get("gal_used", 0)),
        "bds_used": int(record.get("bds_used", 0)),
        "glo_used": int(record.get("glo_used", 0)),
        "avg_cno": float(record.get("avg_cno", 0.0)),
        "pdop": float(record.get("pdop", 0.0)),
    }
    return {
        "satellites": int(record.get("num_vis", 0)),
        "lat": 0.0,
        "lon": 0.0,
        "fix_mode": "3D" if record.get("utc_ok") else "none",
        "extra_data": {key: value for key, value in extra_data.items() if value is not None},
    }


class PanosetiStatusPublisher:
    """Publish GNSS latest status through the PANOSETI Telemetry service."""

    def __init__(self, config: PublisherConfig) -> None:
        host, port = _split_endpoint(config.endpoint)
        self.device_type = config.device_type
        self.client = TelemetryClient(host=host, port=port)

    def publish(self, device_id: str, alias: str, record: dict[str, Any]) -> None:
        self.client.log_strict(self.device_type, device_id, _payload(alias, record))

    def close(self) -> None:
        self.client.channel.close()


def create_publisher(config: PublisherConfig) -> PanosetiStatusPublisher:
    """Entry-point factory discovered by ``ublox_f9t.status``."""

    return PanosetiStatusPublisher(config)
