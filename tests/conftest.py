from collections.abc import Callable, Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from fintrack.config import Settings
from fintrack.deps import get_today
from fintrack.main import create_app

TODAY = date(2026, 10, 15)


@pytest.fixture
def client() -> Iterator[TestClient]:
    settings = Settings(
        database_url="sqlite://",  # fresh in-memory database per test
        jwt_secret="test-secret-that-is-at-least-32-bytes-long",
        password_hash_iterations=1_000,  # keep the suite fast; production uses 600k
        log_level="WARNING",
    )
    app = create_app(settings)
    app.dependency_overrides[get_today] = lambda: TODAY
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def register(client: TestClient) -> Callable[[str], dict[str, str]]:
    """Registers a user and returns auth headers for them."""

    def _register(email: str = "alice@example.com") -> dict[str, str]:
        password = "correct-horse-battery"
        assert client.post(
            "/api/v1/auth/register", json={"email": email, "password": password}
        ).status_code == 201
        token = client.post(
            "/api/v1/auth/token", data={"username": email, "password": password}
        ).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _register


@pytest.fixture
def auth(register: Callable[[str], dict[str, str]]) -> dict[str, str]:
    return register("alice@example.com")
