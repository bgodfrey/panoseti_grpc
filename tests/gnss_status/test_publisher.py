"""Unit tests for the PANOSETI U-Blox status-publisher plugin."""

from __future__ import annotations

from unittest.mock import Mock, patch

from ublox_f9t.status import PublisherConfig

from panoseti_grpc.gnss.status import PanosetiStatusPublisher, _payload


def test_payload_maps_gnss_status() -> None:
    payload = _payload(
        "PTI",
        {
            "unix_ms": 123,
            "num_vis": 8,
            "num_used": 5,
            "utc_ok": True,
            "qerr_ns": 2.5,
        },
    )

    assert payload["satellites"] == 8
    assert payload["fix_mode"] == "3D"
    assert payload["extra_data"]["alias"] == "PTI"
    assert payload["extra_data"]["qerr_ns"] == 2.5


def test_publisher_uses_telemetry_client() -> None:
    client = Mock()
    with patch("panoseti_grpc.gnss.status.TelemetryClient", return_value=client) as client_type:
        publisher = PanosetiStatusPublisher(PublisherConfig(endpoint="headnode:50051"))
        publisher.publish("receiver-1", "PTI", {"num_vis": 4, "utc_ok": True})
        publisher.close()

    client_type.assert_called_once_with(host="headnode", port=50051)
    client.log_strict.assert_called_once()
    client.channel.close.assert_called_once_with()
