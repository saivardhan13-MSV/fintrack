from collections.abc import Callable

from fastapi.testclient import TestClient

URL = "/api/v1/transactions"


def add(client: TestClient, auth: dict[str, str], **fields: object) -> dict:
    body = {"amount": "10.00", "occurred_on": "2026-10-01", "description": "Coffee"} | fields
    response = client.post(URL, json=body, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


def upload(client: TestClient, auth: dict[str, str], csv_text: str) -> dict:
    files = {"file": ("statement.csv", csv_text.encode(), "text/csv")}
    response = client.post(f"{URL}/import", files=files, headers=auth)
    assert response.status_code == 200, response.text
    return response.json()


def test_create_and_get_transaction(client: TestClient, auth: dict[str, str]) -> None:
    txn = add(client, auth, amount="15.49", description="NETFLIX.COM 866-579", category="Streaming")
    assert txn["amount"] == "15.49"
    assert txn["merchant"] == "NETFLIX.COM"
    assert txn["category"] == "Streaming"
    assert txn["kind"] == "expense"
    assert client.get(f"{URL}/{txn['id']}", headers=auth).json() == txn


def test_amount_validation(client: TestClient, auth: dict[str, str]) -> None:
    for bad in ("0", "-5", "1.234"):
        body = {"amount": bad, "occurred_on": "2026-10-01"}
        assert client.post(URL, json=body, headers=auth).status_code == 422


def test_list_filters_and_pagination(client: TestClient, auth: dict[str, str]) -> None:
    for day in range(1, 6):
        add(client, auth, occurred_on=f"2026-10-0{day}", description=f"Store {day}")
    add(client, auth, kind="income", amount="3000.00", description="Payroll")

    page = client.get(URL, params={"limit": 2, "offset": 0, "kind": "expense"}, headers=auth).json()
    assert page["total"] == 5
    assert [t["occurred_on"] for t in page["items"]] == ["2026-10-05", "2026-10-04"]

    ranged = client.get(URL, params={"start": "2026-10-02", "end": "2026-10-03"}, headers=auth)
    assert ranged.json()["total"] == 2

    by_merchant = client.get(URL, params={"merchant": "payroll"}, headers=auth).json()
    assert by_merchant["total"] == 1
    assert by_merchant["items"][0]["amount"] == "3000.00"

    bad_range = client.get(URL, params={"start": "2026-10-05", "end": "2026-10-01"}, headers=auth)
    assert bad_range.status_code == 400


def test_update_and_delete(client: TestClient, auth: dict[str, str]) -> None:
    txn = add(client, auth)
    patched = client.patch(
        f"{URL}/{txn['id']}", json={"amount": "12.25", "category": "Dining"}, headers=auth
    ).json()
    assert patched["amount"] == "12.25"
    assert patched["category"] == "Dining"

    cleared = client.patch(f"{URL}/{txn['id']}", json={"category": None}, headers=auth).json()
    assert cleared["category"] is None

    assert client.delete(f"{URL}/{txn['id']}", headers=auth).status_code == 204
    assert client.get(f"{URL}/{txn['id']}", headers=auth).status_code == 404


def test_users_cannot_see_each_others_data(
    client: TestClient, auth: dict[str, str], register: Callable[[str], dict[str, str]]
) -> None:
    txn = add(client, auth)
    mallory = register("mallory@example.com")
    assert client.get(f"{URL}/{txn['id']}", headers=mallory).status_code == 404
    assert client.delete(f"{URL}/{txn['id']}", headers=mallory).status_code == 404
    assert client.get(URL, headers=mallory).json()["total"] == 0


CSV = """Date,Description,Amount,Category
2026-10-01,PAYROLL ACME CORP,"3,200.00",Salary
2026-10-02,POS WHOLE FOODS #123,-84.20,Groceries
2026-10-02,POS WHOLE FOODS #123,-84.20,Groceries
10/03/2026,SPOTIFY USA*P2A9F1,($10.99),Streaming
2026-10-04,BROKEN ROW,abc,
not-a-date,SOMETHING,-1.00,
2026-10-05,,-1.00,
"""


def test_csv_import_is_idempotent_and_reports_bad_rows(
    client: TestClient, auth: dict[str, str]
) -> None:
    first = upload(client, auth, CSV)
    assert first["imported"] == 4  # both identical Whole Foods rows are kept
    assert first["duplicates_skipped"] == 0
    assert [e["row"] for e in first["errors"]] == [6, 7, 8]

    second = upload(client, auth, CSV)
    assert second["imported"] == 0
    assert second["duplicates_skipped"] == 4

    items = client.get(URL, headers=auth).json()["items"]
    spotify = next(t for t in items if t["merchant"] == "SPOTIFY USA")
    assert spotify == spotify | {"amount": "10.99", "kind": "expense", "category": "Streaming"}
    payroll = next(t for t in items if t["merchant"] == "PAYROLL ACME CORP")
    assert payroll["kind"] == "income"
    assert payroll["amount"] == "3200.00"


def test_csv_import_rejects_missing_columns(client: TestClient, auth: dict[str, str]) -> None:
    files = {"file": ("x.csv", b"when,what\n2026-10-01,thing\n", "text/csv")}
    response = client.post(f"{URL}/import", files=files, headers=auth)
    assert response.status_code == 400
    assert "amount" in response.json()["detail"]


def test_categories_endpoint(client: TestClient, auth: dict[str, str]) -> None:
    created = client.post("/api/v1/categories", json={"name": "Travel"}, headers=auth)
    assert created.status_code == 201
    dup = client.post("/api/v1/categories", json={"name": "travel"}, headers=auth)
    assert dup.status_code == 409
    add(client, auth, category="TRAVEL")  # case-insensitive match reuses the category
    names = [c["name"] for c in client.get("/api/v1/categories", headers=auth).json()]
    assert names == ["Travel"]
