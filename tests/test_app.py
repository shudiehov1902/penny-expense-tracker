import csv
import io
import json
import re
from datetime import date

import pytest

from tracker import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite3"), "LEGACY_FILE": None})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth(client):
    html = client.get("/").text
    token = re.search(r'name="penny-token" content="([^"]+)"', html).group(1)
    return {"X-Penny-Token": token}


def expense(**changes):
    return {"category": "Food", "amount": "12.50", "spent_on": "2026-11-15", "note": "Lunch", **changes}


def test_expense_lifecycle_and_persistence(app, client, auth):
    created = client.post("/api/expenses", json=expense(), headers=auth)
    assert created.status_code == 201
    expense_id = created.json["id"]
    assert client.get("/api/overview?month=2026-11").json["total_cents"] == 1250
    changed = client.put(f"/api/expenses/{expense_id}", json=expense(amount="14.20", category="  Groceries  "), headers=auth)
    assert changed.status_code == 200
    reopened = create_app({"TESTING": True, "DATABASE": app.config["DATABASE"], "LEGACY_FILE": None}).test_client()
    saved = reopened.get("/api/overview?month=2026-11").json["expenses"][0]
    assert saved["amount_cents"] == 1420
    assert saved["category"] == "Groceries"
    assert client.delete(f"/api/expenses/{expense_id}", headers=auth).status_code == 200
    assert client.get("/api/overview?month=2026-11").json["expenses"] == []
    assert client.delete(f"/api/expenses/{expense_id}", headers=auth).status_code == 404


@pytest.mark.parametrize("changes", [
    {"amount": "0"}, {"amount": "-1"}, {"amount": "0.001"},
    {"amount": "hello"}, {"amount": "NaN"}, {"amount": "Infinity"},
    {"amount": True}, {"amount": "10000000"}, {"amount": None},
    {"category": "   "}, {"category": []}, {"category": "x" * 61},
    {"spent_on": "2026-02-30"}, {"spent_on": None},
    {"note": "x" * 241}, {"note": 42},
])
def test_invalid_expenses_do_not_write(client, auth, changes):
    response = client.post("/api/expenses", json=expense(**changes), headers=auth)
    assert response.status_code == 400
    assert response.json["error"]
    assert client.get("/api/overview?month=2026-11").json["expenses"] == []


def test_month_isolation_and_exact_cents(client, auth):
    for amount in ["0.10", "0.20"]:
        assert client.post("/api/expenses", json=expense(amount=amount), headers=auth).status_code == 201
    client.post("/api/expenses", json=expense(amount="99", spent_on="2026-10-01"), headers=auth)
    data = client.get("/api/overview?month=2026-11").json
    assert data["total_cents"] == 30
    assert data["breakdown"] == [{"category": "Food", "amount_cents": 30}]
    assert data["daily"] == [{"date": "2026-11-15", "amount_cents": 30}]
    assert len(data["expenses"]) == 2
    assert client.get("/api/overview?month=2026-12").json["total_cents"] == 0


def test_budgets_are_month_specific(client, auth):
    assert client.put("/api/budget", json={"month": "2026-11", "amount": "400.50"}, headers=auth).status_code == 200
    assert client.get("/api/overview?month=2026-11").json["budget_cents"] == 40050
    assert client.get("/api/overview?month=2026-10").json["budget_cents"] is None
    assert client.put("/api/budget", json={"month": "2026-11", "amount": "0"}, headers=auth).status_code == 400
    assert client.put("/api/budget", json={"month": "2026-11", "amount": None}, headers=auth).status_code == 200
    assert client.get("/api/overview?month=2026-11").json["budget_cents"] is None


def test_local_write_protection(client):
    assert client.post("/api/expenses", json=expense()).status_code == 403
    assert client.put("/api/budget", json={"month": "2026-11", "amount": 100}).status_code == 403
    assert client.delete("/api/expenses/1").status_code == 403


def test_bad_requests(client, auth):
    assert client.get("/api/overview?month=2026-99").status_code == 400
    assert client.get("/api/export?month=not-a-date").status_code == 400
    assert client.post("/api/expenses", json=[], headers=auth).status_code == 400
    assert client.post("/api/expenses", data="{", content_type="application/json", headers=auth).status_code == 400
    assert client.put("/api/expenses/999", json=expense(), headers=auth).status_code == 404


def test_csv_quotes_and_spreadsheet_formulas(client, auth):
    client.post("/api/expenses", json=expense(category="=SUM(1,2)", note='Lunch, "with friends"'), headers=auth)
    response = client.get("/api/export?month=2026-11")
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.data.decode("utf-8-sig"))))
    assert rows[1] == ["2026-11-15", "'=SUM(1,2)", "12.50", 'Lunch, "with friends"']
    assert "penny-2026-11.csv" in response.headers["Content-Disposition"]


def test_legacy_import_happens_only_once(tmp_path):
    original = [{"category": "еда", "amount": 100}, {"category": "food", "amount": 50}]
    legacy = tmp_path / "practice_expenses.json"
    legacy.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    before = legacy.read_bytes()
    config = {"TESTING": True, "DATABASE": str(tmp_path / "app.sqlite3"), "LEGACY_FILE": str(legacy)}
    for _ in range(2):
        app = create_app(config)
        data = app.test_client().get(f'/api/overview?month={date.today():%Y-%m}').json
        assert len(data["expenses"]) == 2
        assert data["total_cents"] == 15000
    assert legacy.read_bytes() == before


def test_invalid_legacy_is_preserved_and_import_is_atomic(tmp_path):
    legacy = tmp_path / "practice_expenses.json"
    legacy.write_text('[{"category":"food","amount":10},{"category":"","amount":20}]', encoding="utf-8")
    before = legacy.read_bytes()
    config = {"TESTING": True, "DATABASE": str(tmp_path / "app.sqlite3"), "LEGACY_FILE": str(legacy)}
    with pytest.raises(RuntimeError, match="Could not import"):
        create_app(config)
    assert legacy.read_bytes() == before
    app = create_app({**config, "LEGACY_FILE": None})
    assert app.test_client().get(f'/api/overview?month={date.today():%Y-%m}').json["expenses"] == []


def test_html_and_assets(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Penny" in response.text
    assert "Content-Security-Policy" in response.headers
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200
