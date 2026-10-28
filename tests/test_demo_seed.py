from fastapi.testclient import TestClient

from fintrack.config import Settings
from fintrack.demo import DEMO_EMAIL, DEMO_PASSWORD
from fintrack.main import create_app


def test_startup_seeds_demo_account_when_enabled() -> None:
    settings = Settings(
        database_url="sqlite://",
        jwt_secret="test-secret-that-is-at-least-32-bytes-long",
        password_hash_iterations=1_000,
        log_level="WARNING",
        seed_demo=True,
    )
    with TestClient(create_app(settings)) as client:
        token = client.post(
            "/api/v1/auth/token", data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD}
        ).json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        assert client.get("/api/v1/transactions", headers=auth).json()["total"] > 300
        assert {b["category"] for b in client.get("/api/v1/budgets", headers=auth).json()} == {
            "Groceries", "Dining", "Shopping"
        }
        tracked = {s["name"] for s in client.get("/api/v1/subscriptions", headers=auth).json()}
        assert tracked == {"Rent", "Spotify"}

        detected = client.post("/api/v1/subscriptions/detect", headers=auth).json()["detected"]
        untracked = {d["merchant"] for d in detected if not d["already_tracked"]}
        assert {"NETFLIX.COM", "ADOBE"} <= untracked
        assert "HULU" not in {d["merchant"] for d in detected}  # cancelled plan is ignored


def test_demo_seed_is_off_by_default(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/token", data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD}
    )
    assert response.status_code == 401
