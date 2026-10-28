from fastapi.testclient import TestClient

URL = "/api/v1/subscriptions"


def add(client: TestClient, auth: dict[str, str], **fields: object) -> dict:
    body = {"name": "Netflix", "amount": "15.49", "next_renewal": "2026-10-20"} | fields
    response = client.post(URL, json=body, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


def test_crud(client: TestClient, auth: dict[str, str]) -> None:
    sub = add(client, auth, category="Streaming")
    assert sub["merchant"] == "NETFLIX"
    assert sub["monthly_cost"] == "15.49"
    assert sub["status"] == "active"
    assert sub["auto_detected"] is False

    patched = client.patch(
        f"{URL}/{sub['id']}", json={"amount": "17.99", "status": "paused"}, headers=auth
    ).json()
    assert patched["amount"] == "17.99"
    assert patched["status"] == "paused"

    active = client.get(URL, params={"status": "active"}, headers=auth).json()
    assert active == []
    assert client.delete(f"{URL}/{sub['id']}", headers=auth).status_code == 204
    assert client.get(f"{URL}/{sub['id']}", headers=auth).status_code == 404


def test_upcoming_includes_repeats_and_rolls_stale_dates_forward(
    client: TestClient, auth: dict[str, str]
) -> None:
    add(client, auth, name="Netflix", next_renewal="2026-10-20")
    add(client, auth, name="Gym", amount="10.00", billing_cycle="weekly",
        next_renewal="2026-10-01")  # stale: Oct 1 + 2 weeks lands on today, Oct 15
    add(client, auth, name="Domain", amount="12.00", billing_cycle="yearly",
        next_renewal="2027-06-01")  # outside the window
    old = add(client, auth, name="Old", next_renewal="2026-10-16")
    client.patch(f"{URL}/{old['id']}", json={"status": "cancelled"}, headers=auth)

    upcoming = client.get(f"{URL}/upcoming", params={"days": 14}, headers=auth).json()
    assert [(r["name"], r["renews_on"], r["days_until"]) for r in upcoming["renewals"]] == [
        ("Gym", "2026-10-15", 0),
        ("Netflix", "2026-10-20", 5),
        ("Gym", "2026-10-22", 7),
        ("Gym", "2026-10-29", 14),
    ]
    assert upcoming["total_due"] == "45.49"


def test_summary_normalises_cycles_to_monthly(client: TestClient, auth: dict[str, str]) -> None:
    add(client, auth, name="Netflix", amount="15.00")
    add(client, auth, name="Prime", amount="120.00", billing_cycle="yearly")
    add(client, auth, name="Insurance", amount="90.00", billing_cycle="quarterly")
    summary = client.get(f"{URL}/summary", headers=auth).json()
    assert summary["active_count"] == 3
    assert summary["monthly_total"] == "55.00"  # 15 + 10 + 30
    assert summary["annual_total"] == "660.00"
    assert summary["by_cycle"] == {"monthly": 1, "yearly": 1, "quarterly": 1}
    assert summary["most_expensive"]["name"] == "Insurance"


def test_detect_from_transactions(client: TestClient, auth: dict[str, str]) -> None:
    rows = ["date,description,amount"]
    for month in range(4, 11):
        price = "-15.49" if month < 10 else "-17.99"
        rows.append(f"2026-{month:02d}-03,NETFLIX.COM 866-579-7172,{price}")
        # Groceries twice a month: frequent but not a subscription.
        rows.append(f"2026-{month:02d}-02,WHOLE FOODS #{month},-{month * 13}.50")
        rows.append(f"2026-{month:02d}-17,WHOLE FOODS #{month},-{month * 7}.25")
    for month in range(5, 11):
        rows.append(f"2026-{month:02d}-12,SPOTIFY USA*P{month}X,-10.99")
    files = {"file": ("s.csv", "\n".join(rows).encode(), "text/csv")}
    client.post("/api/v1/transactions/import", files=files, headers=auth)
    add(client, auth, name="Spotify", merchant="Spotify USA", amount="10.99")

    preview = client.post(f"{URL}/detect", headers=auth).json()
    assert preview["created"] == 0
    by_merchant = {d["merchant"]: d for d in preview["detected"]}
    assert set(by_merchant) == {"NETFLIX.COM", "SPOTIFY USA"}
    netflix = by_merchant["NETFLIX.COM"]
    assert netflix["billing_cycle"] == "monthly"
    assert netflix["amount"] == "17.99"
    assert netflix["price_change"] == "2.50"
    assert netflix["next_renewal"] == "2026-11-03"
    assert netflix["already_tracked"] is False
    assert by_merchant["SPOTIFY USA"]["already_tracked"] is True

    applied = client.post(f"{URL}/detect", params={"apply": True}, headers=auth).json()
    assert applied["created"] == 1
    again = client.post(f"{URL}/detect", params={"apply": True}, headers=auth).json()
    assert again["created"] == 0  # idempotent

    tracked = client.get(URL, headers=auth).json()
    auto = next(s for s in tracked if s["auto_detected"])
    assert auto["name"] == "Netflix.Com"
    assert auto["amount"] == "17.99"
