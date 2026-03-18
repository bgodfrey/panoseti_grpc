"""
Unit tests for Tier 2 logging setup in the GNSS control scripts.

These tests verify that get_logger() initialises correctly for the service
names used by server_v1.py ("GNSS_Control") and agent_v1.py ("agent") without
requiring a running Telemetry Service or serial hardware.
"""
import logging
from logging.handlers import RotatingFileHandler

import pytest
from rich.logging import RichHandler

from panoseti_grpc.telemetry.client import AsyncGrpcHandler
from panoseti_grpc.telemetry.logger import get_logger


# ---------------------------------------------------------------------------
# server_v1.py logger  (service_name="GNSS_Control")
# ---------------------------------------------------------------------------

def test_server_logger_has_console_and_file_handlers(tmp_path):
    logger = get_logger(
        "GNSS_Control",
        level=logging.INFO,
        console=True,
        log_dir=str(tmp_path),
        grpc_enabled=False,
    )
    handler_types = {type(h) for h in logger.handlers}
    assert RichHandler in handler_types
    assert RotatingFileHandler in handler_types
    assert AsyncGrpcHandler not in handler_types


def test_server_logger_level_respected(tmp_path):
    logger = get_logger(
        "GNSS_Control",
        level=logging.WARNING,
        console=True,
        log_dir=str(tmp_path),
        grpc_enabled=False,
    )
    assert logger.level == logging.WARNING


def test_server_logger_writes_to_file(tmp_path):
    logger = get_logger(
        "GNSS_Control",
        level=logging.INFO,
        console=False,
        log_dir=str(tmp_path),
        grpc_enabled=False,
    )
    logger.info("server startup test")
    log_file = tmp_path / "GNSS_Control.log"
    assert log_file.exists()
    assert "server startup test" in log_file.read_text()


def test_server_logger_grpc_enabled_does_not_raise(tmp_path):
    """grpc_enabled=True must not raise even when the Telemetry Service is unreachable."""
    logger = get_logger(
        "GNSS_Control",
        level=logging.INFO,
        console=False,
        log_dir=str(tmp_path),
        grpc_enabled=True,
    )
    logger.info("probe message")  # must not raise


# ---------------------------------------------------------------------------
# agent_v1.py logger  (service_name="agent")
# ---------------------------------------------------------------------------

def test_agent_logger_has_console_and_file_handlers(tmp_path):
    logger = get_logger(
        "agent",
        level=logging.DEBUG,
        console=True,
        log_dir=str(tmp_path),
        grpc_enabled=False,
    )
    handler_types = {type(h) for h in logger.handlers}
    assert RichHandler in handler_types
    assert RotatingFileHandler in handler_types
    assert AsyncGrpcHandler not in handler_types


def test_agent_logger_level_respected(tmp_path):
    logger = get_logger(
        "agent",
        level=logging.DEBUG,
        console=False,
        log_dir=str(tmp_path),
        grpc_enabled=False,
    )
    assert logger.level == logging.DEBUG


def test_agent_logger_writes_to_file(tmp_path):
    logger = get_logger(
        "agent",
        level=logging.INFO,
        console=False,
        log_dir=str(tmp_path),
        grpc_enabled=False,
    )
    logger.warning("watchdog triggered")
    log_file = tmp_path / "agent.log"
    assert log_file.exists()
    assert "watchdog triggered" in log_file.read_text()


def test_agent_logger_grpc_enabled_does_not_raise(tmp_path):
    logger = get_logger(
        "agent",
        level=logging.DEBUG,
        console=False,
        log_dir=str(tmp_path),
        grpc_enabled=True,
    )
    logger.debug("probe message")  # must not raise


# ---------------------------------------------------------------------------
# Verbosity mapping (mirrors the _LEVELS dict in both scripts)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("verbosity,expected_level", [
    (0, logging.ERROR),
    (1, logging.WARNING),
    (2, logging.INFO),
    (3, logging.DEBUG),
])
def test_verbosity_to_level_mapping(verbosity, expected_level, tmp_path):
    _LEVELS = {0: logging.ERROR, 1: logging.WARNING, 2: logging.INFO, 3: logging.DEBUG}
    level = _LEVELS.get(max(0, min(verbosity, 3)), logging.INFO)
    logger = get_logger(
        "GNSS_Control",
        level=level,
        console=False,
        grpc_enabled=False,
    )
    assert logger.level == expected_level
