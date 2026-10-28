from fastapi.testclient import TestClient

URL = "/api/v1/reports/dashboard"


def post(client: TestClient, auth: dict[str, str], path: str, body: dict) -> None:
    response = client.post(f"/api/v1/{path}", json=body, headers=auth)
    assert response.status_code == 201, response.text


def test_dashboard_combines_monthly_figures(client: TestClient, auth: dict[str, str]) -> None:
    txn = {"occurred_on": "2026-10-01"}
    post(client, auth, "transactions", txn | {"kind": "income", "amount": "4000.00",
                                              "description": "Payroll", "category": "Salary"})
    post(client, auth, "transactions", txn | {"amount": "1500.00", "description": "Rent",
                                              "category": "Housing"})
    post(client, auth, "transactions", txn | {"amount": "500.00", "description": "Whole Foods",
                                              "category": "Groceries"})
    post(client, auth, "transactions", {"occurred_on": "2026-09-30", "amount": "999.00",
                                        "description": "Last month"})
    client.put("/api/v1/budgets", json={"category": "Groceries", "monthly_limit": "450.00"},
               headers=auth)
    post(client, auth, "subscriptions", {"name": "Netflix", "amount": "15.49",
                                         "next_renewal": "2026-10-20"})

    dash = client.get(URL, headers=auth).json()  # today = 2026-10-15

    assert dash["month"] == "2026-10"
    assert (dash["income"], dash["expenses"], dash["balance"]) == ("4000.00", "2000.00", "2000.00")
    assert dash["savings_rate"] == 50.0
    assert dash["subscriptions_monthly"] == "15.49"
    assert [(c["category"], c["total"]) for c in dash["categories"]] == [
        ("Housing", "1500.00"), ("Groceries", "500.00")
    ]
    assert dash["budgets"][0]["category"] == "Groceries"
    assert dash["budgets"][0]["status"] == "exceeded"
    assert [r["name"] for r in dash["upcoming_bills"]["renewals"]] == ["Netflix"]


def test_dashboard_for_empty_month(client: TestClient, auth: dict[str, str]) -> None:
    dash = client.get(URL, params={"month": "2026-01"}, headers=auth).json()
    assert (dash["income"], dash["expenses"], dash["balance"]) == ("0.00", "0.00", "0.00")
    assert dash["savings_rate"] is None
    assert dash["categories"] == []


def test_dashboard_rejects_bad_month(client: TestClient, auth: dict[str, str]) -> None:
    assert client.get(URL, params={"month": "2026-1"}, headers=auth).status_code == 422


def test_dashboard_page_is_served(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "/static/app.js" in page.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200
