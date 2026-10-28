from fastapi.testclient import TestClient


def test_register_login_and_me(client: TestClient) -> None:
    created = client.post(
        "/api/v1/auth/register", json={"email": "Bob@Example.com", "password": "password123"}
    )
    assert created.status_code == 201
    assert created.json()["email"] == "bob@example.com"
    assert "hashed_password" not in created.json()

    token = client.post(
        "/api/v1/auth/token", data={"username": "bob@example.com", "password": "password123"}
    ).json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "bob@example.com"


def test_duplicate_email_is_conflict(client: TestClient) -> None:
    body = {"email": "dup@example.com", "password": "password123"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 201
    assert client.post("/api/v1/auth/register", json=body).status_code == 409


def test_validation_errors(client: TestClient) -> None:
    short = client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "x"})
    assert short.status_code == 422
    bad_email = client.post(
        "/api/v1/auth/register", json={"email": "not-an-email", "password": "password123"}
    )
    assert bad_email.status_code == 422


def test_wrong_password_rejected(client: TestClient, auth: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/auth/token", data={"username": "alice@example.com", "password": "nope-nope"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


def test_protected_routes_require_valid_token(client: TestClient) -> None:
    assert client.get("/api/v1/transactions").status_code == 401
    bad = client.get("/api/v1/transactions", headers={"Authorization": "Bearer forged.token.x"})
    assert bad.status_code == 401


def test_health_and_request_id(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "trace-123"})
    assert response.json() == {"status": "ok", "database": "ok"}
    assert response.headers["X-Request-ID"] == "trace-123"
