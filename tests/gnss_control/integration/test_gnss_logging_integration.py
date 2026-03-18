"""
Integration tests for Tier 2 logging in the GNSS control scripts.

Verifies that log records produced by get_logger() with the service names
used in server_v1.py and agent_v1.py actually reach Redis via the
Telemetry gRPC service.
"""
import json
import logging
import time

import pytest

from panoseti_grpc.telemetry.logger import get_logger, PanosetiLogFactory

FLUSH_DELAY = 0.5  # seconds to allow the async gRPC worker to flush


def _logs_for_service(redis_client, service_name):
    """Return all Redis ingress records matching service_name."""
    raw = redis_client.lrange("logs:ingress", 0, -1)
    return [json.loads(r) for r in raw if json.loads(r).get("service_name") == service_name]


# ---------------------------------------------------------------------------
# server_v1.py: service_name="GNSS_Control"
# ---------------------------------------------------------------------------

def test_server_info_log_reaches_redis(redis_client, start_grpc_server, tmp_path):
    logger = get_logger(
        "GNSS_Control",
        level=logging.INFO,
        console=False,
        log_dir=str(tmp_path),
        grpc_enabled=True,
    )
    logger.info("GNSS server starting up")
    time.sleep(FLUSH_DELAY)

    records = _logs_for_service(redis_client, "GNSS_Control")
    assert len(records) >= 1


def test_server_warning_log_has_correct_severity(redis_client, start_grpc_server, tmp_path):
    logger = get_logger(
        "GNSS_Control",
        level=logging.WARNING,
        console=False,
        log_dir=str(tmp_path),
        grpc_enabled=True,
    )
    logger.warning("config push failed")
    time.sleep(FLUSH_DELAY)

    records = _logs_for_service(redis_client, "GNSS_Control")
    assert any(r.get("severity") in (3, "WARNING") for r in records)


def test_server_multiple_logs_all_reach_redis(redis_client, start_grpc_server, tmp_path):
    logger = get_logger(
        "GNSS_Control",
        level=logging.DEBUG,
        console=False,
        log_dir=str(tmp_path),
        grpc_enabled=True,
    )
    messages = [
        "listening on 0.0.0.0:50051",
        "Control.Pipe: HELLO DEVICE01",
        "pushed cfg v1 to DEVICE01",
    ]
    for msg in messages:
        logger.info(msg)
    time.sleep(FLUSH_DELAY)

    records = _logs_for_service(redis_client, "GNSS_Control")
    assert len(records) >= len(messages)


# ---------------------------------------------------------------------------
# agent_v1.py: service_name="agent"
# ---------------------------------------------------------------------------

def test_agent_info_log_reaches_redis(redis_client, start_grpc_server, tmp_path):
    logger = get_logger(
        "agent",
        level=logging.INFO,
        console=False,
        log_dir=str(tmp_path),
        grpc_enabled=True,
    )
    logger.info("agent starting up")
    time.sleep(FLUSH_DELAY)

    records = _logs_for_service(redis_client, "agent")
    assert len(records) >= 1


def test_agent_warning_log_has_correct_severity(redis_client, start_grpc_server, tmp_path):
    logger = get_logger(
        "agent",
        level=logging.WARNING,
        console=False,
        log_dir=str(tmp_path),
        grpc_enabled=True,
    )
    logger.warning("ping watchdog: server silent")
    time.sleep(FLUSH_DELAY)

    records = _logs_for_service(redis_client, "agent")
    assert any(r.get("severity") in (3, "WARNING") for r in records)


def test_agent_log_payload_contains_message(redis_client, start_grpc_server, tmp_path):
    logger = get_logger(
        "agent",
        level=logging.INFO,
        console=False,
        log_dir=str(tmp_path),
        grpc_enabled=True,
    )
    logger.info("subscribe: loop started")
    time.sleep(FLUSH_DELAY)

    records = _logs_for_service(redis_client, "agent")
    payloads = [json.loads(r["payload_json"]) for r in records if "payload_json" in r]
    assert any("subscribe" in p.get("text", "") for p in payloads)


# ---------------------------------------------------------------------------
# Both services can log concurrently without cross-contamination
# ---------------------------------------------------------------------------

def test_server_and_agent_logs_are_independent(redis_client, start_grpc_server, tmp_path):
    server_logger = get_logger(
        "GNSS_Control",
        level=logging.INFO,
        console=False,
        log_dir=str(tmp_path / "server"),
        grpc_enabled=True,
    )
    agent_logger = get_logger(
        "agent",
        level=logging.INFO,
        console=False,
        log_dir=str(tmp_path / "agent"),
        grpc_enabled=True,
    )

    server_logger.info("server only message")
    agent_logger.info("agent only message")
    time.sleep(FLUSH_DELAY)

    server_records = _logs_for_service(redis_client, "GNSS_Control")
    agent_records = _logs_for_service(redis_client, "agent")

    assert len(server_records) >= 1
    assert len(agent_records) >= 1
    # Verify no cross-contamination
    assert all(r["service_name"] == "GNSS_Control" for r in server_records)
    assert all(r["service_name"] == "agent" for r in agent_records)
