import pytest
import redis
import time
import os
import multiprocessing
import socket
import asyncio
from panoseti_grpc.telemetry.client import TelemetryClient
from panoseti_grpc.telemetry.server import serve
from panoseti_grpc.telemetry.logger import PanosetiLogFactory

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
SERVER_PORT = 50051
MAX_GRPC_SERVER_STARTUP_DELAY = 30
TEST_DB_INDEX = 1


@pytest.fixture(autouse=True)
def reset_log_factory():
    PanosetiLogFactory.reset_clients()
    yield
    PanosetiLogFactory.reset_clients()


@pytest.fixture(scope="session")
def redis_connection():
    r = redis.Redis(host=REDIS_HOST, port=6379, db=TEST_DB_INDEX, decode_responses=True)
    try:
        r.ping()
    except redis.ConnectionError:
        pytest.fail(f"Could not connect to Redis at {REDIS_HOST}")
    return r


@pytest.fixture(scope="session")
def redis_client(redis_connection):
    yield redis_connection


@pytest.fixture(scope="session", autouse=True)
def clean_redis(redis_connection):
    redis_connection.flushdb()
    yield


def _run_server_process(redis_host, port):
    asyncio.run(serve(redis_host=redis_host, port=port, redis_db=TEST_DB_INDEX))


@pytest.fixture(scope="session")
def start_grpc_server():
    proc = multiprocessing.Process(
        target=_run_server_process,
        args=(REDIS_HOST, SERVER_PORT),
        daemon=True,
    )
    proc.start()

    start_time = time.time()
    server_ready = False
    while time.time() - start_time < MAX_GRPC_SERVER_STARTUP_DELAY:
        if not proc.is_alive():
            raise RuntimeError("Server process died!")
        try:
            with socket.create_connection(("localhost", SERVER_PORT), timeout=0.1):
                server_ready = True
                break
        except (OSError, ConnectionRefusedError):
            time.sleep(0.1)

    if not server_ready:
        proc.terminate()
        raise TimeoutError("Server failed to bind port")

    yield

    proc.terminate()
    proc.join(timeout=2)
    if proc.is_alive():
        proc.kill()


@pytest.fixture(scope="function")
def grpc_client(start_grpc_server):
    return TelemetryClient(host="localhost", port=SERVER_PORT)
