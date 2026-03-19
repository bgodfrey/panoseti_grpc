"""
E2E test conftest.
Overrides the parent gnss_control conftest's autouse Redis fixtures with
versions that skip (not fail) when Redis is unavailable, so the E2E tests
can run only inside the Docker Compose stack.
"""

import os
import pytest
import redis as redis_lib

REDIS_HOST  = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT  = 6379
REDIS_DB    = 0     # E2E tests use the default (production) DB


@pytest.fixture(scope="session")
def redis_connection():
    r = redis_lib.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True,
    )
    try:
        r.ping()
    except redis_lib.ConnectionError:
        pytest.skip(f"Redis not available at {REDIS_HOST}:{REDIS_PORT}")
    return r


@pytest.fixture(scope="session", autouse=True)
def clean_redis():
    """No-op: E2E tests read from live Redis; no flush needed."""
    yield
