"""
Integration tests for Tier 2 logging in the GNSS control scripts.

Verifies that log records produced by get_logger() with the service names
used in server_v1.py and agent_v1.py actually reach Redis via the
Telemetry gRPC service.

Note: the Telemetry server's schema validator lowercases all service_name
values before storing them (config.py: `return v.lower()`), so Redis records
use "gnss_control" and "agent" regardless of the case passed to get_logger().
"""
import json
import logging
import time

import pytest

from panoseti_grpc.telemetry.logger import get_logger, PanosetiLogFactory

POLL_INTERVAL = 0.1   # seconds between Redis checks
POLL_TIMEOUT  = 10.0  # maximum seconds to wait for a record to appear

# Lowercased names as stored by the server's service_name validator
GNSS_SERVICE = "gnss_control"
AGENT_SERVICE = "agent"


def _wait_for_logs(redis_client, service_name, since=0, count=1):
    """
    Poll Redis for records matching service_name at list indices >= since,
    returning as soon as count records are found or POLL_TIMEOUT elapses.

    Using `since` (a snapshot of the list length taken before emitting the
    log) ensures we only see records added by the current test, not stale
    records left over from earlier tests.
    """
    deadline = time.monotonic() + POLL_TIMEOUT
    while time.monotonic() < deadline:
        raw = redis_client.lrange("logs:ingress", since, -1)
        records = [json.loads(r) for r in raw
                   if json.loads(r).get("service_name") == service_name]
        if len(records) >= count:
            return records
        time.sleep(POLL_INTERVAL)
    return []


# ---------------------------------------------------------------------------
# server_v1.py: service_name="GNSS_Control" → stored as "gnss_control"
# ---------------------------------------------------------------------------

def test_server_info_log_reaches_redis(redis_client, start_grpc_server, tmp_path):
    snapshot = redis_client.llen("logs:ingress")
    logger = get_logger(
        "GNSS_Control",
        level=logging.INFO,
        console=False,
        log_dir=str(tmp_path),
        grpc_enabled=True,
    )
    logger.info("GNSS server starting up")

    records = _wait_for_logs(redis_client, GNSS_SERVICE, since=snapshot)
    assert len(records) >= 1


def test_server_warning_log_has_correct_severity(redis_client, start_grpc_server, tmp_path):
    snapshot = redis_client.llen("logs:ingress")
    logger = get_logger(
        "GNSS_Control",
        level=logging.WARNING,
        console=False,
        log_dir=str(tmp_path),
        grpc_enabled=True,
    )
    logger.warning("config push failed")

    records = _wait_for_logs(redis_client, GNSS_SERVICE, since=snapshot)
    assert any(r.get("severity") in (3, "WARNING") for r in records)


def test_server_multiple_logs_all_reach_redis(redis_client, start_grpc_server, tmp_path):
    snapshot = redis_client.llen("logs:ingress")
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

    records = _wait_for_logs(redis_client, GNSS_SERVICE, since=snapshot, count=len(messages))
    assert len(records) >= len(messages)


# ---------------------------------------------------------------------------
# agent_v1.py: service_name="agent" → stored as "agent"
# ---------------------------------------------------------------------------

def test_agent_info_log_reaches_redis(redis_client, start_grpc_server, tmp_path):
    snapshot = redis_client.llen("logs:ingress")
    logger = get_logger(
        "agent",
        level=logging.INFO,
        console=False,
        log_dir=str(tmp_path),
        grpc_enabled=True,
    )
    logger.info("agent starting up")

    records = _wait_for_logs(redis_client, AGENT_SERVICE, since=snapshot)
    assert len(records) >= 1


def test_agent_warning_log_has_correct_severity(redis_client, start_grpc_server, tmp_path):
    snapshot = redis_client.llen("logs:ingress")
    logger = get_logger(
        "agent",
        level=logging.WARNING,
        console=False,
        log_dir=str(tmp_path),
        grpc_enabled=True,
    )
    logger.warning("ping watchdog: server silent")

    records = _wait_for_logs(redis_client, AGENT_SERVICE, since=snapshot)
    assert any(r.get("severity") in (3, "WARNING") for r in records)


def test_agent_log_payload_contains_message(redis_client, start_grpc_server, tmp_path):
    snapshot = redis_client.llen("logs:ingress")
    logger = get_logger(
        "agent",
        level=logging.INFO,
        console=False,
        log_dir=str(tmp_path),
        grpc_enabled=True,
    )
    logger.info("subscribe: loop started")

    records = _wait_for_logs(redis_client, AGENT_SERVICE, since=snapshot)
    payloads = [json.loads(r["payload_json"]) for r in records if "payload_json" in r]
    assert any("subscribe" in p.get("text", "") for p in payloads)


# ---------------------------------------------------------------------------
# Both services can log concurrently without cross-contamination
# ---------------------------------------------------------------------------

def test_server_and_agent_logs_are_independent(redis_client, start_grpc_server, tmp_path):
    snapshot = redis_client.llen("logs:ingress")
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

    server_records = _wait_for_logs(redis_client, GNSS_SERVICE, since=snapshot)
    agent_records  = _wait_for_logs(redis_client, AGENT_SERVICE, since=snapshot)

    assert len(server_records) >= 1
    assert len(agent_records) >= 1
    assert all(r["service_name"] == GNSS_SERVICE for r in server_records)
    assert all(r["service_name"] == AGENT_SERVICE for r in agent_records)
