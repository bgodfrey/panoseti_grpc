"""
Unit-test conftest: override the parent's session-scoped `clean_redis` and
`redis_connection` fixtures with no-ops so unit tests run without a Redis
instance or gRPC server.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def clean_redis():
    """No-op override: unit tests don't need Redis."""
    yield


@pytest.fixture(scope="session")
def redis_connection():
    """No-op override: unit tests don't need Redis."""
    return None
