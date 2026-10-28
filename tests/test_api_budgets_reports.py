from fastapi.testclient import TestClient


def spend(client: TestClient, auth: dict[str, str], day: str, amount: str, category: str,
          description: str = "Purchase", kind: str = "expense") -> None:
    body = {"amount": amount, "occurred_on": day, "category": category,
            "description": description, "kind": kind}
    assert client.post("/api/v1/transactions", json=body, headers=auth).status_code == 201


def test_budget_upsert_and_status(client: TestClient, auth: dict[str, str]) -> None:
    put = client.put("/api/v1/budgets", json={"category": "Dining", "monthly_limit": "100.00"},
                     headers=auth)
    assert put.status_code == 200
    # PUT is an upsert: same category replaces the limit instead of duplicating.
    client.put("/api/v1/budgets", json={"category": "dining", "monthly_limit": "200.00"},
               headers=auth)
    client.put("/api/v1/budgets", json={"category": "Groceries", "monthly_limit": "400.00"},
               headers=auth)
    client.put("/api/v1/budgets", json={"category": "Fun", "monthly_limit": "50.00"},
               headers=auth)
    client.put("/api/v1/budgets", json={"category": "Travel", "monthly_limit": "1000.00"},
               headers=auth)
    budgets = client.get("/api/v1/budgets", headers=auth).json()
    assert [(b["category"], b["monthly_limit"]) for b in budgets] == [
        ("Dining", "200.00"), ("Fun", "50.00"), ("Groceries", "400.00"), ("Travel", "1000.00")
    ]

    spend(client, auth, "2026-10-03", "170.00", "Dining")     # 85% -> warning
    spend(client, auth, "2026-10-05", "250.00", "Groceries")  # 62.5%, pace 516.67 -> at_risk
    spend(client, auth, "2026-10-07", "60.00", "Fun")         # 120% -> exceeded
    spend(client, auth, "2026-10-08", "100.00", "Travel")     # 10% -> ok
    spend(client, auth, "2026-09-28", "999.00", "Dining")     # previous month, ignored

    status = client.get("/api/v1/budgets/status", headers=auth).json()  # today = 2026-10-15
    by_cat = {s["category"]: s for s in status}
    assert (by_cat["Dining"]["spent"], by_cat["Dining"]["status"]) == ("170.00", "warning")
    assert by_cat["Groceries"]["projected"] == "516.67"
    assert by_cat["Groceries"]["status"] == "at_risk"
    assert by_cat["Fun"]["status"] == "exceeded"
    assert by_cat["Fun"]["remaining"] == "-10.00"
    assert by_cat["Travel"]["status"] == "ok"
    assert [s["category"] for s in status][0] == "Fun"  # sorted by % used

    september = client.get("/api/v1/budgets/status", params={"month": "2026-09"},
                           headers=auth).json()
    sept_dining = next(s for s in september if s["category"] == "Dining")
    assert sept_dining["status"] == "exceeded"
    assert sept_dining["projected"] == "999.00"

    assert client.get("/api/v1/budgets/status", params={"month": "2026-13"},
                      headers=auth).status_code == 422
    assert client.delete(f"/api/v1/budgets/{budgets[0]['id']}", headers=auth).status_code == 204


def test_monthly_trend_uses_window_function(client: TestClient, auth: dict[str, str]) -> None:
    spend(client, auth, "2026-08-10", "3000.00", "Salary", kind="income")
    spend(client, auth, "2026-08-11", "500.00", "Rent")
    spend(client, auth, "2026-09-11", "800.00", "Rent")
    spend(client, auth, "2026-10-01", "3000.00", "Salary", kind="income")
    spend(client, auth, "2026-10-11", "650.00", "Rent")
    spend(client, auth, "2025-01-01", "5.00", "Old")  # outside the 3-month window

    trend = client.get("/api/v1/reports/monthly-trend", params={"months": 3},
                       headers=auth).json()
    assert trend == [
        {"month": "2026-08", "income": "3000.00", "expenses": "500.00", "net": "2500.00",
         "expense_change": None},
        {"month": "2026-09", "income": "0.00", "expenses": "800.00", "net": "-800.00",
         "expense_change": "300.00"},
        {"month": "2026-10", "income": "3000.00", "expenses": "650.00", "net": "2350.00",
         "expense_change": "-150.00"},
    ]


def test_category_breakdown_and_top_merchants(client: TestClient, auth: dict[str, str]) -> None:
    spend(client, auth, "2026-10-02", "300.00", "Groceries", "Whole Foods")
    spend(client, auth, "2026-10-03", "100.00", "Groceries", "Trader Joes")
    spend(client, auth, "2026-10-04", "100.00", "Dining", "Chipotle")
    body = {"amount": "50.00", "occurred_on": "2026-10-05", "description": "Mystery"}
    client.post("/api/v1/transactions", json=body, headers=auth)
    spend(client, auth, "2026-10-06", "4000.00", "Salary", "Payroll", kind="income")

    breakdown = client.get("/api/v1/reports/category-breakdown", headers=auth).json()
    assert breakdown == [
        {"category": "Groceries", "total": "400.00", "transactions": 2, "percent": 72.73},
        {"category": "Dining", "total": "100.00", "transactions": 1, "percent": 18.18},
        {"category": "Uncategorized", "total": "50.00", "transactions": 1, "percent": 9.09},
    ]

    top = client.get("/api/v1/reports/top-merchants", params={"limit": 3}, headers=auth).json()
    assert [(m["rank"], m["merchant"], m["total"]) for m in top] == [
        (1, "WHOLE FOODS", "300.00"), (2, "CHIPOTLE", "100.00"), (2, "TRADER JOES", "100.00")
    ]

    empty = client.get("/api/v1/reports/category-breakdown",
                       params={"start": "2020-01-01", "end": "2020-01-31"}, headers=auth)
    assert empty.json() == []
